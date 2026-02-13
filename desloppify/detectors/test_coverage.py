"""Test coverage gap detection — static analysis of test file mapping and quality.

Measures test *need* (what's dangerous without tests) not just test existence,
weighting by blast radius (importer count) so that testing one critical file
moves the score more than testing ten trivial ones.
"""

from __future__ import annotations

import os
import re
from collections import deque
from pathlib import Path

from ..utils import SRC_PATH
from ..zones import FileZoneMap, Zone

# ── Assertion / mock / snapshot patterns ──────────────────

PY_ASSERT_PATTERNS = [
    re.compile(p) for p in [
        r"^\s*assert\s+", r"self\.assert\w+\(", r"pytest\.raises\(",
        r"\.assert_called", r"\.assert_not_called",
    ]
]
TS_ASSERT_PATTERNS = [
    re.compile(p) for p in [
        r"expect\(", r"assert\.", r"\.should\.",
        r"\b(?:getBy|findBy|getAllBy|findAllBy)\w+\(",
        r"\bwaitFor\(",
        r"\.toBeInTheDocument\(",
        r"\.toBeVisible\(",
        r"\.toHaveTextContent\(",
        r"\.toHaveAttribute\(",
    ]
]
PY_MOCK_PATTERNS = [
    re.compile(p) for p in [
        r"@(?:mock\.)?patch", r"Mock\(\)", r"MagicMock\(\)", r"mocker\.", r"monkeypatch\.",
    ]
]
TS_MOCK_PATTERNS = [
    re.compile(p) for p in [
        r"jest\.mock\(", r"jest\.spyOn\(", r"vi\.mock\(", r"vi\.spyOn\(", r"sinon\.",
    ]
]
TS_SNAPSHOT_PATTERNS = [
    re.compile(p) for p in [
        r"toMatchSnapshot", r"toMatchInlineSnapshot",
    ]
]

