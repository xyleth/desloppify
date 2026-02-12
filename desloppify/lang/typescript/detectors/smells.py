"""TypeScript/React code smell detection.

Defines TS-specific smell rules and multi-line smell helpers (brace-tracked).
"""

import re
from pathlib import Path

from ....utils import PROJECT_ROOT, find_ts_files


TS_SMELL_CHECKS = [
    {
        "id": "empty_catch",
        "label": "Empty catch blocks",
        "pattern": r"catch\s*\([^)]*\)\s*\{\s*\}",
        "severity": "high",
    },
    {
        "id": "any_type",
        "label": "Explicit `any` types",
        "pattern": r":\s*any\b",
        "severity": "medium",
    },
    {
        "id": "ts_ignore",
        "label": "@ts-ignore / @ts-expect-error",
        "pattern": r"@ts-(?:ignore|expect-error)",
        "severity": "medium",
    },
    {
        "id": "ts_nocheck",
        "label": "@ts-nocheck disables all type checking",
        "pattern": r"^\s*//\s*@ts-nocheck",
        "severity": "high",
    },
    {
        "id": "non_null_assert",
        "label": "Non-null assertions (!.)",
        "pattern": r"\w+!\.",
        "severity": "low",
    },
    {
        "id": "hardcoded_color",
        "label": "Hardcoded color values",
        "pattern": r"""(?:color|background|border|fill|stroke)\s*[:=]\s*['"]#[0-9a-fA-F]{3,8}['"]""",
        "severity": "medium",
    },
    {
        "id": "hardcoded_rgb",
        "label": "Hardcoded rgb/rgba",
        "pattern": r"rgba?\(\s*\d+",
        "severity": "medium",
    },
    {
        "id": "async_no_await",
        "label": "Async functions without await",
        "pattern": None,  # multi-line analysis
        "severity": "medium",
    },
    {
        "id": "magic_number",
        "label": "Magic numbers (>1000 in logic)",
        "pattern": r"(?:===?|!==?|>=?|<=?|[+\-*/])\s*\d{4,}",
        "severity": "low",
    },
    {
        "id": "console_error_no_throw",
        "label": "console.error without throw/return",
        "pattern": None,  # multi-line analysis
        "severity": "medium",
    },
    {
        "id": "empty_if_chain",
        "label": "Empty if/else chains",
        "pattern": None,  # multi-line analysis
        "severity": "high",
    },
    {
        "id": "dead_useeffect",
        "label": "useEffect with empty body",
        "pattern": None,  # multi-line analysis
        "severity": "high",
    },
    {
        "id": "swallowed_error",
        "label": "Catch blocks that only log (swallowed errors)",
        "pattern": None,  # multi-line analysis
        "severity": "medium",
    },
    {
        "id": "hardcoded_url",
        "label": "Hardcoded URL in source code",
        "pattern": r"""(?:['\"])https?://[^\s'\"]+(?:['\"])""",
        "severity": "medium",
    },
    {
        "id": "todo_fixme",
        "label": "TODO/FIXME/HACK comments",
        "pattern": r"//\s*(?:TODO|FIXME|HACK|XXX)",
        "severity": "low",
    },
    {
        "id": "debug_tag",
        "label": "Vestigial debug tag in log/print",
        "pattern": r"""(?:['"`])\[([A-Z][A-Z0-9_]{2,})\]\s""",
        "severity": "low",
    },
    {
        "id": "monster_function",
        "label": "Monster function (>150 LOC)",
        # Detected via brace-tracking
        "pattern": None,
        "severity": "high",
    },
    {
        "id": "dead_function",
        "label": "Dead function (body is empty/return-only)",
        # Detected via brace-tracking
        "pattern": None,
        "severity": "medium",
    },
    {
        "id": "voided_symbol",
        "label": "Dead internal code (void-suppressed unused symbol)",
        "pattern": r"^\s*void\s+[a-zA-Z_]\w*\s*;?\s*$",
        "severity": "medium",
    },
    {
        "id": "window_global",
        "label": "Window global escape hatch (window.__*)",
        "pattern": None,  # multi-line analysis — regex needs alternation
        "severity": "medium",
    },
    {
        "id": "workaround_tag",
        "label": "Workaround tag in comment ([PascalCaseTag])",
        "pattern": r"//.*\[([A-Z][a-z]+(?:[A-Z][a-z]+)+)\]",
        "severity": "low",
    },
    {
        "id": "catch_return_default",
        "label": "Catch block returns default object (silent failure)",
        "pattern": None,  # multi-line brace-tracked
        "severity": "high",
    },
]


