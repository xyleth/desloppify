"""review command: prepare or import subjective code review findings."""

import json
import sys
from pathlib import Path

from ..utils import c


def cmd_review(args):
    """Prepare or import subjective code review findings."""
    from ..state import load_state, save_state
    from ..cli import _state_path, _write_query, _resolve_lang

    sp = _state_path(args)
    state = load_state(sp)
    lang = _resolve_lang(args)

    if not lang:
        print(c("  Error: could not detect language. Use --lang.", "red"), file=sys.stderr)
        sys.exit(1)

    import_file = getattr(args, "import_file", None)

    if import_file:
        _do_import(import_file, state, lang, sp)
    else:
        _do_prepare(args, state, lang, sp)


def _do_prepare(args, state, lang, sp):
    """Prepare mode: compute what needs review, output to query.json."""
    from ..cli import _write_query
    from ..review import prepare_review

    path = Path(args.path)
    max_files = getattr(args, "max_files", 50)
    max_age = getattr(args, "max_age", 30)
    force_refresh = getattr(args, "refresh", False)

    dims_str = getattr(args, "dimensions", None)
    dimensions = dims_str.split(",") if dims_str else None

    # Build zone map and dep graph (required for file selection and context)
    # _setup_lang returns the file list so we can pass it through (avoids re-walking)
    found_files = _setup_lang(lang, path, state)

    data = prepare_review(
        path, lang, state,
        max_files=max_files,
        max_age_days=max_age,
        force_refresh=force_refresh,
        dimensions=dimensions,
        files=found_files or None,
    )

    _write_query(data)
    print(c(f"\n  Review prepared: {data['total_candidates']} files to review", "bold"))
    print(c(f"  Cache: {data['cache_status']['fresh']} fresh, "
            f"{data['cache_status']['stale']} stale, "
            f"{data['cache_status']['new']} new", "dim"))
    print(c(f"  Dimensions: {', '.join(data['dimensions'])}", "dim"))
    print(c(f"\n  \u2192 query.json updated. "
            f"Review files, then: desloppify review --import findings.json", "cyan"))


def _do_import(import_file, state, lang, sp):
    """Import mode: ingest agent-produced findings."""
    from ..state import save_state
    from ..review import import_review_findings

    findings_path = Path(import_file)
    if not findings_path.exists():
        print(c(f"  Error: file not found: {import_file}", "red"), file=sys.stderr)
        sys.exit(1)

    try:
        findings_data = json.loads(findings_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(c(f"  Error reading findings: {e}", "red"), file=sys.stderr)
        sys.exit(1)

    if not isinstance(findings_data, list):
        print(c("  Error: findings file must contain a JSON array", "red"), file=sys.stderr)
        sys.exit(1)

    diff = import_review_findings(findings_data, state, lang.name)
    save_state(state, sp)

    print(c(f"\n  Review imported:", "bold"))
    print(c(f"  +{diff['new']} new findings, "
            f"{diff['auto_resolved']} resolved, "
            f"{diff['reopened']} reopened", "dim"))
    print(c(f"\n  Run: desloppify show review", "cyan"))


def _setup_lang(lang, path: Path, state: dict) -> list[str]:
    """Build zone map and dep graph for the language config.

    Returns the file list from file_finder (so callers can reuse it).
    """
    files: list[str] = []

    # Build zone map
    if lang.zone_rules and lang.file_finder:
        from ..zones import FileZoneMap
        from ..utils import rel
        files = lang.file_finder(path)
        zone_overrides = state.get("config", {}).get("zone_overrides") or None
        lang._zone_map = FileZoneMap(files, lang.zone_rules, rel_fn=rel,
                                      overrides=zone_overrides)

    # Build dep graph
    if lang.build_dep_graph and lang._dep_graph is None:
        try:
            lang._dep_graph = lang.build_dep_graph(path)
        except Exception:
            pass  # Non-fatal — context will just lack dep graph info

    return files