PY_TEST_FUNC = re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)\s*\(")
TS_TEST_FUNC = re.compile(r"""(?:it|test)\s*\(\s*['"]""")

# Minimum LOC threshold — tiny files don't need dedicated tests
_MIN_LOC = 10

# Max untested modules to report when there are zero tests
_MAX_NO_TESTS_ENTRIES = 50


def detect_test_coverage(
    graph: dict,
    zone_map: FileZoneMap,
    lang_name: str,
    extra_test_files: set[str] | None = None,
) -> tuple[list[dict], int]:
    """Detect test coverage gaps.

    Args:
        graph: dep graph from lang.build_dep_graph — {filepath: {"imports": set, "importer_count": int, ...}}
        zone_map: FileZoneMap from lang._zone_map
        lang_name: "python" or "typescript"
        extra_test_files: test files outside the scanned path (e.g. PROJECT_ROOT/tests/)

    Returns:
        (entries, potential) where entries are finding-like dicts and potential
        is the count of production files (for scoring denominator).
    """
    all_files = zone_map.all_files()
    production_files = set(zone_map.include_only(all_files, Zone.PRODUCTION, Zone.SCRIPT))
    test_files = set(zone_map.include_only(all_files, Zone.TEST))

    # Include test files from outside the scanned path
    if extra_test_files:
        test_files |= extra_test_files

    # Only score production files that are substantial enough to warrant tests
    scorable = {f for f in production_files if _file_loc(f) >= _MIN_LOC}
    potential = len(scorable)

    if potential == 0:
        return [], 0

    # If zero test files, emit findings for top modules by LOC
    if not test_files:
        entries = _no_tests_findings(scorable, graph)
        return entries, potential

    # Step 1: Import-based mapping (precise)
    directly_tested = _import_based_mapping(graph, test_files, production_files)

    # Step 2: Naming convention fallback
    name_tested = _naming_based_mapping(test_files, production_files, lang_name)
    directly_tested |= name_tested

    # Step 3: Transitive coverage via BFS
    transitively_tested = _transitive_coverage(directly_tested, graph, production_files)

    # Step 4: Test quality analysis
    test_quality = _analyze_test_quality(test_files, lang_name)

    # Step 5: Generate findings
    entries = _generate_findings(
        scorable, directly_tested, transitively_tested,
        test_quality, graph, lang_name,
    )

    return entries, potential


# ── Internal helpers ──────────────────────────────────────


def _file_loc(filepath: str) -> int:
    """Count lines in a file, returning 0 on error."""
    try:
        return len(Path(filepath).read_text().splitlines())
    except (OSError, UnicodeDecodeError):
        return 0


def _no_tests_findings(
    scorable: set[str], graph: dict,
) -> list[dict]:
    """Generate findings when there are zero test files."""
    # Sort by LOC descending, take top N
    by_loc = sorted(scorable, key=lambda f: -_file_loc(f))
    entries = []
    for f in by_loc[:_MAX_NO_TESTS_ENTRIES]:
        loc = _file_loc(f)
        ic = graph.get(f, {}).get("importer_count", 0)
        entries.append({
            "file": f,
            "name": "",
            "tier": 2 if ic >= 10 else 3,
            "confidence": "high",
            "summary": f"Untested module ({loc} LOC, {ic} importers) — no test files found",
            "detail": {"kind": "untested_module", "loc": loc, "importer_count": ic},
        })
    return entries


def _import_based_mapping(
    graph: dict, test_files: set[str], production_files: set[str],
) -> set[str]:
    """Map test files to production files via import edges.

    For test files in the graph, uses the graph's import edges.
    For test files NOT in the graph (external), reads the file and parses
    Python/TS import statements to find references to production files.
    """
    tested = set()
    # Build basename→paths index for fuzzy resolution
    prod_by_module: dict[str, str] = {}
    for pf in production_files:
        # Map module-style paths: "desloppify/utils.py" → "desloppify.utils"
        mod = pf.replace("/", ".").replace("\\", ".")
        if mod.endswith(".py"):
            mod = mod[:-3]
        elif mod.endswith(".ts") or mod.endswith(".tsx"):
            mod = mod.rsplit(".", 1)[0]
        prod_by_module[mod] = pf
        # __init__.py: also map the package path (e.g. "desloppify.lang" → __init__.py)
        if mod.endswith(".__init__"):
            prod_by_module[mod[:-len(".__init__")]] = pf
        # Also map just the final module name: "utils" → path
        parts = mod.split(".")
        if parts:
            prod_by_module[parts[-1]] = pf

    for tf in test_files:
        entry = graph.get(tf)
        if entry is not None:
            for imp in entry.get("imports", set()):
                if imp in production_files:
                    tested.add(imp)
        else:
            # External test file: parse imports from source
            tested |= _parse_test_imports(tf, production_files, prod_by_module)

    # Expand barrel files (index.ts/index.tsx) — one level deep
    barrel_files = [
        f for f in tested
        if os.path.basename(f) in ("index.ts", "index.tsx")
    ]
    for bf in barrel_files:
        tested |= _resolve_barrel_reexports(bf, production_files)

    return tested


_PY_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE
)
_TS_IMPORT_RE = re.compile(
    r"""(?:from|import)\s+['"]([^'"]+)['"]""", re.MULTILINE
)


_TS_EXTENSIONS = ["", ".ts", ".tsx", "/index.ts", "/index.tsx"]


def _resolve_ts_import(
    spec: str, test_path: str, production_files: set[str],
) -> str | None:
    """Resolve a TS import specifier to a production file path.

    Handles @/ and ~/ aliases (via SRC_PATH), relative paths (./  ../),
    and probes common extensions (.ts, .tsx, /index.ts, /index.tsx).
    """
    if spec.startswith("@/") or spec.startswith("~/"):
        base = Path(str(SRC_PATH) + "/" + spec[2:])
    elif spec.startswith("."):
        test_dir = Path(test_path).parent
        base = (test_dir / spec).resolve()
    else:
        return None

    for ext in _TS_EXTENSIONS:
        candidate = str(Path(str(base) + ext))
        if candidate in production_files:
            return candidate
        # Also try resolving symlinks / normalising for on-disk check
        try:
            resolved = str(Path(str(base) + ext).resolve())
            if resolved in production_files:
                return resolved
        except OSError:
            pass
    return None


_REEXPORT_RE = re.compile(
    r"""^export\s+(?:\{[^}]*\}|\*)\s+from\s+['"]([^'"]+)['"]""", re.MULTILINE
)