def _build_ts_line_state(lines: list[str]) -> dict[int, str]:
    """Build a map of line numbers that are inside block comments or template literals.

    Returns {0-indexed line: reason} where reason is "block_comment" or "template_literal".
    Lines not in the map are normal code lines suitable for regex checks.

    Tracks:
    - Block comment state (opened by /*, closed by */)
    - Template literal state (opened by backtick, closed by backtick,
      with ${} nesting awareness)
    """
    state: dict[int, str] = {}
    in_block_comment = False
    in_template = False
    template_brace_depth = 0  # tracks ${} nesting inside template literals

    for i, line in enumerate(lines):
        if in_block_comment:
            state[i] = "block_comment"
            if "*/" in line:
                in_block_comment = False
            continue

        if in_template:
            state[i] = "template_literal"
            # Scan for closing backtick or ${} nesting
            j = 0
            while j < len(line):
                ch = line[j]
                if ch == "\\" and j + 1 < len(line):
                    j += 2
                    continue
                if ch == "$" and j + 1 < len(line) and line[j + 1] == "{":
                    template_brace_depth += 1
                    j += 2
                    continue
                if ch == "}" and template_brace_depth > 0:
                    template_brace_depth -= 1
                    j += 1
                    continue
                if ch == "`" and template_brace_depth == 0:
                    in_template = False
                    # Rest of line is normal code — don't mark it
                    # but we already marked the line; that's fine for
                    # line-level filtering
                    break
                j += 1
            continue

        # Normal code line — check for block comment or template literal start
        j = 0
        in_str = None
        while j < len(line):
            ch = line[j]

            # Skip escape sequences
            if in_str and ch == "\\" and j + 1 < len(line):
                j += 2
                continue

            # String tracking
            if in_str:
                if ch == in_str:
                    in_str = None
                j += 1
                continue

            # Line comment — rest is not code
            if ch == "/" and j + 1 < len(line) and line[j + 1] == "/":
                break

            # Block comment start
            if ch == "/" and j + 1 < len(line) and line[j + 1] == "*":
                # Check if it closes on same line
                close = line.find("*/", j + 2)
                if close != -1:
                    j = close + 2
                    continue
                else:
                    in_block_comment = True
                    break

            # Template literal start
            if ch == "`":
                # Scan for closing backtick on same line
                k = j + 1
                found_close = False
                depth = 0
                while k < len(line):
                    c = line[k]
                    if c == "\\" and k + 1 < len(line):
                        k += 2
                        continue
                    if c == "$" and k + 1 < len(line) and line[k + 1] == "{":
                        depth += 1
                        k += 2
                        continue
                    if c == "}" and depth > 0:
                        depth -= 1
                        k += 1
                        continue
                    if c == "`" and depth == 0:
                        found_close = True
                        j = k + 1
                        break
                    k += 1
                if found_close:
                    continue
                else:
                    in_template = True
                    template_brace_depth = depth
                    break

            if ch in ("'", '"'):
                in_str = ch
                j += 1
                continue

            j += 1

    return state


