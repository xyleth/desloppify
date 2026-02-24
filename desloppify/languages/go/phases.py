"""Go detector phase runners.

Originally contributed by tinker495 (KyuSeok Jung) in PR #128.
Enhanced with Go-specific smell detectors and god package detection.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from desloppify.engine.detectors.base import ComplexitySignal
from desloppify.engine.policy.zones import adjust_potential
from desloppify.languages._framework.base.shared_phases import run_structural_phase
from desloppify.languages._framework.runtime import LangRun
from desloppify.state import make_finding
from desloppify.utils import log

GO_COMPLEXITY_SIGNALS = [
    ComplexitySignal(
        "if/else branches",
        r"\b(?:if|else\s+if|else)\b",
        weight=1,
        threshold=25,
    ),
    ComplexitySignal(
        "switch/case",
        r"\b(?:switch|case)\b",
        weight=1,
        threshold=10,
    ),
    ComplexitySignal(
        "select blocks",
        r"\bselect\b",
        weight=2,
        threshold=5,
    ),
    ComplexitySignal(
        "for loops",
        r"\bfor\b",
        weight=1,
        threshold=15,
    ),
    ComplexitySignal(
        "goroutines",
        r"\bgo\s+(?:func\b|\w+\()",
        weight=2,
        threshold=5,
    ),
    ComplexitySignal(
        "channels",
        r"\bchan\s+",
        weight=2,
        threshold=3,
    ),
    ComplexitySignal(
        "defer",
        r"\bdefer\b",
        weight=1,
        threshold=10,
    ),
    ComplexitySignal(
        "type assertions",
        r"\.\(\w",
        weight=2,
        threshold=3,
    ),
    ComplexitySignal(
        "TODOs",
        r"(?m)//\s*(?:TODO|FIXME|HACK|XXX)",
        weight=2,
        threshold=0,
    ),
]

GO_GOD_PACKAGE_NAMES = {"util", "utils", "common", "misc", "helpers", "base", "shared"}


def _detect_god_packages(path: Path, lang: LangRun) -> list[dict]:
    """Detect god packages: bad names or too many exported symbols."""
    files = lang.file_finder(path) if lang.file_finder else []
    pkg_dirs: dict[str, list[str]] = {}
    for f in files:
        d = os.path.dirname(f)
        pkg_dirs.setdefault(d, []).append(f)

    entries = []
    export_re = re.compile(r"^(?:func|type|var|const)\s+([A-Z]\w*)", re.MULTILINE)

    for pkg_dir, pkg_files in pkg_dirs.items():
        pkg_name = os.path.basename(pkg_dir)
        reasons = []

        if pkg_name.lower() in GO_GOD_PACKAGE_NAMES:
            reasons.append(f"generic name '{pkg_name}'")

        exported = set()
        for filepath in pkg_files:
            if filepath.endswith("_test.go"):
                continue
            try:
                content = Path(filepath).read_text(errors="replace")
            except OSError:
                continue
            for m in export_re.finditer(content):
                exported.add(m.group(1))

        if len(exported) > 40:
            reasons.append(f"{len(exported)} exported symbols")

        if reasons:
            entries.append(
                {
                    "file": pkg_files[0],
                    "package": pkg_name,
                    "summary": f"God package '{pkg_name}': {', '.join(reasons)}",
                    "detail": {
                        "package": pkg_name,
                        "reasons": reasons,
                        "exported_count": len(exported),
                    },
                }
            )

    return entries


def _phase_structural(path: Path, lang: LangRun) -> tuple[list[dict], dict[str, int]]:
    """Run structural detectors (large/complexity/flat directories/god packages)."""
    results, potentials = run_structural_phase(
        path,
        lang,
        complexity_signals=GO_COMPLEXITY_SIGNALS,
        log_fn=log,
    )

    # Go-specific: god package detection
    god_pkg_entries = _detect_god_packages(path, lang)
    for e in god_pkg_entries:
        results.append(
            make_finding(
                "structural",
                e["file"],
                f"god_package::{e['package']}",
                tier=4,
                confidence="medium",
                summary=e["summary"],
                detail=e["detail"],
            )
        )
    if god_pkg_entries:
        log(f"         god packages: {len(god_pkg_entries)} findings")

    return results, potentials


def _phase_smells(path: Path, lang: LangRun) -> tuple[list[dict], dict[str, int]]:
    """Run Go-specific smell detectors."""
    from desloppify.languages.go.detectors.smells import detect_smells

    entries, total_files = detect_smells(path)

    results = []
    for entry in entries:
        first_match = entry["matches"][0] if entry["matches"] else {}
        results.append(
            make_finding(
                "smells",
                first_match.get("file", ""),
                f"go_smell::{entry['id']}",
                tier=2 if entry["severity"] == "high" else 3,
                confidence="medium",
                summary=f"{entry['label']} ({entry['count']} occurrences in {entry['files']} files)",
                detail={
                    "smell_id": entry["id"],
                    "severity": entry["severity"],
                    "count": entry["count"],
                    "files": entry["files"],
                    "matches": entry["matches"][:10],
                },
            )
        )

    if results:
        log(f"         go smells: {len(results)} smell types detected")

    return results, {"smells": adjust_potential(lang.zone_map, total_files)}
