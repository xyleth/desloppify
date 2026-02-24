"""Tests for Go security detectors.

Each test verifies that a specific security detector fires on the synthetic
fixture files under desloppify/tests/fixtures/go/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from desloppify.languages.go.detectors.security import detect_go_security
from desloppify.languages.go.extractors import find_go_files

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "go"


@pytest.fixture()
def security_results():
    """Run security detection on the Go fixtures directory."""
    files = find_go_files(FIXTURES)
    entries, scanned = detect_go_security(files, zone_map=None)
    return entries, scanned


def _has_check(entries: list[dict], check_id: str) -> bool:
    return any(check_id in e.get("name", "") for e in entries)


def test_fixtures_exist():
    assert (FIXTURES / "security.go").exists()


def test_sql_injection(security_results):
    entries, _ = security_results
    assert _has_check(entries, "sql_injection")


def test_command_injection(security_results):
    entries, _ = security_results
    assert _has_check(entries, "command_injection")


def test_clean_file_no_security_issues(security_results):
    """good.go should not trigger any security findings."""
    entries, _ = security_results
    for e in entries:
        assert "good.go" not in e.get("file", ""), (
            f"good.go triggered security check: {e.get('name')}"
        )


def test_scanned_files_positive(security_results):
    _, scanned = security_results
    assert scanned > 0
