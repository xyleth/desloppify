"""Tests for desloppify.commands.fix_cmd — fix command helpers."""

import inspect

import pytest

from desloppify.commands.fix_cmd import (
    _ResultsWithMeta,
    _resolve_fixer_results,
    _print_fix_summary,
    _print_fix_retro,
    _wrap_unused_vars_fix,
    _wrap_debug_logs_fix,
    _SKIP_REASON_LABELS,
    cmd_fix,
)


# ---------------------------------------------------------------------------
# Module-level sanity
# ---------------------------------------------------------------------------

class TestFixModuleSanity:
    """Verify the module imports and has expected exports."""

    def test_cmd_fix_callable(self):
        assert callable(cmd_fix)

    def test_results_with_meta_is_list(self):
        assert issubclass(_ResultsWithMeta, list)

    def test_skip_reason_labels_is_dict(self):
        assert isinstance(_SKIP_REASON_LABELS, dict)
        assert len(_SKIP_REASON_LABELS) > 0


# ---------------------------------------------------------------------------
# _ResultsWithMeta
# ---------------------------------------------------------------------------

class TestResultsWithMeta:
    """_ResultsWithMeta is a list with a skip_reasons dict attribute."""

    def test_empty_init(self):
        r = _ResultsWithMeta()
        assert len(r) == 0
        assert r.skip_reasons == {}

    def test_init_with_data(self):
        r = _ResultsWithMeta([1, 2, 3])
        assert len(r) == 3
        assert list(r) == [1, 2, 3]
        assert r.skip_reasons == {}

    def test_skip_reasons_independent(self):
        """Each instance should have its own skip_reasons dict (not shared)."""
        r1 = _ResultsWithMeta()
        r2 = _ResultsWithMeta()
        r1.skip_reasons["test"] = 5
        assert r2.skip_reasons == {}

    def test_behaves_as_list(self):
        r = _ResultsWithMeta([{"file": "a.ts", "removed": ["x"]}])
        r.append({"file": "b.ts", "removed": ["y"]})
        assert len(r) == 2
        assert r[1]["file"] == "b.ts"

    def test_skip_reasons_assignable(self):
        r = _ResultsWithMeta()
        r.skip_reasons = {"rest_element": 3, "function_param": 2}
        assert r.skip_reasons["rest_element"] == 3


# ---------------------------------------------------------------------------
# _resolve_fixer_results
# ---------------------------------------------------------------------------

class TestResolveFixerResults:
    """_resolve_fixer_results marks matching findings as fixed."""

    def _make_state_with_findings(self, *findings):
        state = {"findings": {}}
        for fid, status in findings:
            state["findings"][fid] = {
                "id": fid, "status": status, "detector": "unused",
                "file": "a.ts", "tier": 2, "confidence": "high",
                "summary": "test", "note": None,
            }
        return state

    def test_resolves_matching_open_findings(self, monkeypatch):
        from desloppify.commands import fix_cmd
        monkeypatch.setattr(fix_cmd, "rel", lambda p: p)

        state = self._make_state_with_findings(
            ("unused::a.ts::foo", "open"),
            ("unused::a.ts::bar", "open"),
        )
        results = [{"file": "a.ts", "removed": ["foo"]}]
        resolved = _resolve_fixer_results(state, results, "unused", "unused-imports")
        assert resolved == ["unused::a.ts::foo"]
        assert state["findings"]["unused::a.ts::foo"]["status"] == "fixed"
        assert state["findings"]["unused::a.ts::bar"]["status"] == "open"

    def test_skips_already_fixed(self, monkeypatch):
        from desloppify.commands import fix_cmd
        monkeypatch.setattr(fix_cmd, "rel", lambda p: p)

        state = self._make_state_with_findings(
            ("unused::a.ts::foo", "fixed"),
        )
        results = [{"file": "a.ts", "removed": ["foo"]}]
        resolved = _resolve_fixer_results(state, results, "unused", "unused-imports")
        assert resolved == []

    def test_skips_nonexistent_findings(self, monkeypatch):
        from desloppify.commands import fix_cmd
        monkeypatch.setattr(fix_cmd, "rel", lambda p: p)

        state = self._make_state_with_findings()
        results = [{"file": "a.ts", "removed": ["ghost"]}]
        resolved = _resolve_fixer_results(state, results, "unused", "unused-imports")
        assert resolved == []

    def test_adds_auto_fix_note(self, monkeypatch):
        from desloppify.commands import fix_cmd
        monkeypatch.setattr(fix_cmd, "rel", lambda p: p)

        state = self._make_state_with_findings(("unused::a.ts::foo", "open"))
        results = [{"file": "a.ts", "removed": ["foo"]}]
        _resolve_fixer_results(state, results, "unused", "unused-imports")
        note = state["findings"]["unused::a.ts::foo"]["note"]
        assert "auto-fixed" in note
        assert "unused-imports" in note

    def test_multiple_files(self, monkeypatch):
        from desloppify.commands import fix_cmd
        monkeypatch.setattr(fix_cmd, "rel", lambda p: p)

        state = self._make_state_with_findings(
            ("unused::a.ts::foo", "open"),
            ("unused::b.ts::bar", "open"),
        )
        state["findings"]["unused::b.ts::bar"]["file"] = "b.ts"

        results = [
            {"file": "a.ts", "removed": ["foo"]},
            {"file": "b.ts", "removed": ["bar"]},
        ]
        resolved = _resolve_fixer_results(state, results, "unused", "unused-imports")
        assert len(resolved) == 2


