"""Concern generators — mechanical findings → subjective review bridge.

Concerns are ephemeral: computed on-demand from current state, never persisted.
Only LLM-confirmed concerns become persistent Finding objects via review import.

Generators focus on cross-cutting synthesis — bundling all signals per file so
the LLM gets a complete picture, and surfacing systemic patterns across files
that no single detector captures.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass

from desloppify.core.registry import JUDGMENT_DETECTORS


@dataclass(frozen=True)
class Concern:
    """A potential design problem surfaced by mechanical signals."""

    type: str  # concern classification
    file: str  # primary file (relative path)
    summary: str  # human-readable 1-liner
    evidence: tuple[str, ...]  # supporting data points
    question: str  # specific question for LLM to evaluate
    fingerprint: str  # stable hash for dismissal tracking
    source_findings: tuple[str, ...]  # finding IDs that triggered this


def _fingerprint(concern_type: str, file: str, key_signals: tuple[str, ...]) -> str:
    """Stable hash of (type, file, sorted key signals)."""
    raw = f"{concern_type}::{file}::{','.join(sorted(key_signals))}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _is_dismissed(
    dismissals: dict, fingerprint: str, source_finding_ids: tuple[str, ...]
) -> bool:
    """Check if a concern was previously dismissed and source findings unchanged."""
    entry = dismissals.get(fingerprint)
    if not isinstance(entry, dict):
        return False
    prev_sources = set(entry.get("source_finding_ids", []))
    return prev_sources == set(source_finding_ids)


def _open_findings(state: dict) -> list[dict]:
    """Return all open findings from state."""
    findings = state.get("findings", {})
    return [
        f for f in findings.values()
        if isinstance(f, dict) and f.get("status") == "open"
    ]


def _group_by_file(state: dict) -> dict[str, list[dict]]:
    """Group open findings by file, excluding holistic (file='.')."""
    by_file: dict[str, list[dict]] = defaultdict(list)
    for f in _open_findings(state):
        file = f.get("file", "")
        if file and file != ".":
            by_file[file].append(f)
    return dict(by_file)


# ── Signal extraction ────────────────────────────────────────────────


def _extract_signals(findings: list[dict]) -> dict:
    """Extract key quantitative signals from a file's findings."""
    signals: dict = {}
    monster_funcs: list[str] = []

    for f in findings:
        det = f.get("detector", "")
        detail = f.get("detail", {})

        if det == "structural":
            s = detail.get("signals", {})
            if isinstance(s, dict):
                for key in ("max_params", "max_nesting", "loc", "function_count"):
                    val = s.get(key, 0)
                    if isinstance(val, int | float) and val > 0:
                        signals[key] = max(signals.get(key, 0), val)

        if det == "smells" and detail.get("smell_id") == "monster_function":
            loc = detail.get("loc", 0)
            if isinstance(loc, int | float) and loc > 0:
                signals["monster_loc"] = max(signals.get("monster_loc", 0), loc)
            func = detail.get("function", "")
            if func:
                monster_funcs.append(func)

    if monster_funcs:
        signals["monster_funcs"] = monster_funcs
    return signals


def _has_elevated_signals(findings: list[dict]) -> bool:
    """Does any finding have signals strong enough to flag on its own?"""
    for f in findings:
        det = f.get("detector", "")
        detail = f.get("detail", {})

        if det == "structural":
            s = detail.get("signals", {})
            if isinstance(s, dict):
                if s.get("max_params", 0) >= 8:
                    return True
                if s.get("max_nesting", 0) >= 6:
                    return True
                if s.get("loc", 0) >= 300:
                    return True

        if det == "smells" and detail.get("smell_id") == "monster_function":
            return True

        if det in ("dupes", "boilerplate_duplication", "coupling",
                    "responsibility_cohesion"):
            return True

    return False


# ── Concern classification ───────────────────────────────────────────


def _classify(detectors: set[str], signals: dict) -> str:
    """Pick the most specific concern type from what's present."""
    if len(detectors) >= 3:
        return "mixed_responsibilities"
    if "dupes" in detectors or "boilerplate_duplication" in detectors:
        return "duplication_design"
    if signals.get("monster_loc", 0) > 0:
        return "structural_complexity"
    if "coupling" in detectors:
        return "coupling_design"
    if signals.get("max_params", 0) >= 8:
        return "interface_design"
    if signals.get("max_nesting", 0) >= 6:
        return "structural_complexity"
    if "responsibility_cohesion" in detectors:
        return "mixed_responsibilities"
    return "design_concern"