def _ts_match_is_in_string(line: str, match_start: int) -> bool:
    """Check if a match position falls inside a string literal or comment on a single line.

    Mirrors Python's _match_is_in_string but for TS syntax (', ", `, //).
    """
    i = 0
    in_str = None

    while i < len(line):
        if i == match_start:
            return in_str is not None

        ch = line[i]

        # Escape sequences inside strings
        if in_str and ch == "\\" and i + 1 < len(line):
            i += 2
            continue

        if in_str:
            if ch == in_str:
                in_str = None
            i += 1
            continue

        # Line comment — everything after is non-code
        if ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
            return match_start > i

        if ch in ("'", '"', '`'):
            in_str = ch
            i += 1
            continue

        i += 1

    return False


def detect_smells(path: Path) -> tuple[list[dict], int]:
    """Detect TypeScript/React code smell patterns across the codebase.

    Returns (entries, total_files_checked).
    """
    checks = TS_SMELL_CHECKS
    smell_counts: dict[str, list[dict]] = {s["id"]: [] for s in checks}
    files = find_ts_files(path)

    for filepath in files:
        if "node_modules" in filepath or ".d.ts" in filepath:
            continue
        try:
            p = Path(filepath) if Path(filepath).is_absolute() else PROJECT_ROOT / filepath
            content = p.read_text()
            lines = content.splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        # Build line state for string/comment filtering
        line_state = _build_ts_line_state(lines)

        # Regex-based smells
        for check in checks:
            if check["pattern"] is None:
                continue
            for i, line in enumerate(lines):
                # Skip lines inside block comments or template literals
                if i in line_state:
                    continue
                m = re.search(check["pattern"], line)
                if not m:
                    continue
                # Check if match is inside a single-line string or comment
                if _ts_match_is_in_string(line, m.start()):
                    continue
                # Skip URLs assigned to module-level constants
                if check["id"] == "hardcoded_url" and re.match(
                    r"^(?:export\s+)?(?:const|let|var)\s+[A-Z_][A-Z0-9_]*\s*=", line.strip()
                ):
                    continue
                smell_counts[check["id"]].append({
                    "file": filepath,
                    "line": i + 1,
                    "content": line.strip()[:100],
                })

        # Multi-line smell helpers (brace-tracked)
        _detect_async_no_await(filepath, content, lines, smell_counts)
        _detect_error_no_throw(filepath, lines, smell_counts)
        _detect_empty_if_chains(filepath, lines, smell_counts)
        _detect_dead_useeffects(filepath, lines, smell_counts)
        _detect_swallowed_errors(filepath, content, lines, smell_counts)
        _detect_monster_functions(filepath, lines, smell_counts)
        _detect_dead_functions(filepath, lines, smell_counts)
        _detect_window_globals(filepath, lines, line_state, smell_counts)
        _detect_catch_return_default(filepath, content, smell_counts)

    # Build summary entries sorted by severity then count
    severity_order = {"high": 0, "medium": 1, "low": 2}
    entries = []
    for check in checks:
        matches = smell_counts[check["id"]]
        if matches:
            entries.append({
                "id": check["id"],
                "label": check["label"],
                "severity": check["severity"],
                "count": len(matches),
                "files": len(set(m["file"] for m in matches)),
                "matches": matches[:50],
            })
    entries.sort(key=lambda e: (severity_order.get(e["severity"], 9), -e["count"]))
    return entries, len(files)


# ── Multi-line smell helpers (brace-tracked) ──────────────


def _detect_async_no_await(filepath: str, content: str, lines: list[str],
                           smell_counts: dict[str, list[dict]]):
    """Find async functions that don't use await.

    Algorithm: for each async declaration, track brace depth to find the function
    body extent (up to 200 lines). Scan each line for 'await' within those braces.
    If the opening brace closes (depth returns to 0) without seeing await, flag it.
    """
    async_re = re.compile(r"(?:async\s+function\s+(\w+)|(\w+)\s*=\s*async)")
    for i, line in enumerate(lines):
        m = async_re.search(line)
        if not m:
            continue
        name = m.group(1) or m.group(2)
        brace_depth = 0
        found_open = False
        has_await = False
        for j in range(i, min(i + 200, len(lines))):
            body_line = lines[j]
            for ch in body_line:
                if ch == '{':
                    brace_depth += 1
                    found_open = True
                elif ch == '}':
                    brace_depth -= 1
            if "await " in body_line or "await\n" in body_line:
                has_await = True
            if found_open and brace_depth <= 0:
                break

        if found_open and not has_await:
            smell_counts["async_no_await"].append({
                "file": filepath,
                "line": i + 1,
                "content": f"async {name or '(anonymous)'} has no await",
            })


