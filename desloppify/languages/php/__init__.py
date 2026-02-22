"""PHP language plugin — phpstan."""

from desloppify.languages._framework.generic import generic_lang
from desloppify.languages._framework.treesitter._specs import PHP_SPEC

generic_lang(
    name="php",
    extensions=[".php"],
    tools=[
        {
            "label": "phpstan",
            "cmd": "phpstan analyse --error-format=json --no-progress",
            "fmt": "json",
            "id": "phpstan_error",
            "tier": 2,
            "fix_cmd": None,
        },
    ],
    exclude=["vendor"],
    depth="shallow",
    detect_markers=["composer.json"],
    treesitter_spec=PHP_SPEC,
)