def _resolve_barrel_reexports(
    filepath: str, production_files: set[str],
) -> set[str]:
    """Resolve re-exports from a barrel file (index.ts/index.tsx).

    One level deep only — no recursive barrel chaining.
    Returns the set of production files re-exported by this barrel.
    """
    try:
        content = Path(filepath).read_text()
    except (OSError, UnicodeDecodeError):
        return set()

    results = set()
    for m in _REEXPORT_RE.finditer(content):
        spec = m.group(1)
        resolved = _resolve_ts_import(spec, filepath, production_files)
        if resolved:
            results.add(resolved)
    return results


def _parse_test_imports(
    test_path: str, production_files: set[str], prod_by_module: dict[str, str],
) -> set[str]:
    """Parse import statements from a test file and resolve to production files."""
    tested = set()
    try:
        content = Path(test_path).read_text()
    except (OSError, UnicodeDecodeError):
        return tested

    # Try Python imports
    for m in _PY_IMPORT_RE.finditer(content):
        module = m.group(1) or m.group(2)
        if not module:
            continue
        # Try full module path and progressively shorter prefixes
        parts = module.split(".")
        for i in range(len(parts), 0, -1):
            candidate = ".".join(parts[:i])
            if candidate in prod_by_module:
                tested.add(prod_by_module[candidate])
                break

    # Try TS imports
    for m in _TS_IMPORT_RE.finditer(content):
        spec = m.group(1)
        if not spec:
            continue
        # First try proper resolution (relative paths, @/ alias)
        resolved = _resolve_ts_import(spec, test_path, production_files)
        if resolved:
            tested.add(resolved)
            continue
        # Fallback: fuzzy module lookup
        cleaned = spec.lstrip("./").replace("/", ".")
        if cleaned in prod_by_module:
            tested.add(prod_by_module[cleaned])

    return tested


def _map_test_to_source(
    test_path: str, production_set: set[str], lang_name: str,
) -> str | None:
    """Try to match a test file to a production file by naming convention."""
    basename = os.path.basename(test_path)
    dirname = os.path.dirname(test_path)
    parent = os.path.dirname(dirname)

    candidates: list[str] = []

    if lang_name == "python":
        # test_X.py → X.py
        if basename.startswith("test_"):
            src = basename[5:]
            candidates.append(os.path.join(dirname, src))
            if parent:
                candidates.append(os.path.join(parent, src))
        # X_test.py → X.py
        if basename.endswith("_test.py"):
            src = basename[:-8] + ".py"
            candidates.append(os.path.join(dirname, src))
            if parent:
                candidates.append(os.path.join(parent, src))
    else:  # typescript
        # X.test.ts → X.ts, X.test.tsx → X.tsx
        for pattern in (".test.", ".spec."):
            if pattern in basename:
                src = basename.replace(pattern, ".")
                candidates.append(os.path.join(dirname, src))
                if parent:
                    candidates.append(os.path.join(parent, src))
        # __tests__/X.ts → ../X.ts
        dir_basename = os.path.basename(dirname)
        if dir_basename == "__tests__" and parent:
            candidates.append(os.path.join(parent, basename))

    # Fuzzy: strip test/spec suffix and try matching basename
    for prod in production_set:
        prod_base = os.path.basename(prod)
        for c in candidates:
            if os.path.basename(c) == prod_base:
                # Check if the candidate path matches (same dir or parent)
                if prod in production_set:
                    return prod

    # Direct path match
    for c in candidates:
        if c in production_set:
            return c

    return None


def _naming_based_mapping(
    test_files: set[str], production_files: set[str], lang_name: str,
) -> set[str]:
    """Map test files to production files by naming conventions."""
    tested = set()
    # Build basename → set of full paths for fast lookup
    prod_by_basename: dict[str, list[str]] = {}
    for p in production_files:
        bn = os.path.basename(p)
        prod_by_basename.setdefault(bn, []).append(p)

    for tf in test_files:
        matched = _map_test_to_source(tf, production_files, lang_name)
        if matched:
            tested.add(matched)
            continue

        # Fallback: fuzzy basename matching
        basename = os.path.basename(tf)
        src_name = _strip_test_markers(basename, lang_name)
        if src_name and src_name in prod_by_basename:
            for p in prod_by_basename[src_name]:
                tested.add(p)

    return tested


