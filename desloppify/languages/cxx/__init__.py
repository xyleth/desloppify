"""C/C++ language plugin — cppcheck."""

from desloppify.languages._framework.generic import generic_lang
from desloppify.languages._framework.treesitter._specs import CPP_SPEC

generic_lang(
    name="cxx",
    extensions=[".c", ".cpp", ".cc", ".cxx", ".h", ".hpp"],
    tools=[
        {
            "label": "cppcheck",
            "cmd": "cppcheck --template='{file}:{line}: {severity}: {message}' --enable=all --quiet .",
            "fmt": "gnu",
            "id": "cppcheck_finding",
            "tier": 2,
            "fix_cmd": None,
        },
    ],
    exclude=["build", "cmake-build-debug", "cmake-build-release"],
    depth="shallow",
    detect_markers=["CMakeLists.txt", "Makefile"],
    treesitter_spec=CPP_SPEC,
)