def _detect_error_no_throw(filepath: str, lines: list[str],
                           smell_counts: dict[str, list[dict]]):
    """Find console.error calls not followed by throw or return."""
    for i, line in enumerate(lines):
        if "console.error" in line:
            following = "\n".join(lines[i+1:i+4])
            if not re.search(r"\b(?:throw|return)\b", following):
                smell_counts["console_error_no_throw"].append({
                    "file": filepath,
                    "line": i + 1,
                    "content": line.strip()[:100],
                })


def _detect_empty_if_chains(filepath: str, lines: list[str],
                            smell_counts: dict[str, list[dict]]):
    """Find if/else chains where all branches are empty."""
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not re.match(r"(?:else\s+)?if\s*\(", stripped):
            i += 1
            continue

        # Single-line: if (...) { }
        if re.match(r"(?:else\s+)?if\s*\([^)]*\)\s*\{\s*\}\s*$", stripped):
            chain_start = i
            j = i + 1
            while j < len(lines):
                next_stripped = lines[j].strip()
                if re.match(r"else\s+if\s*\([^)]*\)\s*\{\s*\}\s*$", next_stripped):
                    j += 1
                    continue
                if re.match(r"(?:\}\s*)?else\s*\{\s*\}\s*$", next_stripped):
                    j += 1
                    continue
                break
            smell_counts["empty_if_chain"].append({
                "file": filepath,
                "line": chain_start + 1,
                "content": stripped[:100],
            })
            i = j
            continue

        # Multi-line: if (...) { followed by } on next non-blank line
        if re.match(r"(?:else\s+)?if\s*\([^)]*\)\s*\{\s*$", stripped):
            chain_start = i
            chain_all_empty = True
            j = i
            while j < len(lines):
                cur = lines[j].strip()
                if j == chain_start:
                    if not re.match(r"(?:else\s+)?if\s*\([^)]*\)\s*\{\s*$", cur):
                        chain_all_empty = False
                        break
                elif re.match(r"\}\s*else\s+if\s*\([^)]*\)\s*\{\s*$", cur):
                    pass
                elif re.match(r"\}\s*else\s*\{\s*$", cur):
                    pass
                elif cur == "}":
                    k = j + 1
                    while k < len(lines) and lines[k].strip() == "":
                        k += 1
                    if k < len(lines) and re.match(r"else\s", lines[k].strip()):
                        j = k
                        continue
                    j += 1
                    break
                elif cur == "":
                    j += 1
                    continue
                else:
                    chain_all_empty = False
                    break
                j += 1

            if chain_all_empty and j > chain_start + 1:
                smell_counts["empty_if_chain"].append({
                    "file": filepath,
                    "line": chain_start + 1,
                    "content": lines[chain_start].strip()[:100],
                })
            i = max(i + 1, j)
            continue

        i += 1


