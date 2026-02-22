"""Tests for external tool adapters: Knip, ruff smells, and bandit.

Each adapter must:
  1. Return None (not crash) when the tool is not installed.
  2. Correctly parse the tool's JSON output format.
  3. Produce entries/findings in the structure the phase runners expect.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch


# ── Knip adapter ────────────────────────────────────────────────────────────


from desloppify.languages.typescript.detectors.knip_adapter import detect_with_knip


class TestKnipAdapter:
    def _run_detect(self, stdout: str):
        """Patch subprocess.run to return a synthetic Knip result."""
        mock_result = MagicMock()
        mock_result.stdout = stdout
        with patch("subprocess.run", return_value=mock_result):
            return detect_with_knip(Path("/fake/project"))

    def test_returns_none_when_knip_not_installed(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("npx not found")):
            assert detect_with_knip(Path("/fake/project")) is None

    def test_returns_none_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("npx", 120)):
            assert detect_with_knip(Path("/fake/project")) is None

    def test_returns_none_on_empty_output(self):
        assert self._run_detect(stdout="") is None

    def test_returns_none_on_invalid_json(self):
        assert self._run_detect(stdout="not-json") is None

    def test_empty_knip_output_returns_empty_list(self):
        result = self._run_detect(stdout=json.dumps({"issues": []}))
        assert result == []

    def test_parses_dead_exports(self, tmp_path):
        f = tmp_path / "utils.ts"
        f.write_text("export function unused() {}")
        payload = json.dumps(
            {
                "issues": [
                    {
                        "file": str(f),
                        "exports": [
                            {"name": "unused", "pos": {"start": {"line": 1, "col": 0}}}
                        ],
                    }
                ]
            }
        )
        mock_result = MagicMock()
        mock_result.stdout = payload
        with patch("subprocess.run", return_value=mock_result):
            result = detect_with_knip(tmp_path)
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "unused"
        assert result[0]["kind"] == "export"
        assert result[0]["line"] == 1

    def test_parses_dead_type_exports(self, tmp_path):
        f = tmp_path / "types.ts"
        f.write_text("export type MyType = string;")
        payload = json.dumps(
            {
                "issues": [
                    {
                        "file": str(f),
                        "types": [{"name": "MyType", "pos": {"start": {"line": 2, "col": 0}}}],
                    }
                ]
            }
        )
        mock_result = MagicMock()
        mock_result.stdout = payload
        with patch("subprocess.run", return_value=mock_result):
            result = detect_with_knip(tmp_path)
        assert result is not None
        assert any(e["kind"] == "type" and e["name"] == "MyType" for e in result)

    def test_skips_files_outside_scan_path(self, tmp_path):
        payload = json.dumps(
            {
                "issues": [
                    {
                        "file": "/other/path/file.ts",
                        "exports": [{"name": "gone", "pos": {"start": {"line": 1, "col": 0}}}],
                    }
                ]
            }
        )
        mock_result = MagicMock()
        mock_result.stdout = payload
        with patch("subprocess.run", return_value=mock_result):
            result = detect_with_knip(tmp_path)
        assert result == []


# ── Ruff smells adapter ──────────────────────────────────────────────────────


from desloppify.languages.python.detectors.ruff_smells import detect_with_ruff_smells


class TestRuffSmellsAdapter:
    def _run_detect(self, stdout: str):
        mock_result = MagicMock()
        mock_result.stdout = stdout

        with patch("subprocess.run", return_value=mock_result):
            return detect_with_ruff_smells(Path("/fake/project"))

    def test_returns_none_when_ruff_not_installed(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("ruff not found")):
            assert detect_with_ruff_smells(Path("/fake/project")) is None

    def test_returns_none_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ruff", 60)):
            assert detect_with_ruff_smells(Path("/fake/project")) is None

    def test_returns_empty_on_no_diagnostics(self):
        result = self._run_detect(stdout="[]")
        assert result == []

    def test_returns_empty_on_empty_output(self):
        result = self._run_detect(stdout="")
        assert result == []

    def test_returns_none_on_invalid_json(self):
        result = self._run_detect(stdout="not-json")
        assert result is None

    def test_parses_b007_unused_loop_var(self):
        diagnostics = [
            {
                "code": "B007",
                "filename": "/project/util.py",
                "message": "Loop control variable `i` not used in loop body",
                "location": {"row": 10, "column": 4},
            }
        ]
        result = self._run_detect(stdout=json.dumps(diagnostics))
        assert result is not None
        assert len(result) == 1
        entry = result[0]
        assert entry["id"] == "unused_loop_var"
        assert entry["severity"] == "medium"
        assert len(entry["matches"]) == 1
        assert entry["matches"][0]["line"] == 10

    def test_parses_e711_none_comparison(self):
        diagnostics = [
            {
                "code": "E711",
                "filename": "/project/utils.py",
                "message": "Comparison to `None` (use `is`)",
                "location": {"row": 5, "column": 8},
            }
        ]
        result = self._run_detect(stdout=json.dumps(diagnostics))
        assert result is not None
        assert any(e["id"] == "none_comparison" for e in result)

    def test_parses_w605_invalid_escape(self):
        diagnostics = [
            {
                "code": "W605",
                "filename": "/project/parse.py",
                "message": r"Invalid escape sequence: `\d`",
                "location": {"row": 3, "column": 0},
            }
        ]
        result = self._run_detect(stdout=json.dumps(diagnostics))
        assert result is not None
        assert any(e["id"] == "invalid_escape" for e in result)

    def test_groups_multiple_matches_by_code(self):
        diagnostics = [
            {
                "code": "B907",  # unknown — should be skipped
                "filename": "/project/x.py",
                "message": "unknown",
                "location": {"row": 1, "column": 0},
            },
            {
                "code": "E711",
                "filename": "/project/a.py",
                "message": "None comparison",
                "location": {"row": 3, "column": 0},
            },
            {
                "code": "E711",
                "filename": "/project/b.py",
                "message": "None comparison",
                "location": {"row": 7, "column": 0},
            },
        ]
        result = self._run_detect(stdout=json.dumps(diagnostics))
        assert result is not None
        none_entries = [e for e in result if e["id"] == "none_comparison"]
        assert len(none_entries) == 1  # grouped under one code
        assert len(none_entries[0]["matches"]) == 2

    def test_unknown_codes_are_skipped(self):
        diagnostics = [
            {
                "code": "Z999",
                "filename": "/project/x.py",
                "message": "unknown rule",
                "location": {"row": 1, "column": 0},
            }
        ]
        result = self._run_detect(stdout=json.dumps(diagnostics))
        assert result == []

    def test_smell_entry_has_required_fields(self):
        diagnostics = [
            {
                "code": "B904",
                "filename": "/project/ex.py",
                "message": "Use `raise from` in except clause",
                "location": {"row": 20, "column": 8},
            }
        ]
        result = self._run_detect(stdout=json.dumps(diagnostics))
        assert result is not None and len(result) == 1
        entry = result[0]
        assert "id" in entry
        assert "label" in entry
        assert "severity" in entry
        assert "matches" in entry
        assert isinstance(entry["matches"], list)


# ── Bandit adapter ───────────────────────────────────────────────────────────


from desloppify.languages.python.detectors.bandit_adapter import (
    _to_security_entry,
    detect_with_bandit,
)


class TestBanditAdapter:
    def _bandit_result(self, results: list[dict], metrics: dict | None = None) -> str:
        return json.dumps({"results": results, "errors": [], "metrics": metrics or {}})

    def _run_detect(self, stdout: str, tmp_path=None):
        mock_result = MagicMock()
        mock_result.stdout = stdout
        path = tmp_path or Path("/fake/project")

        with patch("subprocess.run", return_value=mock_result):
            return detect_with_bandit(path, zone_map=None)

    def test_returns_none_when_bandit_not_installed(self, tmp_path):
        with patch("subprocess.run", side_effect=FileNotFoundError("bandit not found")):
            assert detect_with_bandit(tmp_path, zone_map=None) is None

    def test_returns_none_on_timeout(self, tmp_path):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("bandit", 120)):
            assert detect_with_bandit(tmp_path, zone_map=None) is None

    def test_returns_empty_on_no_findings(self):
        result = self._run_detect(stdout=self._bandit_result([]))
        assert result is not None
        entries, files_scanned = result
        assert entries == []

    def test_returns_empty_on_empty_stdout(self):
        result = self._run_detect(stdout="")
        assert result is not None
        entries, _ = result
        assert entries == []

    def test_returns_none_on_invalid_json(self):
        mock_result = MagicMock()
        mock_result.stdout = "not-json"
        with patch("subprocess.run", return_value=mock_result):
            result = detect_with_bandit(Path("/fake"), zone_map=None)
        assert result is None

    def test_parses_high_severity_finding(self):
        raw = [
            {
                "filename": "/project/app.py",
                "issue_severity": "HIGH",
                "issue_confidence": "HIGH",
                "issue_text": "Use of exec detected.",
                "line_number": 42,
                "test_id": "B102",
                "test_name": "exec_used",
                "code": "exec(user_input)",
                "more_info": "https://bandit.readthedocs.io",
            }
        ]
        result = self._run_detect(stdout=self._bandit_result(raw))
        assert result is not None
        entries, _ = result
        assert len(entries) == 1
        e = entries[0]
        assert e["confidence"] == "high"
        assert e["tier"] == 4
        assert "B102" in e["summary"]
        assert e["detail"]["kind"] == "B102"
        assert e["detail"]["source"] == "bandit"

    def test_parses_medium_severity_finding(self):
        raw = [
            {
                "filename": "/project/api.py",
                "issue_severity": "MEDIUM",
                "issue_confidence": "HIGH",
                "issue_text": "Consider possible security implications.",
                "line_number": 10,
                "test_id": "B608",
                "test_name": "hardcoded_sql_expressions",
                "code": "query = 'SELECT * FROM users WHERE id=' + uid",
                "more_info": "",
            }
        ]
        result = self._run_detect(stdout=self._bandit_result(raw))
        assert result is not None
        entries, _ = result
        assert len(entries) == 1
        assert entries[0]["confidence"] == "medium"
        assert entries[0]["tier"] == 3

    def test_suppresses_low_severity_low_confidence(self):
        raw = [
            {
                "filename": "/project/utils.py",
                "issue_severity": "LOW",
                "issue_confidence": "LOW",
                "issue_text": "Very noisy low-signal finding.",
                "line_number": 5,
                "test_id": "B999",
                "test_name": "fake_low_rule",
                "code": "x = 1",
                "more_info": "",
            }
        ]
        result = self._run_detect(stdout=self._bandit_result(raw))
        assert result is not None
        entries, _ = result
        assert entries == []

    def test_skips_cross_lang_overlap_ids(self):
        """B105 (hardcoded_password_string) overlaps with cross-lang detector — skip it."""
        raw = [
            {
                "filename": "/project/config.py",
                "issue_severity": "HIGH",
                "issue_confidence": "HIGH",
                "issue_text": "Possible hardcoded password.",
                "line_number": 3,
                "test_id": "B105",
                "test_name": "hardcoded_password_string",
                "code": 'password = "abc123"',
                "more_info": "",
            }
        ]
        result = self._run_detect(stdout=self._bandit_result(raw))
        assert result is not None
        entries, _ = result
        assert entries == []

    def test_finding_name_is_stable_and_unique(self):
        raw = [
            {
                "filename": "/project/app.py",
                "issue_severity": "HIGH",
                "issue_confidence": "HIGH",
                "issue_text": "exec() usage",
                "line_number": 10,
                "test_id": "B102",
                "test_name": "exec_used",
                "code": "exec(x)",
                "more_info": "",
            }
        ]
        result = self._run_detect(stdout=self._bandit_result(raw))
        entries, _ = result
        assert "B102" in entries[0]["name"]
        assert "10" in entries[0]["name"]

    def test_to_security_entry_returns_none_for_empty_filename(self):
        result = _to_security_entry({"filename": "", "test_id": "B102"}, zone_map=None)
        assert result is None

    def test_counts_files_scanned_from_metrics(self):
        metrics = {
            "/project/a.py": {"loc": 10},
            "/project/b.py": {"loc": 20},
            "_totals": {"loc": 30},
        }
        stdout = self._bandit_result([], metrics=metrics)
        result = self._run_detect(stdout=stdout)
        assert result is not None
        _, files_scanned = result
        # _totals should be excluded; 2 actual files
        assert files_scanned == 2


# ── jscpd adapter ────────────────────────────────────────────────────────────


from desloppify.engine.detectors.jscpd_adapter import _parse_jscpd_report, detect_with_jscpd


class TestJscpdAdapter:
    def test_returns_none_when_jscpd_not_installed(self, tmp_path):
        with patch("subprocess.run", side_effect=FileNotFoundError("npx not found")):
            assert detect_with_jscpd(tmp_path) is None

    def test_returns_none_on_timeout(self, tmp_path):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("npx", 120)):
            assert detect_with_jscpd(tmp_path) is None

    def test_returns_empty_on_no_duplicates(self, tmp_path):
        result = _parse_jscpd_report({"duplicates": []}, tmp_path)
        assert result == []

    def test_returns_none_on_invalid_json_file(self, tmp_path):
        bad_report = tmp_path / "jscpd-report.json"
        bad_report.write_text("not-json")
        with patch("subprocess.run"), patch("tempfile.TemporaryDirectory") as mock_td:
            mock_td.return_value.__enter__.return_value = str(tmp_path)
            mock_td.return_value.__exit__.return_value = None
            result = detect_with_jscpd(tmp_path)
        assert result is None

    def test_clusters_pairs_with_same_fragment_hash(self, tmp_path):
        f1 = str(tmp_path / "a.py")
        f2 = str(tmp_path / "b.py")
        f3 = str(tmp_path / "c.py")
        fragment = "def foo():\n    pass\n    return None\n    # end"
        report = {
            "duplicates": [
                {
                    "fragment": fragment,
                    "lines": 4,
                    "firstFile": {"name": f1, "start": 1},
                    "secondFile": {"name": f2, "start": 5},
                },
                {
                    "fragment": fragment,
                    "lines": 4,
                    "firstFile": {"name": f2, "start": 5},
                    "secondFile": {"name": f3, "start": 10},
                },
            ]
        }
        result = _parse_jscpd_report(report, tmp_path)
        assert len(result) == 1  # Clustered into one entry
        assert result[0]["distinct_files"] == 3

    def test_distinct_files_counted_correctly(self, tmp_path):
        f1 = str(tmp_path / "a.py")
        f2 = str(tmp_path / "b.py")
        fragment = "x = 1\ny = 2\nz = 3\nw = 4"
        report = {
            "duplicates": [
                {
                    "fragment": fragment,
                    "lines": 4,
                    "firstFile": {"name": f1, "start": 1},
                    "secondFile": {"name": f2, "start": 10},
                }
            ]
        }
        result = _parse_jscpd_report(report, tmp_path)
        assert len(result) == 1
        assert result[0]["distinct_files"] == 2

    def test_skips_files_outside_scan_path(self, tmp_path):
        f_in = str(tmp_path / "a.py")
        f_out = "/other/path/b.py"
        fragment = "x = 1\ny = 2\nz = 3\nw = 4"
        report = {
            "duplicates": [
                {
                    "fragment": fragment,
                    "lines": 4,
                    "firstFile": {"name": f_in, "start": 1},
                    "secondFile": {"name": f_out, "start": 5},
                }
            ]
        }
        result = _parse_jscpd_report(report, tmp_path)
        assert result == []

    def test_sample_extracted_from_fragment(self, tmp_path):
        f1 = str(tmp_path / "a.py")
        f2 = str(tmp_path / "b.py")
        fragment = "line1\nline2\nline3\nline4\nline5\nline6"
        report = {
            "duplicates": [
                {
                    "fragment": fragment,
                    "lines": 6,
                    "firstFile": {"name": f1, "start": 1},
                    "secondFile": {"name": f2, "start": 10},
                }
            ]
        }
        result = _parse_jscpd_report(report, tmp_path)
        assert result[0]["sample"] == ["line1", "line2", "line3", "line4"]


# ── Extended ruff smells adapter ─────────────────────────────────────────────


class TestRuffSmellsAdapterExtended:
    """Tests for the 7 new ruff rules added in Migration 2."""

    def _run_detect(self, stdout: str):
        mock_result = MagicMock()
        mock_result.stdout = stdout
        with patch("subprocess.run", return_value=mock_result):
            return detect_with_ruff_smells(Path("/fake/project"))

    def test_parses_e722_bare_except(self):
        diagnostics = [
            {
                "code": "E722",
                "filename": "/p/a.py",
                "message": "Do not use bare 'except'",
                "location": {"row": 5, "column": 0},
            }
        ]
        result = self._run_detect(json.dumps(diagnostics))
        assert result is not None
        assert any(e["id"] == "bare_except" for e in result)

    def test_parses_ble001_broad_except(self):
        diagnostics = [
            {
                "code": "BLE001",
                "filename": "/p/a.py",
                "message": "Do not catch blind exception: `Exception`",
                "location": {"row": 8, "column": 4},
            }
        ]
        result = self._run_detect(json.dumps(diagnostics))
        assert result is not None
        assert any(e["id"] == "broad_except" for e in result)

    def test_parses_b006_mutable_default(self):
        diagnostics = [
            {
                "code": "B006",
                "filename": "/p/a.py",
                "message": "Do not use mutable data structures for argument defaults",
                "location": {"row": 3, "column": 0},
            }
        ]
        result = self._run_detect(json.dumps(diagnostics))
        assert result is not None
        assert any(e["id"] == "mutable_default" for e in result)

    def test_parses_ruf012_mutable_class_var(self):
        diagnostics = [
            {
                "code": "RUF012",
                "filename": "/p/a.py",
                "message": "Mutable class attributes should be annotated with `typing.ClassVar`",
                "location": {"row": 10, "column": 4},
            }
        ]
        result = self._run_detect(json.dumps(diagnostics))
        assert result is not None
        assert any(e["id"] == "mutable_class_var" for e in result)

    def test_parses_plw0603_global_keyword(self):
        diagnostics = [
            {
                "code": "PLW0603",
                "filename": "/p/a.py",
                "message": "Using the global statement to update `x`",
                "location": {"row": 7, "column": 4},
            }
        ]
        result = self._run_detect(json.dumps(diagnostics))
        assert result is not None
        assert any(e["id"] == "global_keyword" for e in result)

    def test_parses_f403_star_import(self):
        diagnostics = [
            {
                "code": "F403",
                "filename": "/p/a.py",
                "message": "`from foo import *` used; unable to detect undefined names",
                "location": {"row": 1, "column": 0},
            }
        ]
        result = self._run_detect(json.dumps(diagnostics))
        assert result is not None
        assert any(e["id"] == "star_import" for e in result)


# ── import-linter adapter ────────────────────────────────────────────────────


from desloppify.languages.python.detectors.import_linter_adapter import (
    detect_with_import_linter,
)


class TestImportLinterAdapter:
    def _write_config(self, tmp_path):
        (tmp_path / ".importlinter").write_text("[importlinter]\nroot_package=foo\n")

    def test_returns_none_when_lint_imports_not_installed(self, tmp_path):
        self._write_config(tmp_path)
        with patch("subprocess.run", side_effect=FileNotFoundError("lint-imports not found")):
            assert detect_with_import_linter(tmp_path) is None

    def test_returns_none_when_no_importlinter_config(self, tmp_path):
        # No .importlinter file anywhere in the path hierarchy (tmp_path has no .git)
        result = detect_with_import_linter(tmp_path)
        assert result is None

    def test_returns_empty_on_no_violations(self, tmp_path):
        self._write_config(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "All contracts ok.\n"
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            result = detect_with_import_linter(tmp_path)
        assert result == []

    def test_parses_single_violation(self, tmp_path):
        self._write_config(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = (
            "Broken contract 'Engine cannot import Languages':\n"
            "    foo.engine.detectors.coupling imports foo.languages.typescript\n"
        )
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            result = detect_with_import_linter(tmp_path)
        assert result is not None
        assert len(result) == 1
        assert result[0]["confidence"] == "high"
        assert "foo.engine.detectors.coupling" in result[0]["summary"]
        assert "foo.languages.typescript" in result[0]["summary"]

    def test_parses_multiple_violations(self, tmp_path):
        self._write_config(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = (
            "Broken contract 'Engine cannot import Languages':\n"
            "    foo.engine.a imports foo.languages.b\n"
            "    foo.engine.c imports foo.languages.d\n"
        )
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            result = detect_with_import_linter(tmp_path)
        assert result is not None
        assert len(result) == 2
        assert result[0]["source_pkg"] == "a"
        assert result[1]["source_pkg"] == "c"

    def test_returns_none_on_timeout(self, tmp_path):
        self._write_config(tmp_path)
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("lint-imports", 60)
        ):
            assert detect_with_import_linter(tmp_path) is None
