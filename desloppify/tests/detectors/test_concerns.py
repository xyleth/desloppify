"""Tests for concern generators (mechanical → subjective bridge)."""

from __future__ import annotations

from desloppify.core.registry import JUDGMENT_DETECTORS
from desloppify.engine.concerns import (
    cleanup_stale_dismissals,
    generate_concerns,
    _fingerprint,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_finding(
    detector: str,
    file: str,
    name: str,
    *,
    detail: dict | None = None,
    status: str = "open",
) -> dict:
    fid = f"{detector}::{file}::{name}"
    return {
        "id": fid,
        "detector": detector,
        "file": file,
        "tier": 3,
        "confidence": "high",
        "summary": f"test finding {name}",
        "detail": detail or {},
        "status": status,
        "note": None,
        "first_seen": "2026-01-01T00:00:00+00:00",
        "last_seen": "2026-01-01T00:00:00+00:00",
        "resolved_at": None,
        "reopen_count": 0,
    }


def _state_with_findings(*findings: dict) -> dict:
    return {"findings": {f["id"]: f for f in findings}}


# ── Elevated single-detector signals ─────────────────────────────────


class TestElevatedSignals:
    """Files with a single judgment detector but strong signals get flagged."""

    def test_monster_function_flags(self):
        f = _make_finding(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "do_everything", "loc": 200},
        )
        concerns = generate_concerns(_state_with_findings(f))
        assert len(concerns) == 1
        c = concerns[0]
        assert c.type == "structural_complexity"
        assert c.file == "app/big.py"
        assert "do_everything" in c.summary
        assert "200" in c.summary

    def test_high_params_flags(self):
        f = _make_finding(
            "structural", "app/service.py", "struct",
            detail={"signals": {"max_params": 12}},
        )
        concerns = generate_concerns(_state_with_findings(f))
        assert len(concerns) == 1
        assert concerns[0].type == "interface_design"
        assert "12" in concerns[0].summary

    def test_deep_nesting_flags(self):
        f = _make_finding(
            "structural", "app/nested.py", "struct",
            detail={"signals": {"max_nesting": 8}},
        )
        concerns = generate_concerns(_state_with_findings(f))
        assert len(concerns) == 1
        assert concerns[0].type == "structural_complexity"
        assert "8" in concerns[0].summary

    def test_large_file_flags(self):
        f = _make_finding(
            "structural", "app/huge.py", "struct",
            detail={"signals": {"loc": 500}},
        )
        concerns = generate_concerns(_state_with_findings(f))
        assert len(concerns) == 1

    def test_duplication_flags(self):
        f = _make_finding("dupes", "app/dup.py", "dup1")
        concerns = generate_concerns(_state_with_findings(f))
        assert len(concerns) == 1
        assert concerns[0].type == "duplication_design"

    def test_coupling_flags(self):
        f = _make_finding("coupling", "app/coupled.py", "coupling1")
        concerns = generate_concerns(_state_with_findings(f))
        assert len(concerns) == 1
        assert concerns[0].type == "coupling_design"

    def test_responsibility_cohesion_flags(self):
        f = _make_finding("responsibility_cohesion", "app/mixed.py", "resp1")
        concerns = generate_concerns(_state_with_findings(f))
        assert len(concerns) == 1
        assert concerns[0].type == "mixed_responsibilities"


# ── Non-elevated single-detector — no flag ───────────────────────────


class TestNonElevatedSkipped:
    """A single judgment detector without elevated signals is NOT flagged."""

    def test_single_naming_not_flagged(self):
        f = _make_finding("naming", "app/file.py", "name1")
        assert generate_concerns(_state_with_findings(f)) == []

    def test_single_patterns_not_flagged(self):
        f = _make_finding("patterns", "app/file.py", "pat1")
        assert generate_concerns(_state_with_findings(f)) == []

    def test_moderate_structural_not_flagged(self):
        f = _make_finding(
            "structural", "app/ok.py", "struct",
            detail={"signals": {"loc": 150, "max_params": 5, "max_nesting": 3}},
        )
        assert generate_concerns(_state_with_findings(f)) == []

    def test_non_monster_smell_not_flagged(self):
        f = _make_finding(
            "smells", "app/file.py", "smell",
            detail={"smell_id": "dead_useeffect"},
        )
        assert generate_concerns(_state_with_findings(f)) == []


# ── Clear-cut detectors — never flagged alone ────────────────────────