def _detect_dead_useeffects(filepath: str, lines: list[str],
                            smell_counts: dict[str, list[dict]]):
    """Find useEffect calls with empty or whitespace/comment-only bodies.

    Algorithm: two-pass brace/paren tracking with string-escape awareness.
    Pass 1: track paren depth to find the full useEffect(...) extent.
    Pass 2: within that extent, find the arrow body ({...} after =>) using
    brace depth, skipping characters inside string literals (', ", `).
    Then strip comments from the body and check if anything remains.
    """
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not re.match(r"(?:React\.)?useEffect\s*\(\s*\(\s*\)\s*=>\s*\{", stripped):
            continue

        paren_depth = 0
        brace_depth = 0
        end = None
        for j in range(i, min(i + 30, len(lines))):
            in_str = None
            prev_ch = ""
            for ch in lines[j]:
                if in_str:
                    if ch == in_str and prev_ch != "\\":
                        in_str = None
                    prev_ch = ch
                    continue
                if ch in "'\"`":
                    in_str = ch
                elif ch == "(":
                    paren_depth += 1
                elif ch == ")":
                    paren_depth -= 1
                    if paren_depth <= 0:
                        end = j
                        break
                elif ch == "{":
                    brace_depth += 1
                elif ch == "}":
                    brace_depth -= 1
                prev_ch = ch
            if end is not None:
                break

        if end is None:
            continue

        text = "\n".join(lines[i:end + 1])
        arrow_pos = text.find("=>")
        if arrow_pos == -1:
            continue
        brace_pos = text.find("{", arrow_pos)
        if brace_pos == -1:
            continue

        depth = 0
        body_end = None
        in_str = None
        prev_ch = ""
        for ci in range(brace_pos, len(text)):
            ch = text[ci]
            if in_str:
                if ch == in_str and prev_ch != "\\":
                    in_str = None
                prev_ch = ch
                continue
            if ch in "'\"`":
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    body_end = ci
                    break
            prev_ch = ch

        if body_end is None:
            continue

        body = text[brace_pos + 1:body_end]
        body_stripped = re.sub(r"//[^\n]*", "", body)
        body_stripped = re.sub(r"/\*.*?\*/", "", body_stripped, flags=re.DOTALL)
        if body_stripped.strip() == "":
            smell_counts["dead_useeffect"].append({
                "file": filepath,
                "line": i + 1,
                "content": stripped[:100],
            })


def _detect_swallowed_errors(filepath: str, content: str, lines: list[str],
                              smell_counts: dict[str, list[dict]]):
    """Find catch blocks whose only content is console.error/warn/log (swallowed errors).

    Algorithm: regex-find each `catch(...) {`, then track brace depth with
    string-escape awareness to extract the catch body (up to 500 chars).
    Strip comments, split into statements, and check if every statement
    is a console.error/warn/log call.
    """
    catch_re = re.compile(r"catch\s*\([^)]*\)\s*\{")
    for m in catch_re.finditer(content):
        brace_start = m.end() - 1
        depth = 0
        in_str = None
        prev_ch = ""
        body_end = None
        for ci in range(brace_start, min(brace_start + 500, len(content))):
            ch = content[ci]
            if in_str:
                if ch == in_str and prev_ch != "\\":
                    in_str = None
                prev_ch = ch
                continue
            if ch in "'\"`":
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    body_end = ci
                    break
            prev_ch = ch

        if body_end is None:
            continue

        body = content[brace_start + 1:body_end]
        body_clean = re.sub(r"//[^\n]*", "", body)
        body_clean = re.sub(r"/\*.*?\*/", "", body_clean, flags=re.DOTALL)
        body_clean = body_clean.strip()

        if not body_clean:
            continue  # empty catch — caught by empty_catch detector

        statements = [s.strip().rstrip(";") for s in re.split(r"[;\n]", body_clean) if s.strip()]
        if not statements:
            continue

        all_console = all(
            re.match(r"console\.(error|warn|log)\s*\(", stmt)
            for stmt in statements
        )
        if all_console:
            line_no = content[:m.start()].count("\n") + 1
            smell_counts["swallowed_error"].append({
                "file": filepath,
                "line": line_no,
                "content": lines[line_no - 1].strip()[:100] if line_no <= len(lines) else "",
            })


def _track_brace_body(lines: list[str], start_line: int, *, max_scan: int = 2000) -> int | None:
    """Find the closing brace that matches the first opening brace from start_line.

    Tracks brace depth with string-literal awareness (', ", `).
    Returns the line index of the closing brace, or None if not found.
    """
    depth = 0
    found_open = False
    for j in range(start_line, min(start_line + max_scan, len(lines))):
        in_str = None
        prev_ch = ""
        for ch in lines[j]:
            if in_str:
                if ch == in_str and prev_ch != "\\":
                    in_str = None
                prev_ch = ch
                continue
            if ch in "'\"`":
                in_str = ch
            elif ch == "{":
                depth += 1
                found_open = True
            elif ch == "}":
                depth -= 1
                if found_open and depth == 0:
                    return j
            prev_ch = ch
    return None


