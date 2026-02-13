"""Action computation and tool inventory."""

from __future__ import annotations

from ._constants import DETECTOR_TOOLS


def _compute_actions(by_det: dict[str, int], dim_scores: dict, state: dict,
                     debt: dict, lang: str | None) -> list[dict]:
    """Compute prioritized action list with tool mapping."""
    from ..scoring import merge_potentials, compute_score_impact, get_dimension_for_detector

    potentials = merge_potentials(state.get("potentials", {}))
    actions = []
    priority = 0

    def _impact_for(det: str, count: int) -> float:
        if not potentials or not dim_scores:
            return 0.0
        return compute_score_impact(
            {k: {"score": v["score"], "tier": v.get("tier", 3),
                  "detectors": v.get("detectors", {})}
             for k, v in dim_scores.items()},
            potentials, det, count)

    def _dim_name_for(det: str) -> str:
        dim = get_dimension_for_detector(det)
        return dim.name if dim else "Unknown"

    # Auto-fixable actions (or manual-fix for Python)
    for det, tool_info in DETECTOR_TOOLS.items():
        if tool_info["action_type"] != "auto_fix":
            continue
        count = by_det.get(det, 0)
        if count == 0:
            continue

        impact = _impact_for(det, count)

        # Python has no auto-fixers — suggest manual fix instead
        if lang == "python":
            priority += 1
            actions.append({
                "priority": priority,
                "type": "manual_fix",
                "detector": det,
                "count": count,
                "description": f"{count} {det} findings — fix manually",
                "command": f"desloppify show {det} --status open",
                "impact": round(impact, 1),
                "dimension": _dim_name_for(det),
            })
            continue

        for fixer in tool_info["fixers"]:
            priority += 1
            actions.append({
                "priority": priority,
                "type": "auto_fix",
                "detector": det,
                "count": count,
                "description": f"{count} {det} findings — auto-fixable",
                "command": f"desloppify fix {fixer} --dry-run",
                "impact": round(impact, 1),
                "dimension": _dim_name_for(det),
            })
            break  # One action per detector, listing first fixer

    # Reorganize actions
    for det, tool_info in DETECTOR_TOOLS.items():
        if tool_info["action_type"] != "reorganize":
            continue
        count = by_det.get(det, 0)
        if count == 0:
            continue

        impact = _impact_for(det, count)
        priority += 1
        guidance = tool_info.get("guidance", "restructure with move")
        actions.append({
            "priority": priority,
            "type": "reorganize",
            "detector": det,
            "count": count,
            "description": f"{count} {det} findings — {guidance}",
            "command": f"desloppify show {det} --status open",
            "impact": round(impact, 1),
            "dimension": _dim_name_for(det),
        })

    # Refactor actions
    for det, tool_info in DETECTOR_TOOLS.items():
        if tool_info["action_type"] not in ("refactor", "manual_fix"):
            continue
        count = by_det.get(det, 0)
        if count == 0:
            continue

        impact = _impact_for(det, count)
        priority += 1

        # Override command for subjective_review — point to fix review workflow
        if det == "subjective_review":
            command = "desloppify fix review"
            description = f"{count} files need design review — run design review with dimension templates"
        else:
            command = f"desloppify show {det} --status open"
            description = f"{count} {det} findings — {tool_info.get('guidance', 'manual fix')}"

        actions.append({
            "priority": priority,
            "type": tool_info["action_type"],
            "detector": det,
            "count": count,
            "description": description,
            "command": command,
            "impact": round(impact, 1),
            "dimension": _dim_name_for(det),
        })

    # Debt review action
    if debt.get("overall_gap", 0) > 2.0:
        priority += 1
        actions.append({
            "priority": priority,
            "type": "debt_review",
            "detector": None,
            "description": f"{debt['overall_gap']} pts of wontfix debt — review stale decisions",
            "command": "desloppify show --status wontfix",
            "gap": debt["overall_gap"],
        })

    # Sort by impact descending, auto_fix first
    type_order = {"auto_fix": 0, "reorganize": 1, "refactor": 2, "manual_fix": 3, "debt_review": 4}
    actions.sort(key=lambda a: (type_order.get(a["type"], 9), -a.get("impact", 0)))
    for i, a in enumerate(actions):
        a["priority"] = i + 1

    return actions


def _compute_tools(by_det: dict[str, int], lang: str | None,
                   badge: dict) -> dict:
    """Compute available tools inventory for the current context."""
    # Available fixers (only those with >0 open findings)
    fixers = []
    if lang != "python":
        for det, tool_info in DETECTOR_TOOLS.items():
            if tool_info["action_type"] != "auto_fix":
                continue
            count = by_det.get(det, 0)
            if count == 0:
                continue
            for fixer in tool_info["fixers"]:
                fixers.append({
                    "name": fixer,
                    "detector": det,
                    "open_count": count,
                    "command": f"desloppify fix {fixer} --dry-run",
                })

    # Move tool relevance
    org_issues = sum(by_det.get(d, 0) for d in
                     ["orphaned", "flat_dirs", "naming", "single_use", "coupling", "cycles"])
    move_reasons = []
    if by_det.get("orphaned", 0):
        move_reasons.append(f"{by_det['orphaned']} orphaned files")
    if by_det.get("coupling", 0):
        move_reasons.append(f"{by_det['coupling']} coupling violations")
    if by_det.get("single_use", 0):
        move_reasons.append(f"{by_det['single_use']} single-use files")
    if by_det.get("flat_dirs", 0):
        move_reasons.append(f"{by_det['flat_dirs']} flat directories")
    if by_det.get("naming", 0):
        move_reasons.append(f"{by_det['naming']} naming issues")

    return {
        "fixers": fixers,
        "move": {
            "available": True,
            "relevant": org_issues > 0,
            "reason": " + ".join(move_reasons) if move_reasons else None,
            "usage": "desloppify move <source> <dest> [--dry-run]",
        },
        "plan": {
            "command": "desloppify plan",
            "description": "Generate prioritized markdown cleanup plan",
        },
        "badge": badge,
    }
