"""Prepare flow for review command."""

from __future__ import annotations

import sys
from pathlib import Path

from desloppify.app.commands.helpers.query import write_query
from desloppify.app.commands.review import runtime as review_runtime_mod
from desloppify.intelligence import narrative as narrative_mod
from desloppify.intelligence import review as review_mod
from desloppify.utils import colorize


def _redacted_review_config(config: dict | None) -> dict:
    """Return review packet config with target score removed for blind assessment."""
    if not isinstance(config, dict):
        return {}
    return {key: value for key, value in config.items() if key != "target_strict_score"}


def do_prepare(
    args,
    state,
    lang,
    _state_path,
    *,
    config: dict,
) -> None:
    """Prepare mode: holistic-only review packet in query.json."""
    path = Path(args.path)
    dims_str = getattr(args, "dimensions", None)
    dimensions = dims_str.split(",") if dims_str else None

    lang_run, found_files = review_runtime_mod.setup_lang_concrete(lang, path, config)

    lang_name = lang_run.name
    narrative = narrative_mod.compute_narrative(
        state,
        context=narrative_mod.NarrativeContext(lang=lang_name, command="review"),
    )
    data = review_mod.prepare_holistic_review(
        path,
        lang_run,
        state,
        options=review_mod.HolisticReviewPrepareOptions(
            dimensions=dimensions,
            files=found_files or None,
        ),
    )
    data["config"] = _redacted_review_config(config)
    data["narrative"] = narrative
    data["next_command"] = "desloppify review --import findings.json"
    total = data.get("total_files", 0)
    if total == 0:
        print(
            colorize(
                f"\n  Error: no files found at path '{path}'. "
                "Nothing to review.",
                "red",
            ),
            file=sys.stderr,
        )
        scan_path = state.get("scan_path") if isinstance(state, dict) else None
        if scan_path:
            print(
                colorize(
                    f"  Hint: your last scan used --path {scan_path}. "
                    f"Try: desloppify review --prepare --path {scan_path}",
                    "yellow",
                ),
                file=sys.stderr,
            )
        else:
            print(
                colorize(
                    "  Hint: pass --path <dir> matching the path used during scan.",
                    "yellow",
                ),
                file=sys.stderr,
            )
        sys.exit(1)
    write_query(data)
    batches = data.get("investigation_batches", [])
    print(colorize(f"\n  Holistic review prepared: {total} files in codebase", "bold"))
    if batches:
        print(
            colorize(
                "\n  Investigation batches (independent — can run in parallel):", "bold"
            )
        )
        for i, batch in enumerate(batches, 1):
            n_files = len(batch["files_to_read"])
            print(
                colorize(
                    f"    {i}. {batch['name']} ({n_files} files) — {batch['why']}",
                    "dim",
                )
            )
    print(colorize("\n  Workflow:", "bold"))
    for step_i, step in enumerate(data.get("workflow", []), 1):
        print(colorize(f"    {step_i}. {step}", "dim"))
    print(colorize("\n  AGENT PLAN:", "yellow"))
    print(
        colorize(
            "  1. Run each investigation batch independently (parallel-friendly)", "dim"
        )
    )
    print(colorize("  2. Capture findings in findings.json", "dim"))
    print(colorize("  3. Import and rescan", "dim"))
    print(
        colorize(
            "  Next command to improve subjective scores: `desloppify review --import findings.json`",
            "dim",
        )
    )
    print(
        colorize(
            "\n  → query.json updated. "
            "Review codebase, then: desloppify review --import findings.json",
            "cyan",
        )
    )


__all__ = ["do_prepare"]
