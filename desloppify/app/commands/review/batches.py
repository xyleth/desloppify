"""Batch execution flow helpers for review command."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _validate_runner(runner: str, *, colorize_fn) -> None:
    """Validate review batch runner."""
    if runner == "codex":
        return
    print(
        colorize_fn(
            f"  Error: unsupported runner '{runner}' (supported: codex)", "red"
        ),
        file=sys.stderr,
    )
    sys.exit(2)


def _require_batches(
    packet: dict,
    *,
    colorize_fn,
    suggested_prepare_cmd: str | None = None,
) -> list[dict]:
    """Return investigation batches or exit with a clear error."""
    batches = packet.get("investigation_batches", [])
    if isinstance(batches, list) and batches:
        return batches
    print(
        colorize_fn("  Error: packet has no investigation_batches.", "red"),
        file=sys.stderr,
    )
    if isinstance(suggested_prepare_cmd, str) and suggested_prepare_cmd.strip():
        print(
            colorize_fn(
                f"  Regenerate review context first: `{suggested_prepare_cmd}`",
                "yellow",
            ),
            file=sys.stderr,
        )
    print(
        colorize_fn(
            "  Happy path: `desloppify review --run-batches --runner codex --parallel --scan-after-import`.",
            "dim",
        ),
        file=sys.stderr,
    )
    sys.exit(1)


def _print_review_quality(quality: object, *, colorize_fn) -> None:
    """Render merged review quality summary when present."""
    if not isinstance(quality, dict):
        return
    coverage = quality.get("dimension_coverage")
    density = quality.get("evidence_density")
    high_no_risk = quality.get("high_score_without_risk")
    finding_pressure = quality.get("finding_pressure")
    dims_with_findings = quality.get("dimensions_with_findings")
    if not isinstance(coverage, int | float) or not isinstance(density, int | float):
        return

    pressure_segment = ""
    if isinstance(finding_pressure, int | float) and isinstance(dims_with_findings, int):
        pressure_segment = (
            f", finding-pressure {float(finding_pressure):.2f} "
            f"across {dims_with_findings} dims"
        )
    print(
        colorize_fn(
            "  Review quality: "
            f"dimension coverage {float(coverage):.2f}, "
            f"evidence density {float(density):.2f}, "
            f"high-score-no-risk {int(high_no_risk or 0)}"
            f"{pressure_segment}",
            "dim",
        )
    )


def _collect_reviewed_files_from_batches(
    *,
    batches: list[dict],
    selected_indexes: list[int],
) -> list[str]:
    """Collect normalized file paths reviewed in the selected batch set."""
    reviewed: list[str] = []
    seen: set[str] = set()
    for idx in selected_indexes:
        if idx < 0 or idx >= len(batches):
            continue
        batch = batches[idx]
        if not isinstance(batch, dict):
            continue
        files = batch.get("files_to_read", [])
        if not isinstance(files, list):
            continue
        for raw in files:
            if not isinstance(raw, str):
                continue
            path = raw.strip().strip(",'\"")
            if not path or path in {".", ".."}:
                continue
            if path.endswith("/"):
                continue
            if path in seen:
                continue
            seen.add(path)
            reviewed.append(path)
    return reviewed


def do_run_batches(
    args,
    state,
    lang,
    state_file,
    *,
    config: dict | None,
    run_stamp_fn,
    load_or_prepare_packet_fn,
    selected_batch_indexes_fn,
    prepare_run_artifacts_fn,
    run_codex_batch_fn,
    execute_batches_fn,
    collect_batch_results_fn,
    print_failures_and_exit_fn,
    merge_batch_results_fn,
    build_import_provenance_fn,
    do_import_fn,
    run_followup_scan_fn,
    safe_write_text_fn,
    colorize_fn,
    project_root: Path,
    subagent_runs_dir: Path,
) -> None:
    """Run holistic investigation batches with a local subagent runner."""
    config = config or {}
    runner = getattr(args, "runner", "codex")
    _validate_runner(runner, colorize_fn=colorize_fn)

    stamp = run_stamp_fn()
    packet, immutable_packet_path, prompt_packet_path = load_or_prepare_packet_fn(
        args,
        state=state,
        lang=lang,
        config=config,
        stamp=stamp,
    )

    scan_path = str(getattr(args, "path", ".") or ".")
    suggested_prepare_cmd = f"desloppify review --prepare --path {scan_path}"
    batches = _require_batches(
        packet,
        colorize_fn=colorize_fn,
        suggested_prepare_cmd=suggested_prepare_cmd,
    )

    selected_indexes = selected_batch_indexes_fn(args, batch_count=len(batches))
    run_dir, logs_dir, prompt_files, output_files, log_files = prepare_run_artifacts_fn(
        stamp=stamp,
        selected_indexes=selected_indexes,
        batches=batches,
        packet_path=prompt_packet_path,
        run_root=subagent_runs_dir,
        repo_root=project_root,
    )

    if getattr(args, "dry_run", False):
        print(
            colorize_fn(
                "  Dry run only: prompts generated, runner execution skipped.", "yellow"
            )
        )
        print(colorize_fn(f"  Immutable packet: {immutable_packet_path}", "dim"))
        print(colorize_fn(f"  Blind packet: {prompt_packet_path}", "dim"))
        print(colorize_fn(f"  Prompts: {run_dir / 'prompts'}", "dim"))
        return

    def _run_batch(*, prompt: str, output_file: Path, log_file: Path) -> int:
        return run_codex_batch_fn(
            prompt=prompt,
            repo_root=project_root,
            output_file=output_file,
            log_file=log_file,
        )

    total_batches = len(selected_indexes)
    batch_positions = {batch_idx: pos + 1 for pos, batch_idx in enumerate(selected_indexes)}

    def _report_progress(batch_index: int, event: str, code: int | None = None) -> None:
        position = batch_positions.get(batch_index, 0)
        if event == "start":
            print(
                colorize_fn(
                    f"  Batch {position}/{total_batches} started (#{batch_index + 1})",
                    "dim",
                )
            )
            return
        if event == "done":
            status = "done" if code == 0 else f"failed ({code})"
            tone = "dim" if code == 0 else "yellow"
            print(
                colorize_fn(
                    f"  Batch {position}/{total_batches} {status} (#{batch_index + 1})",
                    tone,
                )
            )

    failures = execute_batches_fn(
        selected_indexes=selected_indexes,
        prompt_files=prompt_files,
        output_files=output_files,
        log_files=log_files,
        run_parallel=bool(getattr(args, "parallel", False)),
        run_batch_fn=_run_batch,
        safe_write_text_fn=safe_write_text_fn,
        progress_fn=_report_progress,
    )

    allowed_dims = {
        str(dim) for dim in packet.get("dimensions", []) if isinstance(dim, str)
    }
    batch_results, failures = collect_batch_results_fn(
        selected_indexes=selected_indexes,
        failures=failures,
        output_files=output_files,
        allowed_dims=allowed_dims,
    )

    if failures:
        print_failures_and_exit_fn(
            failures=failures,
            packet_path=immutable_packet_path,
            logs_dir=logs_dir,
            colorize_fn=colorize_fn,
        )

    merged = merge_batch_results_fn(batch_results)
    reviewed_files = _collect_reviewed_files_from_batches(
        batches=batches,
        selected_indexes=selected_indexes,
    )
    if reviewed_files:
        merged["reviewed_files"] = reviewed_files
        print(
            colorize_fn(
                f"  Reviewed files captured for cache refresh: {len(reviewed_files)}",
                "dim",
            )
        )
    merged["provenance"] = build_import_provenance_fn(
        runner=runner,
        blind_packet_path=prompt_packet_path,
        run_stamp=stamp,
        batch_indexes=selected_indexes,
    )
    merged_path = run_dir / "holistic_findings_merged.json"
    safe_write_text_fn(merged_path, json.dumps(merged, indent=2) + "\n")
    print(colorize_fn(f"\n  Merged outputs: {merged_path}", "bold"))
    _print_review_quality(merged.get("review_quality", {}), colorize_fn=colorize_fn)
    allow_partial = getattr(args, "allow_partial", False)
    if not isinstance(allow_partial, bool):
        allow_partial = False

    do_import_fn(
        str(merged_path),
        state,
        lang,
        state_file,
        config=config,
        allow_partial=allow_partial,
        trusted_assessment_source=True,
        trusted_assessment_label="trusted internal run-batches import",
    )

    if getattr(args, "scan_after_import", False):
        followup_code = run_followup_scan_fn(
            lang_name=lang.name,
            scan_path=str(args.path),
        )
        if followup_code != 0:
            print(
                colorize_fn(
                    f"  Follow-up scan failed with exit code {followup_code}.",
                    "red",
                ),
                file=sys.stderr,
            )
            raise SystemExit(followup_code)


__all__ = ["do_run_batches"]
