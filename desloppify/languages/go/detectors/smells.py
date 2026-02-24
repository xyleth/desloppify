"""Go code smell detection.

Detects runtime safety issues, performance anti-patterns, and code smells
that standard Go linters (staticcheck, revive, gosec) don't cover.
"""

from __future__ import annotations

import re
from pathlib import Path

from desloppify.languages.go.extractors import find_go_files


def _smell(id: str, label: str, severity: str, pattern: str | None = None) -> dict:
    return {"id": id, "label": label, "pattern": pattern, "severity": severity}


SMELL_CHECKS = [
    _smell(
        "panic_in_lib",
        "panic() in library code (non-main package)",
        "high",
        r"\bpanic\s*\(",
    ),
    _smell(
        "fire_and_forget_goroutine",
        "Fire-and-forget goroutine (no sync mechanism)",
        "medium",
        r"^\s*go\s+(?:func\b|\w+\()",
    ),
    _smell(
        "time_tick_leak",
        "time.Tick leaks ticker (use time.NewTicker with Stop)",
        "high",
        r"\btime\.Tick\s*\(",
    ),
    _smell(
        "unbuffered_signal",
        "Unbuffered signal channel (may miss signals)",
        "high",
        None,
    ),
    _smell(
        "single_case_select",
        "Single-case select (unnecessary overhead)",
        "low",
        None,
    ),
    _smell(
        "nil_map_write",
        "Potential write to nil map (runtime panic)",
        "high",
        None,
    ),
    _smell(
        "string_concat_loop",
        "String concatenation in loop (O(n²) allocations)",
        "medium",
        None,
    ),
    _smell(
        "yoda_condition",
        "Yoda condition (constant on left side of ==)",
        "low",
        None,
    ),
    _smell(
        "todo_fixme",
        "TODO/FIXME/HACK comments",
        "low",
        r"//\s*(?:TODO|FIXME|HACK|XXX)",
    ),
    _smell(
        "dogsledding",
        "Excessive blank identifiers (3+ underscores on LHS)",
        "low",
        r"_\s*,\s*_\s*,\s*_",
    ),
    _smell(
        "too_many_params",
        "Too many function parameters (>5)",
        "medium",
        None,
    ),
]


def detect_smells(path: Path) -> tuple[list[dict], int]:
    """Detect Go code smell patterns. Returns (entries, total_files_checked)."""
    smell_counts: dict[str, list[dict]] = {s["id"]: [] for s in SMELL_CHECKS}
    files = find_go_files(path)

    for filepath in files:
        if filepath.endswith("_test.go"):
            continue
        try:
            content = Path(filepath).read_text(errors="replace")
            lines = content.splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        is_main_pkg = _is_main_package(lines)

        for check in SMELL_CHECKS:
            if check["pattern"] is None:
                continue
            # Skip panic_in_lib for main packages
            if check["id"] == "panic_in_lib" and is_main_pkg:
                continue
            pat = re.compile(check["pattern"])
            for i, line in enumerate(lines):
                # Don't skip comment lines for TODO detection
                if _is_comment_line(line) and check["id"] != "todo_fixme":
                    continue
                if pat.search(line):
                    smell_counts[check["id"]].append(
                        {
                            "file": filepath,
                            "line": i + 1,
                            "content": line.strip()[:100],
                        }
                    )

        # Multi-line detectors
        _detect_unbuffered_signal(filepath, lines, smell_counts)
        _detect_single_case_select(filepath, content, smell_counts)
        _detect_nil_map_write(filepath, lines, smell_counts)
        _detect_string_concat_loop(filepath, lines, smell_counts)
        _detect_yoda_condition(filepath, lines, smell_counts)
        _detect_too_many_params(filepath, content, smell_counts)

    severity_order = {"high": 0, "medium": 1, "low": 2}
    entries = []
    for check in SMELL_CHECKS:
        matches = smell_counts[check["id"]]
        if matches:
            entries.append(
                {
                    "id": check["id"],
                    "label": check["label"],
                    "severity": check["severity"],
                    "count": len(matches),
                    "files": len(set(m["file"] for m in matches)),
                    "matches": matches[:50],
                }
            )
    entries.sort(key=lambda e: (severity_order.get(e["severity"], 9), -e["count"]))
    return entries, len(files)


def _is_comment_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("//") or stripped.startswith("/*")


def _is_main_package(lines: list[str]) -> bool:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("package "):
            return stripped == "package main"
    return False


def _detect_unbuffered_signal(
    filepath: str, lines: list[str], smell_counts: dict[str, list]
):
    """Detect signal.Notify with unbuffered channel."""
    chan_vars: set[str] = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _is_comment_line(line):
            continue

        m = re.search(r"(\w+)\s*:?=\s*make\s*\(\s*chan\s+os\.Signal\s*\)", stripped)
        if m:
            chan_vars.add(m.group(1))

        if "signal.Notify" in stripped:
            for var in chan_vars:
                if var in stripped:
                    smell_counts["unbuffered_signal"].append(
                        {
                            "file": filepath,
                            "line": i + 1,
                            "content": stripped[:100],
                        }
                    )


