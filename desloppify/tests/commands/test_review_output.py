"""Tests for desloppify.app.commands.review.output — delegation/wiring layer."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from desloppify.app.commands.review import output as review_output_mod


def _colorize(text: str, _style: str) -> str:
    """Identity colorize for testing."""
    return text


# ── _subjective_at_target_dimensions ─────────────────────────────────


def test_subjective_at_target_delegates_with_correct_fns():
    """_subjective_at_target_dimensions wires in the right callable dependencies."""
    mock_subjective_at_target = MagicMock(return_value=[{"name": "Naming", "score": 95.0}])

    with patch.object(
        review_output_mod,
        "review_import_mod",
        SimpleNamespace(subjective_at_target_dimensions=mock_subjective_at_target),
    ):
        result = review_output_mod._subjective_at_target_dimensions(
            {"dimension_scores": {}}, None, target=95.0
        )

    assert mock_subjective_at_target.called
    call_kwargs = mock_subjective_at_target.call_args
    assert call_kwargs.kwargs["target"] == 95.0
    # The two function callables are passed through
    assert callable(call_kwargs.kwargs["scorecard_subjective_entries_fn"])
    assert callable(call_kwargs.kwargs["matches_target_score_fn"])
    assert result == [{"name": "Naming", "score": 95.0}]


def test_subjective_at_target_passes_through_state_and_dim_scores():
    """Both state_or_dim_scores and dim_scores are forwarded to the underlying function."""
    captured_args = {}

    def _capture(*args, **kwargs):
        captured_args["args"] = args
        captured_args["kwargs"] = kwargs
        return []

    with patch.object(
        review_output_mod,
        "review_import_mod",
        SimpleNamespace(subjective_at_target_dimensions=_capture),
    ):
        state = {"dimension_scores": {"code_quality": {"score": 85}}}
        dim_scores = {"code_quality": {"score": 85}}
        review_output_mod._subjective_at_target_dimensions(
            state, dim_scores, target=90.0
        )

    assert captured_args["args"] == (state, dim_scores)
    assert captured_args["kwargs"]["target"] == 90.0


# ── _load_import_findings_data ───────────────────────────────────────


def test_load_import_findings_data_valid_file(tmp_path):
    """Successfully loads a valid import file and returns parsed data."""
    payload = {
        "findings": [
            {
                "dimension": "code_quality",
                "identifier": "processData",
                "summary": "Generic name",
                "suggestion": "Rename",
                "confidence": "medium",
            }
        ],
    }
    findings_file = tmp_path / "findings.json"
    findings_file.write_text(json.dumps(payload))

    result = review_output_mod._load_import_findings_data(str(findings_file))
    assert "findings" in result
    assert len(result["findings"]) == 1
    assert result["findings"][0]["identifier"] == "processData"


def test_load_import_findings_data_missing_file_exits(tmp_path):
    """Missing import file triggers sys.exit(1)."""
    with pytest.raises(SystemExit) as exc:
        review_output_mod._load_import_findings_data(str(tmp_path / "nope.json"))
    assert exc.value.code == 1


def test_load_import_findings_data_passes_override_flags(tmp_path):
    """assessment_override and assessment_note are forwarded."""
    # A sub-100 assessment without feedback normally fails.
    # With override + note, it should pass.
    payload = {
        "findings": [],
        "assessments": {"naming_quality": 90},
    }
    findings_file = tmp_path / "findings.json"
    findings_file.write_text(json.dumps(payload))

    result = review_output_mod._load_import_findings_data(
        str(findings_file),
        assessment_override=True,
        assessment_note="Reviewed carefully, score is justified",
    )
    assert result["assessments"]["naming_quality"] == 90


# ── _print_skipped_validation_details ────────────────────────────────


def test_print_skipped_validation_details_no_skipped(capsys):
    """No output when diff has no skipped findings."""
    review_output_mod._print_skipped_validation_details({"skipped": 0})
    out = capsys.readouterr()
    assert out.out == ""


def test_print_skipped_validation_details_with_skipped(capsys):
    """Prints warning for each skipped finding with details."""
    diff = {
        "skipped": 2,
        "skipped_details": [
            {"index": 0, "identifier": "foo", "missing": ["summary", "confidence"]},
            {"index": 1, "identifier": "bar", "missing": ["invalid dimension_name"]},
        ],
    }
    review_output_mod._print_skipped_validation_details(diff)
    out = capsys.readouterr().out
    assert "2 finding(s) skipped" in out
    assert "foo" in out
    assert "bar" in out


# ── _print_assessments_summary ───────────────────────────────────────


def test_print_assessments_summary_with_assessments(capsys):
    """Prints assessment scores when present in state."""
    state = {
        "subjective_assessments": {
            "naming_quality": {"score": 92},
            "logic_clarity": {"score": 88},
        }
    }
    review_output_mod._print_assessments_summary(state)
    out = capsys.readouterr().out
    assert "logic clarity 88" in out
    assert "naming quality 92" in out


def test_print_assessments_summary_no_assessments(capsys):
    """No output when state has no assessments."""
    review_output_mod._print_assessments_summary({})
    out = capsys.readouterr().out
    assert out == ""


# ── _print_open_review_summary ───────────────────────────────────────


def test_print_open_review_summary_no_open_findings(capsys):
    """Returns 'desloppify scan' when no open review findings exist."""
    state = {"findings": {}}
    result = review_output_mod._print_open_review_summary(state)
    assert result == "desloppify scan"
    assert capsys.readouterr().out == ""


def test_print_open_review_summary_with_open_findings(capsys):
    """Returns 'desloppify issues' and prints count when open findings exist."""
    state = {
        "findings": {
            "f1": {"status": "open", "detector": "review"},
            "f2": {"status": "open", "detector": "review"},
            "f3": {"status": "resolved", "detector": "review"},
            "f4": {"status": "open", "detector": "smells"},
        }
    }
    result = review_output_mod._print_open_review_summary(state)
    assert result == "desloppify issues"
    out = capsys.readouterr().out
    assert "2 review findings open total" in out


# ── _print_review_import_scores_and_integrity ────────────────────────


def test_print_review_import_scores_and_integrity_no_at_target(capsys):
    """Returns empty list when no subjective scores match the target."""
    state = {"dimension_scores": {}}
    config = {"target_strict_score": 95}

    mock_state_mod = SimpleNamespace(
        score_snapshot=lambda s: SimpleNamespace(
            overall=90.0, objective=92.0, strict=88.0, verified=None
        )
    )

    with (
        patch.object(review_output_mod, "state_mod", mock_state_mod),
        patch.object(
            review_output_mod,
            "target_strict_score_from_config",
            return_value=95.0,
        ),
        patch.object(
            review_output_mod,
            "_subjective_at_target_dimensions",
            return_value=[],
        ),
    ):
        result = review_output_mod._print_review_import_scores_and_integrity(
            state, config
        )

    assert result == []
    out = capsys.readouterr().out
    assert "90.0/100" in out


def test_print_review_import_scores_and_integrity_warns_multiple_at_target(capsys):
    """Prints red warning when >= 2 subjective scores match the target."""
    state = {"dimension_scores": {}}
    config = {"target_strict_score": 95}
    at_target = [
        {"name": "Naming", "score": 95.0, "cli_keys": ["naming"]},
        {"name": "Logic", "score": 95.0, "cli_keys": ["logic"]},
    ]

    mock_state_mod = SimpleNamespace(
        score_snapshot=lambda s: SimpleNamespace(
            overall=95.0, objective=96.0, strict=95.0, verified=None
        )
    )

    with (
        patch.object(review_output_mod, "state_mod", mock_state_mod),
        patch.object(
            review_output_mod,
            "target_strict_score_from_config",
            return_value=95.0,
        ),
        patch.object(
            review_output_mod,
            "_subjective_at_target_dimensions",
            return_value=at_target,
        ),
        patch.object(
            review_output_mod,
            "reporting_dimensions_mod",
            SimpleNamespace(subjective_rerun_command=lambda rows, max_items=5: "review --dimensions naming,logic"),
        ),
    ):
        result = review_output_mod._print_review_import_scores_and_integrity(
            state, config
        )

    assert len(result) == 2
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "2 subjective scores match the target" in out
