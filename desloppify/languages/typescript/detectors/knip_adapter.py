"""Knip adapter — dead exports and orphaned file detection via Knip.

Runs ``npx knip --reporter json`` as a subprocess and parses its JSON output
into the entry dicts expected by the existing phase runners.

Knip is far more accurate than the grep-based exports detector because it
understands re-exports, barrel files, dynamic imports, and entry points. It also
detects truly orphaned (unreachable) files more reliably than the custom
graph-traversal approach.

Falls back gracefully when Knip is not installed (returns None), allowing the
existing detectors to take over.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from desloppify.utils import PROJECT_ROOT, rel

logger = logging.getLogger(__name__)


def _run_knip(path: Path, timeout: int = 120) -> dict | None:
    """Run ``npx knip --reporter json`` and return parsed JSON, or None on failure."""
    try:
        result = subprocess.run(
            ["npx", "knip", "--reporter", "json", "--no-gitignore"],
            capture_output=True,
            text=True,
            cwd=str(path),
            timeout=timeout,
        )
    except FileNotFoundError:
        logger.debug("knip: npx not found — skipping Knip detection")
        return None
    except subprocess.TimeoutExpired:
        logger.debug("knip: timed out after %ds", timeout)
        return None
    except OSError as exc:
        logger.debug("knip: OSError running knip: %s", exc)
        return None

    # Knip exits 1 when it finds issues (normal — not an error).
    stdout = result.stdout.strip()
    if not stdout:
        logger.debug("knip: no output (possibly not installed)")
        return None

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        logger.debug("knip: JSON parse error: %s", exc)
        return None

    return data


def _normalize_path(raw: str, scan_path: Path) -> str:
    """Return a path relative to PROJECT_ROOT, scoped to scan_path."""
    p = Path(raw)
    if not p.is_absolute():
        p = (scan_path / p).resolve()
    # Check the file lives inside scan_path.
    try:
        p.relative_to(scan_path.resolve())
    except ValueError:
        return ""
    return rel(str(p))


def detect_with_knip(path: Path) -> tuple[list[dict], list[dict]] | None:
    """Run Knip and return (exports_entries, orphaned_entries).

    Each exports entry: {"file": str, "name": str, "line": int, "kind": str}
    Each orphaned entry: {"file": str, "importers": []}

    Returns None if Knip is not available or fails.
    """
    data = _run_knip(path)
    if data is None:
        return None

    exports_entries: list[dict] = []
    orphaned_entries: list[dict] = []

    # ── Orphaned files (top-level "files" key) ──────────────────────────────
    for raw_file in data.get("files", []):
        norm = _normalize_path(raw_file, path)
        if norm:
            orphaned_entries.append({"file": norm, "importers": []})

    # ── Per-file issues ──────────────────────────────────────────────────────
    for issue in data.get("issues", []):
        raw_file = issue.get("file", "")
        norm = _normalize_path(raw_file, path)
        if not norm:
            continue

        # Unused named exports
        for export in issue.get("exports", []):
            name = export.get("name", "")
            if not name:
                continue
            pos = export.get("pos", {}).get("start", {})
            line = pos.get("line", 0) if isinstance(pos, dict) else 0
            exports_entries.append(
                {
                    "file": norm,
                    "name": name,
                    "line": line,
                    "kind": "export",
                }
            )

        # Unused type exports
        for export in issue.get("types", []):
            name = export.get("name", "")
            if not name:
                continue
            pos = export.get("pos", {}).get("start", {})
            line = pos.get("line", 0) if isinstance(pos, dict) else 0
            exports_entries.append(
                {
                    "file": norm,
                    "name": name,
                    "line": line,
                    "kind": "type",
                }
            )

    logger.debug(
        "knip: found %d dead exports, %d orphaned files",
        len(exports_entries),
        len(orphaned_entries),
    )
    return exports_entries, orphaned_entries
