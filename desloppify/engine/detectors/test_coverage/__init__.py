"""Test coverage detector package."""

from .detector import detect_test_coverage
from .heuristics import _has_testable_logic  # noqa: F401 (re-export for tests)
from .metrics import _file_loc  # noqa: F401 (re-export for tests)

__all__ = ["detect_test_coverage"]