def _find_function_start(line: str, next_lines: list[str]) -> str | None:
    """Return the function name if this line starts a named function, else None.

    Matches:
    - function foo(...)
    - export function foo(...)
    - export default function foo(...)
    - const foo = (...) => {
    - const foo = async (...) => {
    - const foo = function(...)

    Skips interfaces, types, enums, classes.
    """
    stripped = line.strip()
    if re.match(r"(?:export\s+)?(?:interface|type|enum|class)\s+", stripped):
        return None

    # function declaration
    m = re.match(
        r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
        stripped,
    )
    if m:
        return m.group(1)

    # const/let/var assignment — need to verify it's actually a function
    m = re.match(r"(?:export\s+)?(?:const|let|var)\s+(\w+)", stripped)
    if not m:
        return None
    name = m.group(1)

    # Look at what follows the = sign
    combined = "\n".join([stripped] + [l.strip() for l in next_lines[:2]])
    eq_pos = combined.find("=", m.end())
    if eq_pos == -1:
        return None
    after_eq = combined[eq_pos + 1:].lstrip()

    # Direct function: must start with (, async, or function keyword.
    # Skips function calls like useMemo(...), useRef(...), React.memo(...) that
    # may contain => in their arguments or type annotations.
    if re.match(r"(?:async|function)\b", after_eq):
        return name
    if after_eq.startswith("("):
        # Check that this ( ... ) is followed by => (arrow function params)
        # not just a function call like someFunction(...)
        brace_pos = combined.find("{", eq_pos)
        segment = combined[eq_pos:brace_pos] if brace_pos != -1 else combined[eq_pos:]
        if "=>" in segment:
            return name
    return None


def _detect_monster_functions(filepath: str, lines: list[str],
                              smell_counts: dict[str, list[dict]]):
    """Find functions/components exceeding 150 LOC via brace-tracking.

    Matches: function declarations, named arrow functions, and React components.
    Skips: interfaces, types, enums, and objects/arrays.
    """
    for i, line in enumerate(lines):
        name = _find_function_start(line, lines[i + 1:i + 3])
        if not name:
            continue

        # Find opening brace on this or next few lines
        brace_line = None
        for k in range(i, min(i + 5, len(lines))):
            if "{" in lines[k]:
                brace_line = k
                break
        if brace_line is None:
            continue

        end_line = _track_brace_body(lines, brace_line, max_scan=2000)
        if end_line is not None:
            loc = end_line - i + 1
            if loc > 150:
                smell_counts["monster_function"].append({
                    "file": filepath,
                    "line": i + 1,
                    "content": f"{name}() — {loc} LOC",
                })


def _detect_dead_functions(filepath: str, lines: list[str],
                           smell_counts: dict[str, list[dict]]):
    """Find functions with empty body or only return/return null.

    Matches function declarations and named arrow functions.
    Skips decorated functions (TS decorators on line above).
    """
    for i, line in enumerate(lines):
        # Skip decorated functions
        if i > 0 and lines[i - 1].strip().startswith("@"):
            continue

        name = _find_function_start(line, lines[i + 1:i + 3])
        if not name:
            continue

        # Find opening brace
        brace_line = None
        for k in range(i, min(i + 5, len(lines))):
            if "{" in lines[k]:
                brace_line = k
                break
        if brace_line is None:
            continue

        end_line = _track_brace_body(lines, brace_line, max_scan=30)
        if end_line is None:
            continue

        # Extract body between braces
        body_text = "\n".join(lines[brace_line:end_line + 1])
        first_brace = body_text.find("{")
        last_brace = body_text.rfind("}")
        if first_brace == -1 or last_brace == -1 or first_brace >= last_brace:
            continue

        body = body_text[first_brace + 1:last_brace]
        # Strip comments
        body_clean = re.sub(r"//[^\n]*", "", body)
        body_clean = re.sub(r"/\*.*?\*/", "", body_clean, flags=re.DOTALL)
        body_clean = body_clean.strip().rstrip(";")

        if body_clean in ("", "return", "return null", "return undefined"):
            label = body_clean or "empty"
            smell_counts["dead_function"].append({
                "file": filepath,
                "line": i + 1,
                "content": f"{name}() — body is {label}",
            })