def _detect_single_case_select(
    filepath: str, content: str, smell_counts: dict[str, list]
):
    """Detect select statements with only one case."""
    select_re = re.compile(r"\bselect\s*\{")
    for m in select_re.finditer(content):
        start = m.end()
        depth = 1
        i = start
        while i < len(content) and depth > 0:
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
            i += 1
        block = content[start : i - 1]
        case_count = len(re.findall(r"^\s*case\s+", block, re.MULTILINE))
        default_count = len(re.findall(r"^\s*default\s*:", block, re.MULTILINE))
        total = case_count + default_count
        if total == 1:
            line_num = content[: m.start()].count("\n") + 1
            smell_counts["single_case_select"].append(
                {
                    "file": filepath,
                    "line": line_num,
                    "content": content[m.start() : m.start() + 80].strip(),
                }
            )


def _detect_nil_map_write(
    filepath: str, lines: list[str], smell_counts: dict[str, list]
):
    """Detect potential writes to nil maps (var m map[...] without make)."""
    uninit_maps: dict[str, int] = {}

    for i, line in enumerate(lines):
        stripped = line.strip()
        if _is_comment_line(line):
            continue

        m = re.match(r"var\s+(\w+)\s+map\[", stripped)
        if m:
            uninit_maps[m.group(1)] = i + 1

        for var_name in list(uninit_maps):
            if re.search(
                rf"\b{re.escape(var_name)}\s*=\s*(?:make\s*\(|map\[)", stripped
            ):
                del uninit_maps[var_name]

        for var_name in list(uninit_maps):
            if re.search(rf"\b{re.escape(var_name)}\s*\[.+\]\s*=", stripped):
                smell_counts["nil_map_write"].append(
                    {
                        "file": filepath,
                        "line": i + 1,
                        "content": stripped[:100],
                    }
                )
                del uninit_maps[var_name]


def _detect_string_concat_loop(
    filepath: str, lines: list[str], smell_counts: dict[str, list]
):
    """Detect string concatenation with += inside loops."""
    in_loop = False
    loop_depth = 0
    brace_depth = 0
    loop_brace_depth = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if _is_comment_line(line):
            continue

        brace_depth += stripped.count("{") - stripped.count("}")

        if re.match(r"\bfor\b", stripped):
            in_loop = True
            loop_depth += 1
            loop_brace_depth = brace_depth

        if in_loop and brace_depth < loop_brace_depth:
            loop_depth -= 1
            if loop_depth <= 0:
                in_loop = False
                loop_depth = 0

        if in_loop and "+=" in stripped:
            m = re.match(r"(\w+)\s*\+=", stripped)
            if m:
                smell_counts["string_concat_loop"].append(
                    {
                        "file": filepath,
                        "line": i + 1,
                        "content": stripped[:100],
                    }
                )


_YODA_RE = re.compile(
    r"""(?:if|&&|\|\|)\s+     # preceded by if or logical op
    (?:
        (?:(?:true|false|nil)\s*(?:==|!=))  # bool/nil literal on left
        |
        (?:\d+\s*(?:==|!=|>=?|<=?))         # number on left
        |
        (?:"[^"]*"\s*(?:==|!=))             # string literal on left
    )""",
    re.VERBOSE,
)


def _detect_yoda_condition(
    filepath: str, lines: list[str], smell_counts: dict[str, list]
):
    """Detect Yoda conditions (literal on left side of comparison)."""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _is_comment_line(line):
            continue
        if _YODA_RE.search(stripped):
            smell_counts["yoda_condition"].append(
                {
                    "file": filepath,
                    "line": i + 1,
                    "content": stripped[:100],
                }
            )


_FUNC_PARAMS_RE = re.compile(
    r"^func\s+(?:\(\s*\w+\s+\*?\w+\s*\)\s*)?\w+\s*\(([^)]*)\)",
    re.MULTILINE,
)

_MAX_PARAMS = 5


def _detect_too_many_params(
    filepath: str, content: str, smell_counts: dict[str, list]
):
    """Detect functions with more than 5 parameters."""
    lines = content.splitlines()
    for m in _FUNC_PARAMS_RE.finditer(content):
        param_list = m.group(1).strip()
        if not param_list:
            continue
        param_count = param_list.count(",") + 1
        if param_count > _MAX_PARAMS:
            line_num = content[: m.start()].count("\n") + 1
            smell_counts["too_many_params"].append(
                {
                    "file": filepath,
                    "line": line_num,
                    "content": (
                        lines[line_num - 1].strip()[:100]
                        if line_num <= len(lines)
                        else ""
                    ),
                }
            )