def _build_summary(concern_type: str, detectors: set[str], signals: dict) -> str:
    """Human-readable one-liner."""
    if concern_type == "mixed_responsibilities":
        return (
            f"Issues from {len(detectors)} detectors — "
            "may have too many responsibilities"
        )
    if concern_type == "structural_complexity":
        parts: list[str] = []
        monster_loc = signals.get("monster_loc", 0)
        if monster_loc:
            funcs = signals.get("monster_funcs", [])
            label = f" ({', '.join(funcs[:3])})" if funcs else ""
            parts.append(f"monster function{label}: {int(monster_loc)} lines")
        nesting = signals.get("max_nesting", 0)
        if nesting >= 6:
            parts.append(f"nesting depth {int(nesting)}")
        params = signals.get("max_params", 0)
        if params >= 8:
            parts.append(f"{int(params)} parameters")
        return f"Structural complexity: {', '.join(parts) or 'elevated signals'}"
    if concern_type == "duplication_design":
        return "Duplication pattern — assess if extraction is warranted"
    if concern_type == "coupling_design":
        return "Coupling pattern — assess if boundaries need adjustment"
    if concern_type == "interface_design":
        return f"Interface complexity: {int(signals.get('max_params', 0))} parameters"
    return f"Design signals from {', '.join(sorted(detectors))}"


def _build_evidence(findings: list[dict], signals: dict) -> tuple[str, ...]:
    """Build evidence tuple from all findings and extracted signals."""
    evidence: list[str] = []

    detectors = sorted({f.get("detector", "") for f in findings})
    evidence.append(f"Flagged by: {', '.join(detectors)}")

    loc = signals.get("loc")
    if loc:
        evidence.append(f"File size: {int(loc)} lines")
    params = signals.get("max_params")
    if params and params >= 8:
        evidence.append(f"Max parameters: {int(params)}")
    nesting = signals.get("max_nesting")
    if nesting and nesting >= 6:
        evidence.append(f"Max nesting depth: {int(nesting)}")
    monster_loc = signals.get("monster_loc")
    if monster_loc:
        funcs = signals.get("monster_funcs", [])
        label = f" ({', '.join(funcs[:3])})" if funcs else ""
        evidence.append(f"Monster function{label}: {int(monster_loc)} lines")

    # Individual finding summaries — give LLM the full picture, capped.
    for f in findings[:10]:
        summary = f.get("summary", "")
        if summary:
            evidence.append(f"[{f.get('detector', '')}] {summary}")

    return tuple(evidence)


def _build_question(
    detectors: set[str], signals: dict
) -> str:
    """Build targeted question from dominant signals."""
    parts: list[str] = []

    if len(detectors) >= 3:
        parts.append(
            f"This file has issues across {len(detectors)} dimensions "
            f"({', '.join(sorted(detectors))}). Is it trying to do too many "
            "things, or is this complexity inherent to its domain?"
        )

    funcs = signals.get("monster_funcs", [])
    if funcs:
        parts.append(
            f"What are the distinct responsibilities in {funcs[0]}()? "
            "Should it be decomposed into focused functions?"
        )

    if signals.get("max_params", 0) >= 8:
        parts.append(
            "Should the parameters be grouped into a config/context object? "
            "Which ones belong together?"
        )

    if signals.get("max_nesting", 0) >= 6:
        parts.append(
            "Can the nesting be reduced with early returns, guard clauses, "
            "or extraction into helper functions?"
        )

    if "dupes" in detectors or "boilerplate_duplication" in detectors:
        parts.append(
            "Is the duplication worth extracting into a shared utility, "
            "or is it intentional variation?"
        )

    if "coupling" in detectors:
        parts.append(
            "Is the coupling intentional or does it indicate a missing "
            "abstraction boundary?"
        )

    if "orphaned" in detectors:
        parts.append(
            "Is this file truly dead, or is it used via a non-import mechanism "
            "(dynamic import, CLI entry point, plugin)?"
        )

    if "responsibility_cohesion" in detectors:
        parts.append(
            "What are the distinct responsibilities? Should this module be "
            "split along those lines?"
        )

    if not parts:
        parts.append(
            "Review the flagged patterns — are they design problems that "
            "need addressing, or acceptable given the file's role?"
        )

    return " ".join(parts)


# ── Generators ───────────────────────────────────────────────────────


