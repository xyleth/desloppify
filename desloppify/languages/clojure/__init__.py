"""Clojure language plugin — clj-kondo."""

from desloppify.languages._framework.generic import generic_lang
from desloppify.languages._framework.treesitter._specs import CLOJURE_SPEC

generic_lang(
    name="clojure",
    extensions=[".clj", ".cljs", ".cljc"],
    tools=[
        {
            "label": "clj-kondo",
            "cmd": "clj-kondo --lint . --config '{:output {:format :json}}'",
            "fmt": "json",
            "id": "clj_kondo_finding",
            "tier": 2,
            "fix_cmd": None,
        },
    ],
    depth="minimal",
    detect_markers=["deps.edn", "project.clj"],
    treesitter_spec=CLOJURE_SPEC,
)
