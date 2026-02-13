"""Tests for desloppify.lang.typescript.detectors.deps — dependency graph and import analysis."""

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _set_project_root(tmp_path, monkeypatch):
    """Point PROJECT_ROOT and SRC_PATH at the tmp directory."""
    monkeypatch.setenv("DESLOPPIFY_ROOT", str(tmp_path))
    import desloppify.utils as utils_mod
    monkeypatch.setattr(utils_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(utils_mod, "SRC_PATH", tmp_path / "src")
    import desloppify.lang.typescript.detectors.deps as det_mod
    monkeypatch.setattr(det_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(det_mod, "SRC_PATH", tmp_path / "src")
    utils_mod._find_source_files_cached.cache_clear()


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# ── build_dep_graph ──────────────────────────────────────────


class TestBuildDepGraph:
    def test_simple_relative_import(self, tmp_path):
        """Graph captures a simple relative import between two files."""
        from desloppify.lang.typescript.detectors.deps import build_dep_graph

        _write(tmp_path, "utils.ts", "export function foo() { return 1; }\n")
        _write(tmp_path, "main.ts", "import { foo } from './utils';\nconsole.log(foo());\n")

        graph = build_dep_graph(tmp_path)
        main_key = str((tmp_path / "main.ts").resolve())
        utils_key = str((tmp_path / "utils.ts").resolve())

        assert main_key in graph
        assert utils_key in graph[main_key]["imports"]
        assert main_key in graph[utils_key]["importers"]

    def test_import_with_extension(self, tmp_path):
        """Graph resolves imports where the file has a .ts extension match."""
        from desloppify.lang.typescript.detectors.deps import build_dep_graph

        _write(tmp_path, "helpers.ts", "export const x = 1;\n")
        _write(tmp_path, "app.ts", "import { x } from './helpers';\n")

        graph = build_dep_graph(tmp_path)
        app_key = str((tmp_path / "app.ts").resolve())
        helpers_key = str((tmp_path / "helpers.ts").resolve())
        assert helpers_key in graph[app_key]["imports"]

    def test_import_tsx_file(self, tmp_path):
        """Graph resolves imports to .tsx files."""
        from desloppify.lang.typescript.detectors.deps import build_dep_graph

        _write(tmp_path, "Button.tsx", "export const Button = () => <button />;\n")
        _write(tmp_path, "App.tsx", "import { Button } from './Button';\n")

        graph = build_dep_graph(tmp_path)
        app_key = str((tmp_path / "App.tsx").resolve())
        button_key = str((tmp_path / "Button.tsx").resolve())
        assert button_key in graph[app_key]["imports"]

    def test_index_file_resolution(self, tmp_path):
        """Graph resolves directory imports to index.ts files."""
        from desloppify.lang.typescript.detectors.deps import build_dep_graph

        _write(tmp_path, "components/index.ts", "export const Comp = 'comp';\n")
        _write(tmp_path, "main.ts", "import { Comp } from './components';\n")

        graph = build_dep_graph(tmp_path)
        main_key = str((tmp_path / "main.ts").resolve())
        index_key = str((tmp_path / "components" / "index.ts").resolve())
        assert index_key in graph[main_key]["imports"]

    def test_no_external_packages_in_graph(self, tmp_path):
        """External package imports (non-relative, non-alias) should not appear in the graph."""
        from desloppify.lang.typescript.detectors.deps import build_dep_graph

        _write(tmp_path, "app.ts", "import React from 'react';\nimport { useState } from 'react';\n")

        graph = build_dep_graph(tmp_path)
        # Only the app.ts file should be in the graph (as a node), no react entries
        for key in graph:
            assert "react" not in Path(key).name

    def test_graph_has_counts(self, tmp_path):
        """Graph entries should have import_count and importer_count fields."""
        from desloppify.lang.typescript.detectors.deps import build_dep_graph

        _write(tmp_path, "a.ts", "export const a = 1;\n")
        _write(tmp_path, "b.ts", "import { a } from './a';\nexport const b = a;\n")

        graph = build_dep_graph(tmp_path)
        a_key = str((tmp_path / "a.ts").resolve())
        b_key = str((tmp_path / "b.ts").resolve())
        assert graph[a_key]["importer_count"] == 1
        assert graph[b_key]["import_count"] == 1

    def test_empty_directory(self, tmp_path):
        """Empty directory returns an empty graph."""
        from desloppify.lang.typescript.detectors.deps import build_dep_graph

        graph = build_dep_graph(tmp_path)
        assert graph == {}

    def test_multiple_imports_from_same_file(self, tmp_path):
        """Multiple import lines from the same source still yield one edge."""
        from desloppify.lang.typescript.detectors.deps import build_dep_graph

        _write(tmp_path, "utils.ts", "export const a = 1;\nexport const b = 2;\n")
        _write(tmp_path, "main.ts", (
            "import { a } from './utils';\n"
            "import { b } from './utils';\n"
        ))

        graph = build_dep_graph(tmp_path)
        main_key = str((tmp_path / "main.ts").resolve())
        utils_key = str((tmp_path / "utils.ts").resolve())
        # imports is a set, so duplicates are collapsed
        assert utils_key in graph[main_key]["imports"]
        assert graph[main_key]["import_count"] == 1

    def test_bidirectional_import(self, tmp_path):
        """Two files importing each other creates bidirectional edges."""
        from desloppify.lang.typescript.detectors.deps import build_dep_graph

        _write(tmp_path, "a.ts", "import { bVal } from './b';\nexport const aVal = 1;\n")
        _write(tmp_path, "b.ts", "import { aVal } from './a';\nexport const bVal = 2;\n")

        graph = build_dep_graph(tmp_path)
        a_key = str((tmp_path / "a.ts").resolve())
        b_key = str((tmp_path / "b.ts").resolve())
        assert b_key in graph[a_key]["imports"]
        assert a_key in graph[b_key]["imports"]


# ── ts_alias_resolver ────────────────────────────────────────


class TestTsAliasResolver:
    def test_resolves_at_alias(self):
        from desloppify.lang.typescript.detectors.deps import ts_alias_resolver
        assert ts_alias_resolver("@/components/Button") == "src/components/Button"

    def test_passthrough_relative(self):
        from desloppify.lang.typescript.detectors.deps import ts_alias_resolver
        assert ts_alias_resolver("./utils") == "./utils"

    def test_passthrough_package(self):
        from desloppify.lang.typescript.detectors.deps import ts_alias_resolver
        assert ts_alias_resolver("react") == "react"


# ── build_dynamic_import_targets ─────────────────────────────


class TestBuildDynamicImportTargets:
    def test_finds_dynamic_import(self, tmp_path):
        """Finds files referenced by dynamic import() expressions."""
        from desloppify.lang.typescript.detectors.deps import build_dynamic_import_targets

        _write(tmp_path, "app.ts", "const mod = import('./lazy');\n")

        targets = build_dynamic_import_targets(tmp_path, [".ts", ".tsx"])
        assert "./lazy" in targets

    def test_finds_side_effect_import(self, tmp_path):
        """Finds side-effect imports (import 'module')."""
        from desloppify.lang.typescript.detectors.deps import build_dynamic_import_targets

        _write(tmp_path, "app.ts", "import './polyfill';\n")

        targets = build_dynamic_import_targets(tmp_path, [".ts", ".tsx"])
        assert "./polyfill" in targets

    def test_empty_directory(self, tmp_path):
        """Empty directory returns empty set."""
        from desloppify.lang.typescript.detectors.deps import build_dynamic_import_targets

        targets = build_dynamic_import_targets(tmp_path, [".ts", ".tsx"])
        assert targets == set()
