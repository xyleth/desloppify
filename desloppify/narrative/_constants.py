"""Shared constants for the narrative package.

Separate module to avoid import cycles — submodules import from here
instead of from __init__.py.
"""

from __future__ import annotations

from ..registry import detector_tools as _detector_tools

DETECTOR_TOOLS = _detector_tools()

# Structural sub-detectors that merge under "structural"
STRUCTURAL_MERGE = {"large", "complexity", "gods", "concerns"}

# Detector-level cascade: fixing one detector may auto-resolve findings in another.
_DETECTOR_CASCADE = {
    "logs": ["unused"],
    "smells": ["unused"],
}

_REMINDER_DECAY_THRESHOLD = 3  # Suppress after this many occurrences

_FEEDBACK_URL = "https://github.com/peteromalley/desloppify/issues"
