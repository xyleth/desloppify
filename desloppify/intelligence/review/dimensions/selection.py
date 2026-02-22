"""Dimension selection policy for per-file and holistic review preparation.

This module exists to keep precedence rules explicit and centralized.
"""

from __future__ import annotations

from desloppify.intelligence.review.dimensions.file import DEFAULT_DIMENSIONS
from desloppify.intelligence.review.dimensions.holistic import HOLISTIC_DIMENSIONS
from desloppify.intelligence.review.dimensions.lang import HOLISTIC_DIMENSIONS_BY_LANG


def _non_empty(values: list[str] | None) -> list[str] | None:
    """Return ``values`` only when it is a non-empty list."""
    if values and isinstance(values, list):
        return values
    return None


def resolve_per_file_dimensions(
    *,
    cli_dimensions: list[str] | None,
    config_dimensions: list[str] | None,
    default_dimensions: list[str] | None = None,
) -> list[str]:
    """Resolve per-file dimensions using a single precedence policy.

    Precedence (highest to lowest):
    1) CLI ``--dimensions``
    2) Config ``review_dimensions``
    3) Global defaults from ``dimensions.json``
    """
    return list(
        _non_empty(cli_dimensions)
        or _non_empty(config_dimensions)
        or _non_empty(default_dimensions)
        or DEFAULT_DIMENSIONS
    )


def resolve_holistic_dimensions(
    *,
    lang_name: str,
    cli_dimensions: list[str] | None,
    default_dimensions: list[str] | None = None,
) -> list[str]:
    """Resolve holistic dimensions using a single precedence policy.

    Precedence (highest to lowest):
    1) CLI ``--dimensions``
    2) Language-curated defaults from language plugin configuration
    3) Global defaults from ``holistic_dimensions.json``
    """
    return list(
        _non_empty(cli_dimensions)
        or _non_empty(HOLISTIC_DIMENSIONS_BY_LANG.get(lang_name))
        or _non_empty(default_dimensions)
        or HOLISTIC_DIMENSIONS
    )