def _strip_test_markers(basename: str, lang_name: str) -> str | None:
    """Strip test naming markers from a basename to get the source name."""
    if lang_name == "python":
        if basename.startswith("test_"):
            return basename[5:]
        if basename.endswith("_test.py"):
            return basename[:-8] + ".py"
    else:
        for marker in (".test.", ".spec."):
            if marker in basename:
                return basename.replace(marker, ".")
    return None


def _transitive_coverage(
    directly_tested: set[str],
    graph: dict,
    production_files: set[str],
) -> set[str]:
    """BFS from directly-tested files through dep graph imports.

    Returns production files reachable from tested files (transitively covered).
    """
    visited = set(directly_tested)
    queue = deque(directly_tested)

    while queue:
        current = queue.popleft()
        entry = graph.get(current)
        if entry is None:
            continue
        for imp in entry.get("imports", set()):
            if imp in production_files and imp not in visited:
                visited.add(imp)
                queue.append(imp)

    # Transitively covered = reachable but NOT directly tested
    return visited - directly_tested


def _strip_py_comment(line: str) -> str:
    """Strip Python # comments while respecting string literals."""
    in_str = None
    for i, ch in enumerate(line):
        if in_str:
            if ch == '\\' and i + 1 < len(line):
                continue  # skip escaped char (next iteration handles it)
            if ch == in_str:
                in_str = None
        elif ch in ('"', "'"):
            in_str = ch
        elif ch == '#' and not in_str:
            return line[:i]
    return line


def _analyze_test_quality(
    test_files: set[str], lang_name: str,
) -> dict[str, dict]:
    """Analyze quality of each test file.

    Returns {test_path: {"assertions": int, "mocks": int, "test_functions": int,
                          "snapshots": int, "quality": str}}
    """
    assert_pats = PY_ASSERT_PATTERNS if lang_name == "python" else TS_ASSERT_PATTERNS
    mock_pats = PY_MOCK_PATTERNS if lang_name == "python" else TS_MOCK_PATTERNS
    test_func_re = PY_TEST_FUNC if lang_name == "python" else TS_TEST_FUNC

    quality_map: dict[str, dict] = {}

    for tf in test_files:
        try:
            content = Path(tf).read_text()
        except (OSError, UnicodeDecodeError):
            continue

        # Strip comments before pattern matching
        if lang_name != "python":
            from ..lang.typescript.detectors._smell_helpers import _strip_ts_comments
            stripped = _strip_ts_comments(content)
        else:
            stripped = "\n".join(_strip_py_comment(line) for line in content.splitlines())

        lines = stripped.splitlines()

        # Use any() per line to avoid double-counting when multiple patterns
        # match the same line (e.g. expect(el).toBeVisible() matching both)
        assertions = sum(
            1 for line in lines
            if any(pat.search(line) for pat in assert_pats)
        )
        mocks = sum(
            1 for line in lines
            if any(pat.search(line) for pat in mock_pats)
        )
        snapshots = sum(
            1 for line in lines
            if any(pat.search(line) for pat in TS_SNAPSHOT_PATTERNS)
        ) if lang_name != "python" else 0

        test_functions = len(test_func_re.findall(stripped))

        # Classify quality
        if test_functions == 0:
            quality = "no_tests"
        elif assertions == 0:
            quality = "assertion_free"
        elif mocks > assertions:
            quality = "over_mocked"
        elif snapshots > 0 and snapshots > assertions * 0.5:
            quality = "snapshot_heavy"
        elif test_functions > 0 and assertions / test_functions < 1:
            quality = "smoke"
        elif assertions / test_functions >= 3:
            quality = "thorough"
        else:
            quality = "adequate"

        quality_map[tf] = {
            "assertions": assertions,
            "mocks": mocks,
            "test_functions": test_functions,
            "snapshots": snapshots,
            "quality": quality,
        }

    return quality_map


def _get_test_files_for_prod(
    prod_file: str,
    test_files: set[str],
    graph: dict,
    lang_name: str,
) -> list[str]:
    """Find which test files test a given production file."""
    result = []
    for tf in test_files:
        entry = graph.get(tf)
        if entry and prod_file in entry.get("imports", set()):
            result.append(tf)
            continue
        # Naming match
        if _map_test_to_source(tf, {prod_file}, lang_name) == prod_file:
            result.append(tf)
    return result