def _detect_window_globals(filepath: str, lines: list[str],
                           line_state: dict[int, str],
                           smell_counts: dict[str, list[dict]]):
    """Find window.__* assignments — global state escape hatches.

    Matches:
    - window.__foo = ...
    - (window as any).__foo = ...
    - window['__foo'] = ...
    """
    window_re = re.compile(
        r"""(?:"""
        r"""\(?\s*window\s+as\s+any\s*\)?\s*\.\s*(__\w+)"""   # (window as any).__name
        r"""|window\s*\.\s*(__\w+)"""                           # window.__name
        r"""|window\s*\[\s*['"](__\w+)['"]\s*\]"""              # window['__name']
        r""")\s*=""",
    )
    for i, line in enumerate(lines):
        if i in line_state:
            continue
        m = window_re.search(line)
        if not m:
            continue
        if _ts_match_is_in_string(line, m.start()):
            continue
        name = m.group(1) or m.group(2) or m.group(3)
        smell_counts["window_global"].append({
            "file": filepath,
            "line": i + 1,
            "content": line.strip()[:100],
        })


def _detect_catch_return_default(filepath: str, content: str,
                                  smell_counts: dict[str, list[dict]]):
    """Find catch blocks that return object literals with default/no-op values.

    Catches the pattern:
      catch (...) { ... return { key: false, key: null, key: () => {} }; }

    This is a silent failure — the caller gets valid-looking data but the
    operation actually failed.
    """
    catch_re = re.compile(r"catch\s*\([^)]*\)\s*\{")
    for m in catch_re.finditer(content):
        brace_start = m.end() - 1
        depth = 0
        in_str = None
        prev_ch = ""
        body_end = None
        for ci in range(brace_start, min(brace_start + 1000, len(content))):
            ch = content[ci]
            if in_str:
                if ch == in_str and prev_ch != "\\":
                    in_str = None
                prev_ch = ch
                continue
            if ch in "'\"`":
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    body_end = ci
                    break
            prev_ch = ch

        if body_end is None:
            continue

        body = content[brace_start + 1:body_end]
        # Check if body contains "return {" — a return with object literal
        return_obj = re.search(r"\breturn\s*\{", body)
        if not return_obj:
            continue

        # Extract the returned object content
        obj_start = body.find("{", return_obj.start())
        obj_depth = 0
        obj_end = None
        ois = None
        prev = ""
        for ci in range(obj_start, len(body)):
            ch = body[ci]
            if ois:
                if ch == ois and prev != "\\":
                    ois = None
                prev = ch
                continue
            if ch in "'\"`":
                ois = ch
            elif ch == "{":
                obj_depth += 1
            elif ch == "}":
                obj_depth -= 1
                if obj_depth == 0:
                    obj_end = ci
                    break
            prev = ch

        if obj_end is None:
            continue

        obj_content = body[obj_start + 1:obj_end]
        # Count default/no-op fields
        noop_count = len(re.findall(r"\(\)\s*=>\s*\{\s*\}", obj_content))  # () => {}
        false_count = len(re.findall(r":\s*(?:false|null|undefined|0|''|\"\")\b", obj_content))
        default_fields = noop_count + false_count

        if default_fields >= 2:
            line_no = content[:m.start()].count("\n") + 1
            lines = content.splitlines()
            smell_counts["catch_return_default"].append({
                "file": filepath,
                "line": line_no,
                "content": lines[line_no - 1].strip()[:100] if line_no <= len(lines) else "",
            })