# ---------------------------------------------------------------------------
# _wrap_unused_vars_fix
# ---------------------------------------------------------------------------

class TestWrapUnusedVarsFix:
    """_wrap_unused_vars_fix wraps a fix function to return _ResultsWithMeta."""

    def test_wraps_results_and_skip_reasons(self):
        def fake_fix(entries, *, dry_run=False):
            results = [{"file": "a.ts", "removed": ["x"]}]
            skip_reasons = {"rest_element": 2}
            return results, skip_reasons

        wrapped = _wrap_unused_vars_fix(fake_fix)
        result = wrapped([{"name": "x"}], dry_run=True)
        assert isinstance(result, _ResultsWithMeta)
        assert len(result) == 1
        assert result.skip_reasons == {"rest_element": 2}


# ---------------------------------------------------------------------------
# _wrap_debug_logs_fix
# ---------------------------------------------------------------------------

class TestWrapDebugLogsFix:
    """_wrap_debug_logs_fix normalises 'tags' field to 'removed'."""

    def test_normalises_tags_to_removed(self):
        def fake_fix(entries, *, dry_run=False):
            return [{"file": "a.ts", "tags": ["DEBUG", "TODO"]}]

        wrapped = _wrap_debug_logs_fix(fake_fix)
        result = wrapped([{"name": "x"}], dry_run=False)
        assert result[0]["removed"] == ["DEBUG", "TODO"]

    def test_preserves_existing_removed(self):
        def fake_fix(entries, *, dry_run=False):
            return [{"file": "a.ts", "removed": ["foo"]}]

        wrapped = _wrap_debug_logs_fix(fake_fix)
        result = wrapped([{"name": "x"}], dry_run=False)
        assert result[0]["removed"] == ["foo"]


# ---------------------------------------------------------------------------
# _print_fix_summary
# ---------------------------------------------------------------------------

class TestPrintFixSummary:
    """_print_fix_summary prints per-file summary table."""

    def test_basic_output(self, monkeypatch, capsys):
        from desloppify.commands import fix_cmd
        monkeypatch.setattr(fix_cmd, "rel", lambda p: p)

        fixer = {"label": "unused imports", "verb": "Removed", "dry_verb": "Would remove"}
        results = [{"file": "a.ts", "removed": ["foo", "bar"], "lines_removed": 5}]
        _print_fix_summary(fixer, results, 2, 5, dry_run=False)
        out = capsys.readouterr().out
        assert "Removed 2" in out
        assert "unused imports" in out
        assert "5 lines" in out

    def test_dry_run_uses_dry_verb(self, monkeypatch, capsys):
        from desloppify.commands import fix_cmd
        monkeypatch.setattr(fix_cmd, "rel", lambda p: p)

        fixer = {"label": "unused imports", "verb": "Removed", "dry_verb": "Would remove"}
        results = [{"file": "a.ts", "removed": ["foo"]}]
        _print_fix_summary(fixer, results, 1, 0, dry_run=True)
        out = capsys.readouterr().out
        assert "Would remove" in out


# ---------------------------------------------------------------------------
# _print_fix_retro
# ---------------------------------------------------------------------------

class TestPrintFixRetro:
    """_print_fix_retro prints post-fix reflection."""

    def test_basic_retro(self, capsys):
        _print_fix_retro("unused-imports", 10, 8, 6)
        out = capsys.readouterr().out
        assert "Fixed 8/10" in out
        assert "2 skipped" in out
        assert "6 findings resolved" in out
        assert "Checklist:" in out

    def test_retro_with_skip_reasons(self, capsys):
        _print_fix_retro("unused-vars", 10, 7, 5,
                         skip_reasons={"rest_element": 2, "function_param": 1})
        out = capsys.readouterr().out
        assert "Skip reasons" in out
        assert "rest" in out.lower()

    def test_no_skip_reasons_with_skipped(self, capsys):
        _print_fix_retro("unused-imports", 10, 7, 5, skip_reasons=None)
        out = capsys.readouterr().out
        assert "skipped" in out.lower()
        assert "fixer" in out.lower()  # suggestion about improving fixer
