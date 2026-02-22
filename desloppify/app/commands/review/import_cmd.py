"""Import flow helpers for review command."""

from __future__ import annotations

import sys

from desloppify import state as state_mod
from desloppify.app.commands.helpers.query import write_query
from desloppify.app.commands.review import import_helpers as import_helpers_mod
from desloppify.app.commands.review import output as review_output_mod
from desloppify.intelligence import narrative as narrative_mod
from desloppify.intelligence import review as review_mod
from desloppify.intelligence.narrative.core import NarrativeContext
from desloppify.utils import colorize


def subjective_at_target_dimensions(
    state_or_dim_scores: dict,
    dim_scores: dict | None = None,
    *,
    target: float,
    scorecard_subjective_entries_fn,
    matches_target_score_fn,
) -> list[dict]:
    """Return scorecard-aligned subjective rows that sit on the target threshold."""
    state = state_or_dim_scores
    if dim_scores is None:
        dim_scores = state_or_dim_scores
        state = {"dimension_scores": dim_scores}

    rows: list[dict] = []
    for entry in scorecard_subjective_entries_fn(state, dim_scores=dim_scores):
        if entry.get("placeholder"):
            continue
        strict_val = float(entry.get("strict", entry.get("score", 100.0)))
        if matches_target_score_fn(strict_val, target):
            rows.append(
                {
                    "name": str(entry.get("name", "Subjective")),
                    "score": strict_val,
                    "cli_keys": list(entry.get("cli_keys", [])),
                }
            )
    rows.sort(key=lambda item: item["name"].lower())
    return rows


def do_import(
    import_file,
    state,
    lang,
    state_file,
    *,
    config: dict | None = None,
    assessment_override: bool = False,
    assessment_note: str | None = None,
) -> None:
    """Import mode: ingest agent-produced findings."""
    if assessment_override and (
        not isinstance(assessment_note, str) or not assessment_note.strip()
    ):
        print(
            colorize(
                "  Error: --assessment-override requires --assessment-note",
                "red",
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    findings_data = import_helpers_mod.load_import_findings_data(
        import_file,
        colorize_fn=colorize,
        assessment_override=assessment_override,
        assessment_note=assessment_note,
    )

    diff = review_mod.import_holistic_findings(findings_data, state, lang.name)
    label = "Holistic review"

    if assessment_override:
        audit = state.setdefault("assessment_import_audit", [])
        audit.append(
            {
                "timestamp": state_mod.utc_now(),
                "override_used": True,
                "note": (assessment_note or "").strip(),
                "import_file": str(import_file),
            }
        )
    state_mod.save_state(state, state_file)

    lang_name = lang.name
    narrative = narrative_mod.compute_narrative(
        state, NarrativeContext(lang=lang_name, command="review")
    )

    print(colorize(f"\n  {label} imported:", "bold"))
    print(
        colorize(
            f"  +{diff['new']} new findings, "
            f"{diff['auto_resolved']} resolved, "
            f"{diff['reopened']} reopened",
            "dim",
        )
    )
    import_helpers_mod.print_skipped_validation_details(diff, colorize_fn=colorize)
    import_helpers_mod.print_assessments_summary(state, colorize_fn=colorize)
    next_command = import_helpers_mod.print_open_review_summary(
        state, colorize_fn=colorize
    )
    at_target = review_output_mod._print_review_import_scores_and_integrity(
        state, config or {}
    )

    print(
        colorize(
            f"  Next command to improve subjective scores: `{next_command}`", "dim"
        )
    )
    write_query(
        {
            "command": "review",
            "action": "import",
            "mode": "holistic",
            "diff": diff,
            "next_command": next_command,
            "subjective_at_target": [
                {"dimension": entry["name"], "score": entry["score"]}
                for entry in at_target
            ],
            "narrative": narrative,
        }
    )


__all__ = ["do_import", "subjective_at_target_dimensions"]
