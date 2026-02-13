"""Review coverage detector — flags production files lacking design review.

Runs during every scan. Checks the review_cache (persisted in state) to determine
which production files have been reviewed, are stale, or have changed since review.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..review import _MIN_REVIEW_LOC, _LOW_VALUE_NAMES, _hash_file
from ..utils import rel, _read_file_text, resolve_path


def detect_review_coverage(
    files: list[str],
    zone_map,
    review_cache: dict,
    lang_name: str,
    max_age_days: int = 30,
) -> tuple[list[dict], int]:
    """Detect production files missing or with stale design reviews.

    Args:
        files: list of file paths from file_finder
        zone_map: FileZoneMap (or None)
        review_cache: dict of {rel_path: {content_hash, reviewed_at, finding_count}}
        lang_name: "python" or "typescript"
        max_age_days: reviews older than this are flagged as stale

    Returns:
        (entries, potential) where potential = count of reviewable production files.
    """
    now = datetime.now(timezone.utc)
    entries: list[dict] = []
    potential = 0

    for filepath in files:
        rpath = rel(filepath)

        # Skip non-production files
        if zone_map is not None:
            zone = zone_map.get(filepath)
            if zone.value in ("test", "generated", "vendor", "config", "script"):
                continue

        # Skip low-value files (types, constants, enums, index, .d.ts)
        if _LOW_VALUE_NAMES.search(rpath):
            continue

        # Skip files below minimum LOC
        abs_path = resolve_path(filepath)
        content = _read_file_text(abs_path)
        if content is None:
            continue
        loc = len(content.splitlines())
        if loc < _MIN_REVIEW_LOC:
            continue

        potential += 1

        # Check review cache
        cached = review_cache.get(rpath)
        if cached is None:
            entries.append({
                "file": abs_path,
                "name": "unreviewed",
                "tier": 4,
                "confidence": "low",
                "summary": f"No design review on record — run `desloppify review --prepare`",
                "detail": {"reason": "unreviewed", "loc": loc},
            })
            continue

        # Check if content changed since review
        current_hash = _hash_file(abs_path)
        if current_hash and current_hash != cached.get("content_hash", ""):
            entries.append({
                "file": abs_path,
                "name": "changed",
                "tier": 4,
                "confidence": "medium",
                "summary": f"File changed since last review — re-review recommended",
                "detail": {"reason": "changed", "loc": loc},
            })
            continue

        # Check if review is stale (age expired)
        reviewed_at = cached.get("reviewed_at", "")
        if reviewed_at:
            try:
                reviewed = datetime.fromisoformat(reviewed_at)
                age_days = (now - reviewed).days
                if age_days > max_age_days:
                    entries.append({
                        "file": abs_path,
                        "name": "stale",
                        "tier": 4,
                        "confidence": "low",
                        "summary": f"Review is stale ({age_days} days old) — re-review recommended",
                        "detail": {"reason": "stale", "age_days": age_days, "loc": loc},
                    })
                    continue
            except (ValueError, TypeError):
                # Can't parse date — treat as stale
                entries.append({
                    "file": abs_path,
                    "name": "stale",
                    "tier": 4,
                    "confidence": "low",
                    "summary": f"Review date unparseable — re-review recommended",
                    "detail": {"reason": "stale", "loc": loc},
                })
                continue
        else:
            # No reviewed_at — treat as unreviewed
            entries.append({
                "file": abs_path,
                "name": "unreviewed",
                "tier": 4,
                "confidence": "low",
                "summary": f"No design review on record — run `desloppify review --prepare`",
                "detail": {"reason": "unreviewed", "loc": loc},
            })

    return entries, potential
