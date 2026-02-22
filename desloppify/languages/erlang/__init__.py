"""Erlang language plugin — dialyzer."""

from desloppify.languages._framework.generic import generic_lang
from desloppify.languages._framework.treesitter._specs import ERLANG_SPEC

generic_lang(
    name="erlang",
    extensions=[".erl", ".hrl"],
    tools=[
        {
            "label": "dialyzer",
            "cmd": "dialyzer --src -r . 2>&1",
            "fmt": "gnu",
            "id": "dialyzer_warning",
            "tier": 2,
            "fix_cmd": None,
        },
    ],
    depth="shallow",
    detect_markers=["rebar.config", "rebar.lock"],
    treesitter_spec=ERLANG_SPEC,
)
