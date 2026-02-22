"""Shared subjective-integrity utilities used across commands and scoring."""

from __future__ import annotations

from desloppify.engine._scoring.policy.core import (
    SUBJECTIVE_TARGET_MATCH_TOLERANCE,
    matches_target_score,
)

__all__ = [
    "SUBJECTIVE_TARGET_MATCH_TOLERANCE",
    "matches_target_score",
]