class TestClearCutDetectorsSkipped:
    """Auto-fixable / clear-cut detectors don't generate concerns."""

    def test_unused_not_flagged(self):
        f = _make_finding("unused", "app/file.py", "unused1")
        assert generate_concerns(_state_with_findings(f)) == []

    def test_logs_not_flagged(self):
        f = _make_finding("logs", "app/file.py", "log1")
        assert generate_concerns(_state_with_findings(f)) == []

    def test_security_not_flagged(self):
        f = _make_finding("security", "app/file.py", "sec1")
        assert generate_concerns(_state_with_findings(f)) == []

    def test_two_clearcut_not_flagged(self):
        """Two clear-cut detectors on the same file: no concern."""
        findings = [
            _make_finding("unused", "app/file.py", "unused1"),
            _make_finding("logs", "app/file.py", "log1"),
        ]
        assert generate_concerns(_state_with_findings(*findings)) == []


# ── Multi-detector files ─────────────────────────────────────────────


class TestMultiDetector:
    """Files with 2+ judgment detectors get flagged."""

    def test_two_judgment_detectors_flag(self):
        findings = [
            _make_finding("naming", "app/file.py", "name1"),
            _make_finding("patterns", "app/file.py", "pat1"),
        ]
        concerns = generate_concerns(_state_with_findings(*findings))
        assert len(concerns) == 1
        assert concerns[0].file == "app/file.py"

    def test_three_detectors_is_mixed_responsibilities(self):
        findings = [
            _make_finding("smells", "app/god.py", "smell1"),
            _make_finding("naming", "app/god.py", "name1"),
            _make_finding("structural", "app/god.py", "struct1"),
        ]
        concerns = generate_concerns(_state_with_findings(*findings))
        assert len(concerns) == 1
        assert concerns[0].type == "mixed_responsibilities"
        assert "3" in concerns[0].summary

    def test_judgment_plus_clearcut_not_flagged(self):
        """One judgment + one clear-cut detector = only 1 judgment, not enough."""
        findings = [
            _make_finding("naming", "app/file.py", "name1"),
            _make_finding("unused", "app/file.py", "unused1"),
        ]
        assert generate_concerns(_state_with_findings(*findings)) == []


# ── Evidence and questions ───────────────────────────────────────────


class TestEvidenceAndQuestions:
    """Concerns bundle full context for the LLM."""

    def test_evidence_includes_all_findings(self):
        findings = [
            _make_finding("smells", "app/f.py", "s1"),
            _make_finding("naming", "app/f.py", "n1"),
        ]
        concerns = generate_concerns(_state_with_findings(*findings))
        assert len(concerns) == 1
        evidence = concerns[0].evidence
        # Should include detector list and individual finding summaries.
        assert any("Flagged by:" in e for e in evidence)
        assert any("[smells]" in e for e in evidence)
        assert any("[naming]" in e for e in evidence)

    def test_evidence_includes_signals(self):
        f = _make_finding(
            "structural", "app/f.py", "struct",
            detail={"signals": {"max_params": 15, "max_nesting": 9, "loc": 400}},
        )
        concerns = generate_concerns(_state_with_findings(f))
        evidence = concerns[0].evidence
        assert any("15" in e and "parameters" in e.lower() for e in evidence)
        assert any("9" in e and "nesting" in e.lower() for e in evidence)
        assert any("400" in e for e in evidence)

    def test_question_mentions_monster_function(self):
        f = _make_finding(
            "smells", "app/f.py", "m",
            detail={"smell_id": "monster_function", "function": "big_func", "loc": 200},
        )
        concerns = generate_concerns(_state_with_findings(f))
        assert "big_func" in concerns[0].question

    def test_question_mentions_params(self):
        f = _make_finding(
            "structural", "app/f.py", "s",
            detail={"signals": {"max_params": 10}},
        )
        concerns = generate_concerns(_state_with_findings(f))
        assert "parameter" in concerns[0].question.lower()

    def test_question_mentions_nesting(self):
        f = _make_finding(
            "structural", "app/f.py", "s",
            detail={"signals": {"max_nesting": 7}},
        )
        concerns = generate_concerns(_state_with_findings(f))
        assert "nesting" in concerns[0].question.lower()

    def test_question_mentions_duplication(self):
        f = _make_finding("dupes", "app/f.py", "d")
        concerns = generate_concerns(_state_with_findings(f))
        assert "duplication" in concerns[0].question.lower()

    def test_question_mentions_coupling(self):
        f = _make_finding("coupling", "app/f.py", "c")
        concerns = generate_concerns(_state_with_findings(f))
        assert "coupling" in concerns[0].question.lower()

    def test_question_mentions_orphaned(self):
        findings = [
            _make_finding("orphaned", "app/f.py", "o"),
            _make_finding("naming", "app/f.py", "n"),
        ]
        concerns = generate_concerns(_state_with_findings(*findings))
        assert any("dead" in concerns[0].question.lower() or
                    "orphan" in concerns[0].question.lower()
                    for _ in [1])


