"""OCaml language plugin — compiler warnings."""

from desloppify.languages._framework.generic import generic_lang
from desloppify.languages._framework.treesitter._specs import OCAML_SPEC

generic_lang(
    name="ocaml",
    extensions=[".ml", ".mli"],
    tools=[
        {
            "label": "ocaml check",
            "cmd": "ocamlfind ocamlopt -c $(find . -name '*.ml' -maxdepth 3 | head -20) 2>&1 || true",
            "fmt": "gnu",
            "id": "ocaml_error",
            "tier": 3,
            "fix_cmd": None,
        },
    ],
    depth="minimal",
    detect_markers=["dune-project", "opam"],
    treesitter_spec=OCAML_SPEC,
)
