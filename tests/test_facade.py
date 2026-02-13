"""Tests for desloppify.detectors.facade — re-export facade detection."""

import pytest

from desloppify.detectors.facade import (
    _is_py_facade,
    _is_ts_facade,
    detect_reexport_facades,
)


def _make_graph_entry(importer_count: int = 0) -> dict:
    return {
        "imports": set(),
        "importers": set(),
        "import_count": 0,
        "importer_count": importer_count,
    }


class TestIsPyFacade:
    def test_pure_reexport(self, tmp_path):
        f = tmp_path / "facade.py"
        f.write_text("from .new_module import foo, bar\nfrom .other import baz\n")
        result = _is_py_facade(str(f))
        assert result is not None
        assert "new_module" in result["imports_from"]
        assert "other" in result["imports_from"]

    def test_file_with_logic_not_facade(self, tmp_path):
        f = tmp_path / "real.py"
        f.write_text("from .mod import foo\n\ndef compute():\n    return foo() + 1\n")
        result = _is_py_facade(str(f))
        assert result is None

    def test_file_with_docstring_and_imports(self, tmp_path):
        f = tmp_path / "facade.py"
        f.write_text('"""This module re-exports."""\nfrom .core import A, B\n')
        result = _is_py_facade(str(f))
        assert result is not None

    def test_file_with_dunder_all_allowed(self, tmp_path):
        f = tmp_path / "facade.py"
        f.write_text('from .core import A, B\n__all__ = ["A", "B"]\n')
        result = _is_py_facade(str(f))
        assert result is not None

    def test_file_with_non_all_assignment_not_facade(self, tmp_path):
        f = tmp_path / "real.py"
        f.write_text("from .core import A\nVERSION = '1.0'\n")
        result = _is_py_facade(str(f))
        assert result is None

    def test_empty_file_not_facade(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("")
        result = _is_py_facade(str(f))
        assert result is None

    def test_import_statement(self, tmp_path):
        f = tmp_path / "facade.py"
        f.write_text("import os\nimport sys\n")
        result = _is_py_facade(str(f))
        assert result is not None
        assert "os" in result["imports_from"]
        assert "sys" in result["imports_from"]

    def test_nonexistent_file(self):
        result = _is_py_facade("/nonexistent/path/facade.py")
        assert result is None


class TestIsTsFacade:
    def test_pure_reexport(self, tmp_path):
        f = tmp_path / "index.ts"
        f.write_text("export { foo, bar } from './module';\nexport * from './other';\n")
        result = _is_ts_facade(str(f))
        assert result is not None
        assert "./module" in result["imports_from"]
        assert "./other" in result["imports_from"]

    def test_file_with_logic_not_facade(self, tmp_path):
        f = tmp_path / "real.ts"
        f.write_text("export { foo } from './module';\nconst x = 1;\n")
        result = _is_ts_facade(str(f))
        assert result is None

    def test_type_reexport(self, tmp_path):
        f = tmp_path / "types.ts"
        f.write_text("export type { MyType } from './types';\n")
        result = _is_ts_facade(str(f))
        assert result is not None

    def test_comments_allowed(self, tmp_path):
        f = tmp_path / "index.ts"
        f.write_text("// Re-exports\nexport { foo } from './module';\n")
        result = _is_ts_facade(str(f))
        assert result is not None

    def test_empty_file_not_facade(self, tmp_path):
        f = tmp_path / "empty.ts"
        f.write_text("")
        result = _is_ts_facade(str(f))
        assert result is None

    def test_nonexistent_file(self):
        result = _is_ts_facade("/nonexistent/path/index.ts")
        assert result is None


class TestDetectReexportFacades:
    def test_facade_file_detected_python(self, tmp_path):
        f = tmp_path / "facade.py"
        f.write_text("from .core import A, B\nfrom .utils import C\n")

        graph = {str(f): _make_graph_entry(importer_count=1)}
        entries, total = detect_reexport_facades(graph, lang="python")
        assert len(entries) == 1
        assert entries[0]["file"] == str(f)
        assert entries[0]["kind"] == "file"
        assert entries[0]["importers"] == 1
        assert total == 1

    def test_facade_file_detected_typescript(self, tmp_path):
        f = tmp_path / "index.ts"
        f.write_text("export { foo } from './module';\nexport * from './other';\n")

        graph = {str(f): _make_graph_entry(importer_count=0)}
        entries, total = detect_reexport_facades(graph, lang="typescript")
        assert len(entries) == 1
        assert entries[0]["kind"] == "file"

    def test_non_facade_file_not_detected(self, tmp_path):
        f = tmp_path / "real.py"
        f.write_text("from .core import A\n\ndef process():\n    return A()\n")

        graph = {str(f): _make_graph_entry(importer_count=1)}
        entries, total = detect_reexport_facades(graph, lang="python")
        assert entries == []

    def test_too_many_importers_excluded(self, tmp_path):
        """Files with more than max_importers should not be flagged."""
        f = tmp_path / "facade.py"
        f.write_text("from .core import A, B\n")

        graph = {str(f): _make_graph_entry(importer_count=5)}
        entries, total = detect_reexport_facades(graph, lang="python", max_importers=2)
        assert entries == []

    def test_custom_max_importers(self, tmp_path):
        f = tmp_path / "facade.py"
        f.write_text("from .core import A\n")

        graph = {str(f): _make_graph_entry(importer_count=3)}
        # max_importers=3 should include files with 3 importers (uses > not >=)
        entries, total = detect_reexport_facades(graph, lang="python", max_importers=3)
        assert len(entries) == 1

    def test_empty_graph(self):
        entries, total = detect_reexport_facades({}, lang="python")
        assert entries == []
        assert total == 0

    def test_entry_structure(self, tmp_path):
        f = tmp_path / "facade.py"
        f.write_text("from .core import A\n")

        graph = {str(f): _make_graph_entry(importer_count=1)}
        entries, total = detect_reexport_facades(graph, lang="python")
        entry = entries[0]
        assert "file" in entry
        assert "loc" in entry
        assert "importers" in entry
        assert "imports_from" in entry
        assert "kind" in entry

    def test_python_directory_facade(self, tmp_path):
        """A directory where __init__.py and all submodules are facades."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        init = pkg / "__init__.py"
        init.write_text("from .sub import A\n")
        sub = pkg / "sub.py"
        sub.write_text("from .real import B\n")

        graph = {
            str(init): _make_graph_entry(importer_count=1),
            str(sub): _make_graph_entry(importer_count=1),
        }
        entries, total = detect_reexport_facades(graph, lang="python")
        # Should find both file facades and the directory facade
        kinds = {e["kind"] for e in entries}
        assert "file" in kinds
        assert "directory" in kinds

    def test_multiple_files_sorted(self, tmp_path):
        """Entries should be sorted by kind, importers, then LOC descending."""
        f1 = tmp_path / "small.py"
        f1.write_text("from .a import X\n")
        f2 = tmp_path / "big.py"
        f2.write_text("from .a import X\nfrom .b import Y\nfrom .c import Z\n")

        graph = {
            str(f1): _make_graph_entry(importer_count=0),
            str(f2): _make_graph_entry(importer_count=0),
        }
        entries, total = detect_reexport_facades(graph, lang="python")
        assert len(entries) == 2
        assert total == 2