# ── Cross-file systemic patterns ─────────────────────────────────────


class TestSystemicPatterns:
    """3+ files with the same detector combo → systemic pattern."""

    def test_three_files_same_combo_flagged(self):
        findings = []
        for fname in ("a.py", "b.py", "c.py"):
            findings.append(_make_finding("smells", fname, "s"))
            findings.append(_make_finding("naming", fname, "n"))
        concerns = generate_concerns(_state_with_findings(*findings))
        systemic = [c for c in concerns if c.type == "systemic_pattern"]
        assert len(systemic) == 1
        assert "3 files" in systemic[0].summary

    def test_two_files_same_combo_not_flagged(self):
        findings = []
        for fname in ("a.py", "b.py"):
            findings.append(_make_finding("smells", fname, "s"))
            findings.append(_make_finding("naming", fname, "n"))
        concerns = generate_concerns(_state_with_findings(*findings))
        systemic = [c for c in concerns if c.type == "systemic_pattern"]
        assert len(systemic) == 0

    def test_systemic_plus_per_file(self):
        """Systemic patterns coexist with per-file concerns."""
        findings = []
        for fname in ("a.py", "b.py", "c.py"):
            findings.append(_make_finding("smells", fname, "s"))
            findings.append(_make_finding("naming", fname, "n"))
        concerns = generate_concerns(_state_with_findings(*findings))
        # Should have per-file concerns AND a systemic pattern.
        per_file = [c for c in concerns if c.type != "systemic_pattern"]
        systemic = [c for c in concerns if c.type == "systemic_pattern"]
        assert len(per_file) == 3
        assert len(systemic) == 1


# ── Dismissal tracking ──────────────────────────────────────────────


class TestDismissals:
    def test_dismissed_concern_suppressed(self):
        f = _make_finding(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "f", "loc": 200},
        )
        state = _state_with_findings(f)
        concerns = generate_concerns(state)
        assert len(concerns) == 1
        fp = concerns[0].fingerprint

        state["concern_dismissals"] = {
            fp: {
                "dismissed_at": "2026-01-01T00:00:00+00:00",
                "reasoning": "Single responsibility",
                "source_finding_ids": [f["id"]],
            }
        }
        assert generate_concerns(state) == []

    def test_dismissed_with_source_ids_suppresses(self):
        """Dismissals with matching source_finding_ids suppress the concern."""
        f = _make_finding(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "f", "loc": 200},
        )
        state = _state_with_findings(f)
        concerns = generate_concerns(state)
        assert len(concerns) == 1
        fp = concerns[0].fingerprint

        # Dismissal with correct source IDs suppresses.
        state["concern_dismissals"] = {
            fp: {
                "dismissed_at": "2026-01-01T00:00:00+00:00",
                "reasoning": "Acceptable complexity",
                "source_finding_ids": [f["id"]],
            }
        }
        assert generate_concerns(state) == []

    def test_stale_dismissal_cleaned_up(self):
        """Dismissals whose source findings are all gone get removed."""
        f = _make_finding(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "f", "loc": 200},
        )
        state = _state_with_findings(f)
        concerns = generate_concerns(state)
        fp = concerns[0].fingerprint

        # Create a dismissal referencing findings that no longer exist.
        state["concern_dismissals"] = {
            "stale_fp_abc123": {
                "dismissed_at": "2026-01-01T00:00:00+00:00",
                "reasoning": "Old dismissal",
                "source_finding_ids": ["gone::finding::1", "gone::finding::2"],
            },
            fp: {
                "dismissed_at": "2026-01-01T00:00:00+00:00",
                "reasoning": "Still valid",
                "source_finding_ids": [f["id"]],
            },
        }
        removed = cleanup_stale_dismissals(state)
        # Stale dismissal removed, valid one stays.
        assert removed == 1
        assert "stale_fp_abc123" not in state["concern_dismissals"]
        assert fp in state["concern_dismissals"]

    def test_stale_dismissal_without_source_ids_not_cleaned(self):
        """Dismissals without source_finding_ids are preserved (legacy)."""
        f = _make_finding(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "f", "loc": 200},
        )
        state = _state_with_findings(f)
        state["concern_dismissals"] = {
            "legacy_fp": {
                "dismissed_at": "2026-01-01T00:00:00+00:00",
                "reasoning": "Legacy dismissal",
            },
        }
        removed = cleanup_stale_dismissals(state)
        # Legacy dismissal without source_finding_ids is NOT cleaned up.
        assert removed == 0
        assert "legacy_fp" in state["concern_dismissals"]

    def test_cleanup_on_empty_state(self):
        """cleanup_stale_dismissals on empty state is a no-op."""
        assert cleanup_stale_dismissals({}) == 0
        assert cleanup_stale_dismissals({"concern_dismissals": {}}) == 0

    def test_generate_concerns_does_not_mutate_dismissals(self):
        """generate_concerns is a pure query — no side effects on state."""
        f = _make_finding(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "f", "loc": 200},
        )
        state = _state_with_findings(f)
        state["concern_dismissals"] = {
            "stale_fp": {
                "dismissed_at": "2026-01-01T00:00:00+00:00",
                "reasoning": "Old",
                "source_finding_ids": ["gone::id"],
            },
        }
        generate_concerns(state)
        # generate_concerns must NOT remove stale dismissals.
        assert "stale_fp" in state["concern_dismissals"]

    def test_dismissed_resurfaces_on_changed_findings(self):
        f = _make_finding(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "f", "loc": 200},
        )
        state = _state_with_findings(f)
        concerns = generate_concerns(state)
        fp = concerns[0].fingerprint

        state["concern_dismissals"] = {
            fp: {
                "dismissed_at": "2026-01-01T00:00:00+00:00",
                "reasoning": "Was fine",
                "source_finding_ids": ["other::finding::id"],
            }
        }
        assert len(generate_concerns(state)) == 1


