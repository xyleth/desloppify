"""Data models for review-context construction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


@dataclass
class ReviewContext:
    """Codebase-wide context for contextual file evaluation."""

    naming_vocabulary: dict = field(default_factory=dict)
    error_conventions: dict = field(default_factory=dict)
    module_patterns: dict = field(default_factory=dict)
    import_graph_summary: dict = field(default_factory=dict)
    zone_distribution: dict = field(default_factory=dict)
    existing_findings: dict = field(default_factory=dict)
    codebase_stats: dict = field(default_factory=dict)
    sibling_conventions: dict = field(default_factory=dict)
    ai_debt_signals: dict = field(default_factory=dict)
    auth_patterns: dict = field(default_factory=dict)
    error_strategies: dict = field(default_factory=dict)


@dataclass
class HolisticContext:
    """Typed seam contract for holistic review context pipelines."""

    architecture: dict = field(default_factory=dict)
    coupling: dict = field(default_factory=dict)
    conventions: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)
    abstractions: dict = field(default_factory=dict)
    dependencies: dict = field(default_factory=dict)
    testing: dict = field(default_factory=dict)
    api_surface: dict = field(default_factory=dict)
    structure: dict = field(default_factory=dict)
    codebase_stats: dict = field(default_factory=dict)
    authorization: dict = field(default_factory=dict)
    ai_debt_signals: dict = field(default_factory=dict)
    migration_signals: dict = field(default_factory=dict)

    @classmethod
    def from_raw(cls, payload: Mapping[str, Any] | None) -> HolisticContext:
        raw = payload if isinstance(payload, Mapping) else {}
        return cls(
            architecture=_as_dict(raw.get("architecture")),
            coupling=_as_dict(raw.get("coupling")),
            conventions=_as_dict(raw.get("conventions")),
            errors=_as_dict(raw.get("errors")),
            abstractions=_as_dict(raw.get("abstractions")),
            dependencies=_as_dict(raw.get("dependencies")),
            testing=_as_dict(raw.get("testing")),
            api_surface=_as_dict(raw.get("api_surface")),
            structure=_as_dict(raw.get("structure")),
            codebase_stats=_as_dict(raw.get("codebase_stats")),
            authorization=_as_dict(raw.get("authorization")),
            ai_debt_signals=_as_dict(raw.get("ai_debt_signals")),
            migration_signals=_as_dict(raw.get("migration_signals")),
        )

    def to_dict(self) -> dict[str, object]:
        out = {
            "architecture": self.architecture,
            "coupling": self.coupling,
            "conventions": self.conventions,
            "errors": self.errors,
            "abstractions": self.abstractions,
            "dependencies": self.dependencies,
            "testing": self.testing,
            "api_surface": self.api_surface,
            "structure": self.structure,
        }
        out["codebase_stats"] = self.codebase_stats
        if self.authorization:
            out["authorization"] = self.authorization
        if self.ai_debt_signals:
            out["ai_debt_signals"] = self.ai_debt_signals
        if self.migration_signals:
            out["migration_signals"] = self.migration_signals
        return out


__all__ = ["ReviewContext", "HolisticContext"]
