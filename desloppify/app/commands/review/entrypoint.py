"""CLI entrypoint for review command."""

from __future__ import annotations

import argparse
import sys

from desloppify.app.commands.helpers.lang import resolve_lang
from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.utils import colorize

from .batch import _do_run_batches
from .import_cmd import do_import
from .prepare import do_prepare


def cmd_review(args: argparse.Namespace) -> None:
    """Prepare or import subjective code review findings."""
    runtime = command_runtime(args)
    state_file = runtime.state_path
    state = runtime.state
    lang = resolve_lang(args)

    if not lang:
        print(
            colorize("  Error: could not detect language. Use --lang.", "red"),
            file=sys.stderr,
        )
        sys.exit(1)

    if getattr(args, "run_batches", False):
        _do_run_batches(
            args,
            state,
            lang,
            state_file,
            config=runtime.config,
        )
        return

    import_file = getattr(args, "import_file", None)

    if import_file:
        do_import(
            import_file,
            state,
            lang,
            state_file,
            config=runtime.config,
        )
    else:
        do_prepare(args, state, lang, state_file, config=runtime.config)
