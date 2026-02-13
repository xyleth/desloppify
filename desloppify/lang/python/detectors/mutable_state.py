"""Detect module-level mutable state modified from functions within the same module."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ....utils import PROJECT_ROOT, find_py_files


def detect_global_mutable_config(path: Path) -> tuple[list[dict], int]:
    """Detect module-level mutable state that gets modified from functions.

    Finds module-level assignments to None, {}, [], set(), or annotated Optional
    that are later reassigned or mutated from functions within the same module.
    Skips UPPER_CASE names that are genuinely constant (only flag names initialized
    to mutable values).

    Returns (entries, total_files_checked).
    """
    files = find_py_files(path)
    entries: list[dict] = []

    for filepath in files:
        try:
            p = Path(filepath) if Path(filepath).is_absolute() else PROJECT_ROOT / filepath
            content = p.read_text()
        except (OSError, UnicodeDecodeError):
            continue

        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue

        _detect_in_module(filepath, tree, entries)

    return entries, len(files)


# Mutable initializer values
_MUTABLE_INIT = (ast.List, ast.Dict, ast.Set)
_MUTABLE_CALL_NAMES = {"set", "list", "dict", "defaultdict", "OrderedDict", "Counter"}

# Mutating method names
_MUTATING_METHODS = {
    "append", "extend", "insert", "pop", "remove", "clear",
    "update", "setdefault", "add", "discard",
}


def _is_mutable_init(value: ast.AST) -> bool:
    """Check if an AST value is a mutable initializer ([], {}, set(), etc.)."""
    if isinstance(value, _MUTABLE_INIT):
        return True
    if isinstance(value, ast.Call):
        func = value.func
        if isinstance(func, ast.Name) and func.id in _MUTABLE_CALL_NAMES:
            return True
        if isinstance(func, ast.Attribute) and func.attr in _MUTABLE_CALL_NAMES:
            return True
    if isinstance(value, ast.Constant) and value.value is None:
        return True
    return False


def _is_upper_case(name: str) -> bool:
    """Check if a name is UPPER_CASE (constant convention)."""
    return bool(re.match(r"^_?[A-Z][A-Z0-9_]+$", name))


def _collect_module_level_mutables(tree: ast.Module) -> dict[str, int]:
    """Collect module-level names initialized to mutable values.

    Returns {name: lineno} for names that are NOT UPPER_CASE constants.
    """
    mutables: dict[str, int] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and _is_mutable_init(stmt.value):
                    if not _is_upper_case(target.id):
                        mutables[target.id] = stmt.lineno
        elif isinstance(stmt, ast.AnnAssign) and stmt.target and isinstance(stmt.target, ast.Name):
            name = stmt.target.id
            if _is_upper_case(name):
                continue
            # Annotated with Optional or assigned to mutable
            if stmt.value is not None and _is_mutable_init(stmt.value):
                mutables[name] = stmt.lineno
            elif _is_optional_annotation(stmt.annotation):
                mutables[name] = stmt.lineno
    return mutables


def _is_optional_annotation(ann: ast.AST) -> bool:
    """Check if an annotation looks like Optional[...]."""
    if isinstance(ann, ast.Subscript):
        if isinstance(ann.value, ast.Name) and ann.value.id == "Optional":
            return True
        if isinstance(ann.value, ast.Attribute) and ann.value.attr == "Optional":
            return True
    # X | None form (Python 3.10+)
    if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
        if isinstance(ann.right, ast.Constant) and ann.right.value is None:
            return True
        if isinstance(ann.left, ast.Constant) and ann.left.value is None:
            return True
    return False


def _find_mutations_in_functions(tree: ast.Module, mutables: dict[str, int]) -> dict[str, list[int]]:
    """Find functions that reassign or mutate module-level mutable names.

    Returns {name: [line numbers where mutation occurs]}.

    Bare assignments (name = x) and augmented assignments (name += x) only count
    as mutations when the function has an explicit `global name` declaration —
    without it, Python creates a local variable. Subscript assignments (name[k] = v)
    and method calls (name.append(x)) don't need `global` because they operate on
    the object reference, not rebind the name.
    """
    mutations: dict[str, list[int]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Skip if name is a parameter
        param_names = {a.arg for a in node.args.args + node.args.posonlyargs + node.args.kwonlyargs}
        # Collect names declared `global` in this function
        global_names: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Global):
                global_names.update(child.names)

        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    # Bare name assignment: requires `global` to actually mutate
                    if isinstance(target, ast.Name) and target.id in mutables and target.id not in param_names:
                        if target.id in global_names:
                            mutations.setdefault(target.id, []).append(child.lineno)
                    # Subscript assignment (name[k] = v): operates on the object, no `global` needed
                    elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                        if target.value.id in mutables and target.value.id not in param_names:
                            mutations.setdefault(target.value.id, []).append(child.lineno)
            # Augmented assignment (name += x): requires `global` to actually mutate
            elif isinstance(child, ast.AugAssign):
                if (isinstance(child.target, ast.Name) and child.target.id in mutables
                        and child.target.id not in param_names and child.target.id in global_names):
                    mutations.setdefault(child.target.id, []).append(child.lineno)
            # Mutating method call: name.append(...) — no `global` needed
            elif isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if (child.func.attr in _MUTATING_METHODS
                        and isinstance(child.func.value, ast.Name)
                        and child.func.value.id in mutables
                        and child.func.value.id not in param_names):
                    mutations.setdefault(child.func.value.id, []).append(child.lineno)

    return mutations


def _detect_in_module(filepath: str, tree: ast.Module, entries: list[dict]):
    """Detect global mutable config patterns in a single module."""
    mutables = _collect_module_level_mutables(tree)
    if not mutables:
        return

    mutations = _find_mutations_in_functions(tree, mutables)
    if not mutations:
        return

    for name, mutation_lines in mutations.items():
        defn_line = mutables[name]
        entries.append({
            "file": filepath,
            "name": name,
            "line": defn_line,
            "mutation_lines": mutation_lines[:5],
            "mutation_count": len(mutation_lines),
            "confidence": "medium",
            "summary": (f"Module-level mutable '{name}' (line {defn_line}) "
                        f"modified from {len(mutation_lines)} site(s)"),
        })