# ── Edge cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_state(self):
        assert generate_concerns({}) == []
        assert generate_concerns({"findings": {}}) == []

    def test_non_open_findings_ignored(self):
        f = _make_finding(
            "smells", "app/big.py", "monster",
            detail={"smell_id": "monster_function", "function": "f", "loc": 200},
            status="fixed",
        )
        assert generate_concerns(_state_with_findings(f)) == []

    def test_holistic_file_ignored(self):
        """File '.' (holistic findings) should not generate concerns."""
        findings = [
            _make_finding("smells", ".", "s"),
            _make_finding("naming", ".", "n"),
            _make_finding("structural", ".", "st"),
            _make_finding("patterns", ".", "p"),
        ]
        assert generate_concerns(_state_with_findings(*findings)) == []

    def test_results_sorted_by_type_then_file(self):
        findings = [
            _make_finding("dupes", "z_file.py", "d"),
            _make_finding(
                "smells", "a_file.py", "m",
                detail={"smell_id": "monster_function", "function": "f", "loc": 150},
            ),
        ]
        concerns = generate_concerns(_state_with_findings(*findings))
        assert len(concerns) == 2
        for a, b in zip(concerns, concerns[1:]):
            assert (a.type, a.file) <= (b.type, b.file)

    def test_no_duplicate_fingerprints(self):
        findings = [
            _make_finding("smells", "a.py", "s"),
            _make_finding("naming", "a.py", "n"),
        ]
        concerns = generate_concerns(_state_with_findings(*findings))
        fps = [c.fingerprint for c in concerns]
        assert len(fps) == len(set(fps))


# ── Fingerprint stability ───────────────────────────────────────────


class TestFingerprint:
    def test_deterministic(self):
        fp1 = _fingerprint("t", "f.py", ("x", "y"))
        fp2 = _fingerprint("t", "f.py", ("y", "x"))
        assert fp1 == fp2

    def test_different_type_different_fingerprint(self):
        fp1 = _fingerprint("a", "f.py", ("x",))
        fp2 = _fingerprint("b", "f.py", ("x",))
        assert fp1 != fp2


# ── Registry integration ─────────────────────────────────────────


class TestRegistryIntegration:
    """JUDGMENT_DETECTORS derived from registry replaces hardcoded set."""

    def test_judgment_detectors_includes_cycles(self):
        assert "cycles" in JUDGMENT_DETECTORS

    def test_judgment_detectors_excludes_clearcut(self):
        for det in ("unused", "logs", "exports", "deprecated", "security",
                     "test_coverage", "stale_exclude"):
            assert det not in JUDGMENT_DETECTORS

    def test_judgment_detectors_includes_expected(self):
        expected = {
            "structural", "smells", "dupes", "boilerplate_duplication",
            "coupling", "cycles", "props", "react", "orphaned", "naming",
            "patterns", "facade", "single_use", "responsibility_cohesion",
            "signature", "dict_keys", "flat_dirs", "global_mutable_config",
            "private_imports", "layer_violation",
        }
        assert expected.issubset(JUDGMENT_DETECTORS)