def _generate_findings(
    scorable: set[str],
    directly_tested: set[str],
    transitively_tested: set[str],
    test_quality: dict[str, dict],
    graph: dict,
    lang_name: str,
) -> list[dict]:
    """Generate test coverage findings from the analysis results."""
    entries: list[dict] = []

    # Collect all test files for mapping
    test_files = set(test_quality.keys())

    for f in scorable:
        loc = _file_loc(f)
        ic = graph.get(f, {}).get("importer_count", 0)

        if f in directly_tested:
            # Check quality of the test(s) for this file
            related_tests = _get_test_files_for_prod(f, test_files, graph, lang_name)
            for tf in related_tests:
                tq = test_quality.get(tf)
                if tq is None:
                    continue

                if tq["quality"] == "assertion_free":
                    entries.append({
                        "file": f,
                        "name": f"assertion_free::{os.path.basename(tf)}",
                        "tier": 3,
                        "confidence": "medium",
                        "summary": (f"Assertion-free test: {os.path.basename(tf)} "
                                    f"has {tq['test_functions']} test functions but 0 assertions"),
                        "detail": {"kind": "assertion_free_test", "test_file": tf,
                                   "test_functions": tq["test_functions"]},
                    })
                elif tq["quality"] == "smoke":
                    entries.append({
                        "file": f,
                        "name": f"shallow::{os.path.basename(tf)}",
                        "tier": 3,
                        "confidence": "medium",
                        "summary": (f"Shallow tests: {os.path.basename(tf)} has "
                                    f"{tq['assertions']} assertions across "
                                    f"{tq['test_functions']} test functions"),
                        "detail": {"kind": "shallow_tests", "test_file": tf,
                                   "assertions": tq["assertions"],
                                   "test_functions": tq["test_functions"]},
                    })
                elif tq["quality"] == "over_mocked":
                    entries.append({
                        "file": f,
                        "name": f"over_mocked::{os.path.basename(tf)}",
                        "tier": 3,
                        "confidence": "low",
                        "summary": (f"Over-mocked tests: {os.path.basename(tf)} has "
                                    f"{tq['mocks']} mocks vs {tq['assertions']} assertions"),
                        "detail": {"kind": "over_mocked", "test_file": tf,
                                   "mocks": tq["mocks"], "assertions": tq["assertions"]},
                    })
                elif tq["quality"] == "snapshot_heavy" and lang_name != "python":
                    entries.append({
                        "file": f,
                        "name": f"snapshot_heavy::{os.path.basename(tf)}",
                        "tier": 3,
                        "confidence": "low",
                        "summary": (f"Snapshot-heavy tests: {os.path.basename(tf)} has "
                                    f"{tq['snapshots']} snapshots vs {tq['assertions']} assertions"),
                        "detail": {"kind": "snapshot_heavy", "test_file": tf,
                                   "snapshots": tq["snapshots"],
                                   "assertions": tq["assertions"]},
                    })

        elif f in transitively_tested:
            entries.append({
                "file": f,
                "name": "transitive_only",
                "tier": 2 if ic >= 10 else 3,
                "confidence": "medium",
                "summary": (f"No direct tests ({loc} LOC, {ic} importers) "
                            f"— covered only via imports from tested modules"),
                "detail": {"kind": "transitive_only", "loc": loc, "importer_count": ic},
            })

        else:
            # Untested
            if ic >= 10:
                entries.append({
                    "file": f,
                    "name": "untested_critical",
                    "tier": 2,
                    "confidence": "high",
                    "summary": (f"Untested critical module ({loc} LOC, {ic} importers) "
                                f"— high blast radius"),
                    "detail": {"kind": "untested_critical", "loc": loc, "importer_count": ic},
                })
            else:
                entries.append({
                    "file": f,
                    "name": "untested_module",
                    "tier": 3,
                    "confidence": "high",
                    "summary": f"Untested module ({loc} LOC, {ic} importers)",
                    "detail": {"kind": "untested_module", "loc": loc, "importer_count": ic},
                })

    return entries
