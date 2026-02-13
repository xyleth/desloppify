"""Canonical detector registry — single source of truth.

All detector metadata lives here. Other modules derive their views
(display order, CLI names, narrative tools, scoring validation) from this registry
instead of maintaining their own lists.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DetectorMeta:
    name: str
    display: str                    # Human-readable for terminal display
    dimension: str                  # Scoring dimension name
    action_type: str                # "auto_fix" | "refactor" | "reorganize" | "manual_fix"
    guidance: str                   # Narrative coaching text
    fixers: tuple[str, ...] = ()
    tool: str = ""                  # "move" or empty
    structural: bool = False        # Merges under "structural" in display


DETECTORS: dict[str, DetectorMeta] = {
    # ── Auto-fixable ──────────────────────────────────────
    "unused": DetectorMeta(
        "unused", "unused", "Import hygiene", "auto_fix",
        "remove unused imports and variables",
        fixers=("unused-imports", "unused-vars", "unused-params")),
    "logs": DetectorMeta(
        "logs", "logs", "Debug cleanliness", "auto_fix",
        "remove debug logs",
        fixers=("debug-logs",)),
    "exports": DetectorMeta(
        "exports", "exports", "API surface", "auto_fix",
        "remove dead exports",
        fixers=("dead-exports",)),
    "smells": DetectorMeta(
        "smells", "smells", "Code quality", "auto_fix",
        "fix code smells — dead useEffect, empty if chains",
        fixers=("dead-useeffect", "empty-if-chain")),
    # ── Reorganize (move tool) ────────────────────────────
    "orphaned": DetectorMeta(
        "orphaned", "orphaned", "Organization", "reorganize",
        "delete dead files or relocate with `desloppify move`",
        tool="move"),
    "flat_dirs": DetectorMeta(
        "flat_dirs", "flat dirs", "Organization", "reorganize",
        "create subdirectories and use `desloppify move`",
        tool="move"),
    "naming": DetectorMeta(
        "naming", "naming", "Organization", "reorganize",
        "rename files with `desloppify move` to fix conventions",
        tool="move"),
    "single_use": DetectorMeta(
        "single_use", "single_use", "Coupling", "reorganize",
        "inline or relocate with `desloppify move`",
        tool="move"),
    "coupling": DetectorMeta(
        "coupling", "coupling", "Coupling", "reorganize",
        "fix boundary violations with `desloppify move`",
        tool="move"),
    "cycles": DetectorMeta(
        "cycles", "cycles", "Dependency health", "reorganize",
        "break cycles by extracting shared code or using `desloppify move`",
        tool="move"),
    "facade": DetectorMeta(
        "facade", "facade", "Organization", "reorganize",
        "flatten re-export facades or consolidate barrel files",
        tool="move"),
    # ── Refactor ──────────────────────────────────────────
    "structural": DetectorMeta(
        "structural", "structural", "File health", "refactor",
        "decompose large files — extract logic into focused modules"),
    "props": DetectorMeta(
        "props", "props", "Component design", "refactor",
        "split bloated components, extract sub-components"),
    "react": DetectorMeta(
        "react", "react", "Code quality", "refactor",
        "refactor React antipatterns (state sync, provider nesting, hook bloat)"),
    "dupes": DetectorMeta(
        "dupes", "dupes", "Duplication", "refactor",
        "extract shared utility or consolidate duplicates"),
    "patterns": DetectorMeta(
        "patterns", "patterns", "Pattern consistency", "refactor",
        "align to single pattern across the codebase"),
    "dict_keys": DetectorMeta(
        "dict_keys", "dict keys", "Code quality", "refactor",
        "fix dict key mismatches — dead writes are likely dead code, "
        "schema drift suggests a typo or missed rename"),
    "test_coverage": DetectorMeta(
        "test_coverage", "test coverage", "Test health", "refactor",
        "add tests for untested production modules — prioritize by import count"),
    "signature": DetectorMeta(
        "signature", "signature", "Code quality", "refactor",
        "consolidate inconsistent function signatures"),
    "global_mutable_config": DetectorMeta(
        "global_mutable_config", "global mutable config", "Code quality", "manual_fix",
        "refactor module-level mutable state — use explicit init functions or dependency injection"),
    # ── Manual fix ────────────────────────────────────────
    "deprecated": DetectorMeta(
        "deprecated", "deprecated", "API surface", "manual_fix",
        "remove deprecated symbols or migrate callers"),
    "stale_exclude": DetectorMeta(
        "stale_exclude", "stale exclude", "Organization", "manual_fix",
        "remove stale exclusion or verify it's still needed"),
    "security": DetectorMeta(
        "security", "security", "Security", "manual_fix",
        "review and fix security findings — prioritize by severity"),
    # ── Subjective review ────────────────────────────────────
    "review": DetectorMeta(
        "review", "design review", "Design quality", "refactor",
        "address design quality findings from AI code review"),
    "subjective_review": DetectorMeta(
        "subjective_review", "subjective review", "Design quality", "manual_fix",
        "run `desloppify fix review` to evaluate files against quality dimensions"),
}

# ── Canonical display order for terminal output ──────────────

_DISPLAY_ORDER = [
    "logs", "unused", "exports", "deprecated", "structural", "props",
    "single_use", "coupling", "cycles", "orphaned", "facade", "patterns",
    "naming", "smells", "react", "dupes", "stale_exclude",
    "dict_keys", "flat_dirs", "signature", "global_mutable_config",
    "test_coverage", "security", "review", "subjective_review",
]


def detector_names() -> list[str]:
    """All registered detector names, sorted."""
    return sorted(DETECTORS.keys())


def display_order() -> list[str]:
    """Canonical display order for terminal output."""
    return list(_DISPLAY_ORDER)


def detector_tools() -> dict[str, dict]:
    """DETECTOR_TOOLS-shaped dict for narrative.py backward compat."""
    result = {}
    for name, d in DETECTORS.items():
        entry: dict = {
            "fixers": list(d.fixers),
            "action_type": d.action_type,
        }
        if d.tool:
            entry["tool"] = d.tool
        if d.guidance:
            entry["guidance"] = d.guidance
        result[name] = entry
    return result