def _file_concerns(state: dict, dismissals: dict) -> list[Concern]:
    """Per-file design concerns from aggregated mechanical signals.

    Flags a file if it has 2+ judgment-needed detectors OR a single
    detector with elevated signals (monster function, high params,
    deep nesting, duplication, coupling, mixed responsibilities).
    Bundles ALL findings for that file so the LLM sees the full picture.
    """
    by_file = _group_by_file(state)
    concerns: list[Concern] = []

    for file, all_findings in by_file.items():
        judgment = [
            f for f in all_findings
            if f.get("detector", "") in JUDGMENT_DETECTORS
        ]
        if not judgment:
            continue

        judgment_dets = {f.get("detector", "") for f in judgment}
        elevated = _has_elevated_signals(judgment)

        # Flag if 2+ judgment detectors OR 1 with elevated signals.
        if len(judgment_dets) < 2 and not elevated:
            continue

        signals = _extract_signals(judgment)
        concern_type = _classify(judgment_dets, signals)
        evidence = _build_evidence(judgment, signals)
        question = _build_question(judgment_dets, signals)
        summary = _build_summary(concern_type, judgment_dets, signals)

        all_ids = tuple(sorted(f.get("id", "") for f in judgment))
        fp_keys = tuple(sorted(judgment_dets))
        fp = _fingerprint(concern_type, file, fp_keys)

        if _is_dismissed(dismissals, fp, all_ids):
            continue

        concerns.append(
            Concern(
                type=concern_type,
                file=file,
                summary=summary,
                evidence=evidence,
                question=question,
                fingerprint=fp,
                source_findings=all_ids,
            )
        )

    return concerns


def _cross_file_patterns(state: dict, dismissals: dict) -> list[Concern]:
    """Systemic patterns: same judgment detector combo across 3+ files.

    When multiple files share the same combination of detector types,
    that's likely a codebase-wide pattern rather than isolated issues.
    """
    by_file = _group_by_file(state)

    # Group files by their judgment detector profile.
    profile_to_files: dict[frozenset[str], list[str]] = defaultdict(list)
    for file, findings in by_file.items():
        dets = frozenset(
            f.get("detector", "") for f in findings
            if f.get("detector", "") in JUDGMENT_DETECTORS
        )
        if len(dets) >= 2:
            profile_to_files[dets].append(file)

    concerns: list[Concern] = []
    for det_combo, files in profile_to_files.items():
        if len(files) < 3:
            continue

        sorted_files = sorted(files)
        combo_names = tuple(sorted(det_combo))
        all_ids = tuple(sorted(
            f.get("id", "")
            for file in sorted_files
            for f in by_file[file]
            if f.get("detector", "") in det_combo
        ))
        # Use first few files in fingerprint so it's stable but bounded.
        fp = _fingerprint(
            "systemic_pattern",
            ",".join(sorted_files[:5]),
            combo_names,
        )

        if _is_dismissed(dismissals, fp, all_ids):
            continue

        concerns.append(
            Concern(
                type="systemic_pattern",
                file=sorted_files[0],
                summary=(
                    f"{len(files)} files share the same problem pattern "
                    f"({', '.join(combo_names)})"
                ),
                evidence=(
                    f"Affected files: {', '.join(sorted_files[:10])}",
                    f"Shared detectors: {', '.join(combo_names)}",
                    f"Total files: {len(files)}",
                ),
                question=(
                    f"These {len(files)} files all have the same combination "
                    f"of issues ({', '.join(combo_names)}). Is this a systemic "
                    "pattern that should be addressed at the architecture level "
                    "(shared base class, framework change, lint rule), or are "
                    "these independent issues that happen to look similar?"
                ),
                fingerprint=fp,
                source_findings=all_ids,
            )
        )

    return concerns


_GENERATORS = [_file_concerns, _cross_file_patterns]


def generate_concerns(
    state: dict, lang_name: str | None = None
) -> list[Concern]:
    """Run all concern generators against current state.

    Returns deduplicated list sorted by (type, file).
    lang_name is reserved for future language-specific generators.
    """
    del lang_name  # Reserved for future use.
    dismissals = state.get("concern_dismissals", {})
    concerns: list[Concern] = []
    seen_fps: set[str] = set()

    for gen in _GENERATORS:
        for concern in gen(state, dismissals):
            if concern.fingerprint not in seen_fps:
                seen_fps.add(concern.fingerprint)
                concerns.append(concern)

    concerns.sort(key=lambda c: (c.type, c.file))
    return concerns


def cleanup_stale_dismissals(state: dict) -> int:
    """Remove dismissals whose source findings all disappeared.

    Returns the number of stale entries removed.  Dismissals without
    ``source_finding_ids`` (legacy) are left untouched.
    """
    dismissals = state.get("concern_dismissals", {})
    if not dismissals:
        return 0
    open_ids = {f.get("id", "") for f in _open_findings(state)}
    stale_fps = [
        fp
        for fp, entry in dismissals.items()
        if entry.get("source_finding_ids")
        and not any(sid in open_ids for sid in entry["source_finding_ids"])
    ]
    for fp in stale_fps:
        del dismissals[fp]
    return len(stale_fps)


__all__ = ["Concern", "cleanup_stale_dismissals", "generate_concerns"]
