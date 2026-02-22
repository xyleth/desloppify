"""Direct tests for review packet blinding and subjective import guardrails."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from desloppify.app.commands.review.import_helpers import load_import_findings_data
from desloppify.app.commands.review.prepare import do_prepare
from desloppify.app.commands.review.runner_helpers import write_packet_snapshot


def _colorize(text: str, _style: str) -> str:
    return text


def test_import_rejects_sub100_assessment_without_feedback(tmp_path, capsys):
    payload = {
        "findings": [],
        "assessments": {
            "naming_quality": 95,
            "logic_clarity": {"score": 92},
        },
    }
    findings_path = tmp_path / "findings.json"
    findings_path.write_text(json.dumps(payload))

    with pytest.raises(SystemExit) as exc:
        load_import_findings_data(str(findings_path), colorize_fn=_colorize)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "assessments below 100 must include explicit feedback" in err
    assert "naming_quality (95.0)" in err
    assert "logic_clarity (92.0)" in err


def test_import_accepts_sub100_assessment_with_dimension_feedback(tmp_path):
    payload = {
        "findings": [
            {
                "dimension": "naming_quality",
                "identifier": "processData",
                "summary": "Generic name",
                "suggestion": "Rename to reconcile_invoice",
                "confidence": "medium",
            }
        ],
        "assessments": {"naming_quality": 95},
    }
    findings_path = tmp_path / "findings.json"
    findings_path.write_text(json.dumps(payload))

    parsed = load_import_findings_data(str(findings_path), colorize_fn=_colorize)
    assert parsed["assessments"]["naming_quality"] == 95


def test_import_accepts_perfect_assessment_without_feedback(tmp_path):
    payload = {
        "findings": [],
        "assessments": {"naming_quality": 100},
    }
    findings_path = tmp_path / "findings.json"
    findings_path.write_text(json.dumps(payload))

    parsed = load_import_findings_data(str(findings_path), colorize_fn=_colorize)
    assert parsed["assessments"]["naming_quality"] == 100


def test_write_packet_snapshot_redacts_target_from_blind_packet(tmp_path):
    packet = {
        "command": "review",
        "config": {"target_strict_score": 98, "noise_budget": 10},
        "dimensions": ["high_level_elegance"],
    }
    review_packet_dir = tmp_path / "review_packets"
    blind_path = tmp_path / "review_packet_blind.json"

    def _safe_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    packet_path, _ = write_packet_snapshot(
        packet,
        stamp="20260218_160000",
        review_packet_dir=review_packet_dir,
        blind_path=blind_path,
        safe_write_text_fn=_safe_write,
    )

    immutable_payload = json.loads(packet_path.read_text())
    blind_payload = json.loads(blind_path.read_text())

    assert immutable_payload["config"]["target_strict_score"] == 98
    assert "target_strict_score" not in blind_payload["config"]
    assert blind_payload["config"]["noise_budget"] == 10


from unittest.mock import patch


_P_SETUP = "desloppify.app.commands.review.prepare.review_runtime_mod.setup_lang_concrete"
_P_NARRATIVE = "desloppify.app.commands.review.prepare.narrative_mod.compute_narrative"
_P_REVIEW_PREP = "desloppify.app.commands.review.prepare.review_mod.prepare_holistic_review"
_P_REVIEW_OPTS = "desloppify.app.commands.review.prepare.review_mod.HolisticReviewPrepareOptions"
_P_NARRATIVE_CTX = "desloppify.app.commands.review.prepare.narrative_mod.NarrativeContext"
_P_WRITE_QUERY = "desloppify.app.commands.review.prepare.write_query"


def _do_prepare_patched(*, total_files: int = 3, state: dict | None = None, config: dict | None = None):
    """Call do_prepare with mocked dependencies; return captured write_query payload."""
    args = SimpleNamespace(path=".", dimensions=None)
    captured: dict = {}

    def _fake_write_query(payload):
        captured.update(payload)

    with (
        patch(_P_SETUP, return_value=(SimpleNamespace(name="python"), [])),
        patch(_P_NARRATIVE, return_value={"headline": "x"}),
        patch(_P_REVIEW_PREP, return_value={
            "total_files": total_files,
            "investigation_batches": [],
            "workflow": [],
        }),
        patch(_P_REVIEW_OPTS, side_effect=lambda **kw: SimpleNamespace(**kw)),
        patch(_P_NARRATIVE_CTX, side_effect=lambda **kw: SimpleNamespace(**kw)),
        patch(_P_WRITE_QUERY, side_effect=_fake_write_query),
    ):
        do_prepare(
            args,
            state=state or {},
            lang=SimpleNamespace(name="python"),
            _state_path=None,
            config=config or {},
        )
    return captured


def test_review_prepare_zero_files_exits_with_error(capsys):
    """Regression guard for issue #127: 0-file result must error, not silently succeed."""
    with pytest.raises(SystemExit) as exc:
        _do_prepare_patched(total_files=0)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "no files found" in err.lower()


def test_review_prepare_zero_files_hints_scan_path(capsys):
    """When state has a scan_path, the error hint mentions it."""
    with pytest.raises(SystemExit):
        _do_prepare_patched(total_files=0, state={"scan_path": "."})
    err = capsys.readouterr().err
    assert "--path" in err


def test_review_prepare_query_redacts_target_score():
    captured = _do_prepare_patched(
        total_files=3,
        config={"target_strict_score": 98, "noise_budget": 10},
    )

    assert "config" in captured
    config = captured["config"]
    assert isinstance(config, dict)
    assert "target_strict_score" not in config
    assert config.get("noise_budget") == 10
