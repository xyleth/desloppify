"""Computed narrative context for LLM coaching and terminal headlines.

Pure functions that derive structured observations from state data.
No print statements — returns dicts that flow into _write_query().
"""

from __future__ import annotations

# ── Shared constants (from _constants to avoid import cycles) ──────

from ._constants import (  # noqa: F401
    DETECTOR_TOOLS,
    STRUCTURAL_MERGE,
    _DETECTOR_CASCADE,
    _REMINDER_DECAY_THRESHOLD,
    _FEEDBACK_URL,
)


# ── Re-exports (submodule imports) ──

from .core import (  # noqa: E402
    compute_narrative,
    _count_open_by_detector,
    _compute_badge_status,
)
from .phase import _detect_phase, _detect_milestone  # noqa: E402
from .dimensions import _analyze_dimensions, _finding_in_dimension, _analyze_debt  # noqa: E402
from .actions import _compute_actions, _compute_tools  # noqa: E402
from .headline import _compute_headline  # noqa: E402
from .reminders import _compute_reminders, _compute_fp_rates  # noqa: E402
from .strategy import (  # noqa: E402
    _open_files_by_detector,
    _compute_fixer_leverage,
    _compute_lanes,
    _group_by_file_overlap,
    _compute_strategy_hint,
    _compute_strategy,
)

__all__ = [
    # Public API
    "compute_narrative",
    "STRUCTURAL_MERGE",
    "DETECTOR_TOOLS",
    # Re-exports for backward compatibility (tests + internal consumers)
    "_count_open_by_detector",
    "_compute_badge_status",
    "_detect_phase",
    "_detect_milestone",
    "_analyze_dimensions",
    "_finding_in_dimension",
    "_analyze_debt",
    "_compute_actions",
    "_compute_tools",
    "_compute_headline",
    "_compute_reminders",
    "_compute_fp_rates",
    "_open_files_by_detector",
    "_compute_fixer_leverage",
    "_compute_lanes",
    "_group_by_file_overlap",
    "_compute_strategy_hint",
    "_compute_strategy",
    "_FEEDBACK_URL",
]
