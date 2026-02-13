"""Tests for desloppify.commands.status — display helpers."""

import pytest

from desloppify.commands.status import (
    _show_dimension_table,
    _show_focus_suggestion,
    _show_structural_areas,
    cmd_status,
)


# ---------------------------------------------------------------------------
# Module-level sanity
# ---------------------------------------------------------------------------

class TestStatusModuleSanity:
    """Verify the module imports and has expected exports."""

    def test_cmd_status_callable(self):
        assert callable(cmd_status)

    def test_show_dimension_table_callable(self):
        assert callable(_show_dimension_table)

    def test_show_focus_suggestion_callable(self):
        assert callable(_show_focus_suggestion)

    def test_show_structural_areas_callable(self):
        assert callable(_show_structural_areas)


# ---------------------------------------------------------------------------
# _show_structural_areas
# ---------------------------------------------------------------------------

class TestShowStructuralAreas:
    """_show_structural_areas groups T3/T4 debt by area."""

    def _make_finding(self, fid, *, file, tier, status="open"):
        return {
            "id": fid, "file": file, "tier": tier, "status": status,
            "detector": "test", "confidence": "medium", "summary": "test",
        }

    def test_no_output_when_fewer_than_5_structural(self, capsys):
        """Should produce no output when structural findings < 5."""
        state = {"findings": {
            "f1": self._make_finding("f1", file="src/a/foo.ts", tier=3),
            "f2": self._make_finding("f2", file="src/b/bar.ts", tier=4),
        }}
        _show_structural_areas(state)
        assert capsys.readouterr().out == ""

    def test_no_output_when_single_area(self, capsys):
        """Needs at least 2 areas to be worth showing."""
        state = {"findings": {
            f"f{i}": self._make_finding(f"f{i}", file=f"src/area/{chr(97+i)}.ts", tier=3)
            for i in range(6)
        }}
        _show_structural_areas(state)
        # All files in same area "src/area" -> should not print
        assert capsys.readouterr().out == ""

    def test_output_when_multiple_areas(self, capsys):
        """Shows structural debt when 5+ findings across 2+ areas."""
        findings = {}
        for i in range(3):
            fid = f"a{i}"
            findings[fid] = self._make_finding(fid, file=f"src/alpha/{chr(97+i)}.ts", tier=3)
        for i in range(3):
            fid = f"b{i}"
            findings[fid] = self._make_finding(fid, file=f"src/beta/{chr(97+i)}.ts", tier=4)
        state = {"findings": findings}
        _show_structural_areas(state)
        out = capsys.readouterr().out
        assert "Structural Debt" in out

    def test_excludes_non_structural_tiers(self, capsys):
        """T1 and T2 findings should not be counted."""
        findings = {}
        for i in range(10):
            fid = f"f{i}"
            findings[fid] = self._make_finding(fid, file=f"src/a/{i}.ts", tier=1)
        state = {"findings": findings}
        _show_structural_areas(state)
        assert capsys.readouterr().out == ""

    def test_includes_wontfix_status(self, capsys):
        """wontfix findings should be counted as structural debt."""
        findings = {}
        for i in range(3):
            fid = f"a{i}"
            findings[fid] = self._make_finding(
                fid, file=f"src/alpha/{chr(97+i)}.ts", tier=3, status="wontfix")
        for i in range(3):
            fid = f"b{i}"
            findings[fid] = self._make_finding(
                fid, file=f"src/beta/{chr(97+i)}.ts", tier=4, status="open")
        state = {"findings": findings}
        _show_structural_areas(state)
        out = capsys.readouterr().out
        assert "Structural Debt" in out
