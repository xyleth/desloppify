"""Go-specific security detectors — SQL injection, command injection, path traversal."""

from __future__ import annotations

import re
from pathlib import Path

from desloppify.engine.detectors.security import rules as security_rules_mod
from desloppify.engine.policy.zones import FileZoneMap, Zone


def _make_entry(
    filepath: str,
    line_num: int,
    line: str,
    *,
    check_id: str,
    summary: str,
    severity: str,
    confidence: str,
    remediation: str,
) -> dict:
    return security_rules_mod.make_security_entry(
        filepath,
        line_num,
        line,
        security_rules_mod.SecurityRule(
            check_id=check_id,
            summary=summary,
            severity=severity,
            confidence=confidence,
            remediation=remediation,
        ),
    )


def detect_go_security(
    files: list[str],
    zone_map: FileZoneMap | None,
) -> tuple[list[dict], int]:
    """Detect Go-specific security issues. Returns (entries, files_scanned)."""
    entries: list[dict] = []
    scanned = 0

    for filepath in files:
        if not filepath.endswith(".go"):
            continue
        if filepath.endswith("_test.go"):
            continue
        if zone_map is not None:
            zone = zone_map.get(filepath)
            if zone in (Zone.GENERATED, Zone.VENDOR):
                continue

        try:
            content = Path(filepath).read_text(errors="replace")
        except OSError:
            continue

        scanned += 1
        lines = content.splitlines()

        for line_num, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith("//"):
                continue

            _check_sql_injection(filepath, line_num, line, entries)
            _check_command_injection(filepath, line_num, line, entries)
            _check_path_traversal(filepath, line_num, line, entries)

    return entries, scanned


_SQL_INJECT_RE = re.compile(
    r"(?:db|tx)\.\s*(?:Query|Exec|QueryRow|QueryContext|ExecContext)\s*\("
)
_SQL_FORMAT_RE = re.compile(r"(?:fmt\.Sprintf|\"\s*\+\s*\w|\bfmt\.Fprintf)")


def _check_sql_injection(
    filepath: str, line_num: int, line: str, entries: list[dict]
):
    """Detect SQL queries built with string formatting."""
    if _SQL_INJECT_RE.search(line):
        if _SQL_FORMAT_RE.search(line) or "+" in line:
            entries.append(
                _make_entry(
                    filepath,
                    line_num,
                    line,
                    check_id="sql_injection",
                    summary="SQL injection risk: query built with string formatting",
                    severity="critical",
                    confidence="high",
                    remediation='Use parameterized queries: db.Query("SELECT ... WHERE id = $1", id)',
                )
            )


_EXEC_CMD_RE = re.compile(r"exec\.Command\s*\(")


def _check_command_injection(
    filepath: str, line_num: int, line: str, entries: list[dict]
):
    """Detect exec.Command with dynamic arguments."""
    if _EXEC_CMD_RE.search(line):
        stripped = line.strip()
        if not re.search(r'exec\.Command\s*\(\s*"[^"]*"\s*\)', stripped):
            entries.append(
                _make_entry(
                    filepath,
                    line_num,
                    line,
                    check_id="command_injection",
                    summary="Potential command injection: exec.Command with dynamic arguments",
                    severity="high",
                    confidence="medium",
                    remediation="Validate and sanitize all arguments passed to exec.Command",
                )
            )


_PATH_TRAVERSAL_RE = re.compile(
    r"filepath\.Join\s*\([^)]*(?:\+|fmt\.Sprintf|r\.URL)"
)


def _check_path_traversal(
    filepath: str, line_num: int, line: str, entries: list[dict]
):
    """Detect potential path traversal via unsanitized filepath.Join."""
    if _PATH_TRAVERSAL_RE.search(line):
        entries.append(
            _make_entry(
                filepath,
                line_num,
                line,
                check_id="path_traversal",
                summary="Potential path traversal: filepath.Join with unsanitized input",
                severity="high",
                confidence="medium",
                remediation="Validate input does not contain '..' and use filepath.Clean",
            )
        )
