"""Tests for Go smell detectors.

Each test verifies that a specific smell detector fires on the synthetic
fixture files under desloppify/tests/fixtures/go/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from desloppify.languages.go.detectors.smells import detect_smells

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "go"


@pytest.fixture()
def smell_results():
    """Run smell detection on the Go fixtures directory."""
    entries, total_files = detect_smells(FIXTURES)
    return {e["id"]: e for e in entries}, total_files


def _has_smell(results: dict, smell_id: str) -> bool:
    return smell_id in results


def test_fixtures_exist():
    assert FIXTURES.exists(), f"Go fixture dir missing: {FIXTURES}"
    assert (FIXTURES / "smells.go").exists()


def test_nil_map_write(smell_results):
    results, _ = smell_results
    assert _has_smell(results, "nil_map_write")


def test_string_concat_loop(smell_results):
    results, _ = smell_results
    assert _has_smell(results, "string_concat_loop")


def test_yoda_condition(smell_results):
    results, _ = smell_results
    assert _has_smell(results, "yoda_condition")


def test_todo_fixme(smell_results):
    results, _ = smell_results
    assert _has_smell(results, "todo_fixme")


def test_dogsledding(smell_results):
    results, _ = smell_results
    assert _has_smell(results, "dogsledding")


def test_too_many_params(smell_results):
    results, _ = smell_results
    assert _has_smell(results, "too_many_params")


def test_panic_in_lib(smell_results):
    """panic() in non-main package should be flagged."""
    results, _ = smell_results
    assert _has_smell(results, "panic_in_lib")


def test_panic_not_flagged_in_main(smell_results):
    """panic() in package main should NOT be flagged."""
    results, _ = smell_results
    if "panic_in_lib" in results:
        matches = results["panic_in_lib"]["matches"]
        for m in matches:
            assert "smells.go" not in m["file"], "panic should not be flagged in package main"


def test_fire_and_forget_goroutine(smell_results):
    results, _ = smell_results
    assert _has_smell(results, "fire_and_forget_goroutine")


def test_time_tick_leak(smell_results):
    results, _ = smell_results
    assert _has_smell(results, "time_tick_leak")


def test_unbuffered_signal(smell_results):
    results, _ = smell_results
    assert _has_smell(results, "unbuffered_signal")


def test_single_case_select(smell_results):
    results, _ = smell_results
    assert _has_smell(results, "single_case_select")


def test_clean_file_no_smells(smell_results):
    """good.go should not trigger any smells."""
    results, _ = smell_results
    for entry in results.values():
        for m in entry["matches"]:
            assert "good.go" not in m["file"], (
                f"good.go triggered smell {entry['id']}: {m['content']}"
            )


def test_total_files_positive(smell_results):
    _, total_files = smell_results
    assert total_files > 0
