"""State and query IO helpers for fix command flows."""

from __future__ import annotations

from desloppify import state as state_mod
from desloppify.app.commands.helpers.state import state_path


def _load_state(args) -> tuple[str, dict]:
    state_file = state_path(args)
    return state_file, state_mod.load_state(state_file)


def _save_state(state: dict, state_path_value: str) -> None:
    state_mod.save_state(state, state_path_value)
