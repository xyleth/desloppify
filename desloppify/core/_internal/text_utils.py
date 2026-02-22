"""Text-oriented utility helpers split from the main utils facade."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("DESLOPPIFY_ROOT", Path.cwd())).resolve()


def read_code_snippet(
    filepath: str,
    line: int,
    context: int = 1,
    *,
    project_root: Path | str | None = None,
) -> str | None:
    """Read ±context lines around a line number. Returns formatted string or None."""
    try:
        root = (
            Path(project_root).resolve()
            if project_root is not None
            else PROJECT_ROOT
        )
        full = Path(filepath)
        if not full.is_absolute():
            full = root / full
        content = full.read_text(errors="replace")
    except OSError:
        return None
    lines = content.splitlines()
    if line < 1 or line > len(lines):
        return None
    start = max(0, line - 1 - context)
    end = min(len(lines), line + context)
    parts = []
    for i in range(start, end):
        ln = i + 1
        marker = "→" if ln == line else " "
        text = lines[i]
        if len(text) > 120:
            text = text[:117] + "..."
        parts.append(f"    {marker} {ln:>4} │ {text}")
    return "\n".join(parts)


def get_area(filepath: str, *, min_depth: int = 2) -> str:
    """Derive an area name from a file path (generic: first 2 path components).

    *min_depth* controls the minimum number of path components required before
    the two-component area is returned.  The default (2) means a path like
    ``"a/b"`` already qualifies.  Python uses ``min_depth=3`` so that
    ``"pkg/mod.py"`` returns just ``"pkg"`` while ``"pkg/sub/mod.py"`` returns
    ``"pkg/sub"``.
    """
    text = (filepath or "").strip()
    if not text:
        return "(unknown)"
    parts = Path(text).parts
    if not parts:
        return "(unknown)"
    return "/".join(parts[:2]) if len(parts) >= min_depth else parts[0]


def strip_c_style_comments(text: str) -> str:
    """Strip // and /* */ comments while preserving string literals."""
    result: list[str] = []
    i = 0
    in_str = None
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\" and i + 1 < len(text):
                result.append(text[i : i + 2])
                i += 2
                continue
            if ch == in_str:
                in_str = None
            result.append(ch)
            i += 1
        elif ch in ('"', "'", "`"):
            in_str = ch
            result.append(ch)
            i += 1
        elif ch == "/" and i + 1 < len(text):
            if text[i + 1] == "/":
                nl = text.find("\n", i)
                if nl == -1:
                    break
                i = nl
            elif text[i + 1] == "*":
                end = text.find("*/", i + 2)
                if end == -1:
                    break
                i = end + 2
            else:
                result.append(ch)
                i += 1
        else:
            result.append(ch)
            i += 1
    return "".join(result)


def is_numeric(value: object) -> bool:
    """Return True if *value* is an int or float but NOT a bool.

    Python's ``bool`` is a subclass of ``int``, so ``isinstance(True, int)``
    is ``True``.  Many JSON-derived payloads need to distinguish real numbers
    from booleans; this helper centralises that guard.
    """
    return isinstance(value, int | float) and not isinstance(value, bool)


__all__ = ["get_area", "is_numeric", "read_code_snippet", "strip_c_style_comments"]
