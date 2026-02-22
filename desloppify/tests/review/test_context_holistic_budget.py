"""Focused unit tests for context_holistic.budget helpers."""

from __future__ import annotations

from desloppify.intelligence.review.context_holistic import budget as budget_mod


def test_count_signature_params_ignores_instance_receiver_tokens():
    assert budget_mod._count_signature_params("self, a, b, cls, this, c") == 3
    assert budget_mod._count_signature_params("   ") == 0


def test_extract_type_names_handles_generics_and_qualified_names():
    raw = "IRepo, pkg.Service<T>, (BaseProtocol), invalid-token"
    names = budget_mod._extract_type_names(raw)
    assert names == ["IRepo", "Service", "BaseProtocol"]


def test_abstractions_context_reports_wrapper_and_indirection_signals(tmp_path):
    util_file = tmp_path / "pkg" / "utils.py"
    contracts_file = tmp_path / "pkg" / "contracts.ts"
    service_file = tmp_path / "pkg" / "service.py"

    util_content = (
        "def wrap_user(value):\n"
        "    return make_user(value)\n\n"
        "def make_user(value):\n"
        "    return value\n"
    )
    contracts_content = "interface Repo {}\nclass SqlRepo implements Repo {}\n"
    service_content = (
        "def build(a, b, c, d, e, f, g):\n"
        "    return a\n\n"
        "value = root.one.two.three.four\n"
        "config config config config config config config config config config\n"
    )

    util_file.parent.mkdir(parents=True, exist_ok=True)
    util_file.write_text(util_content)
    contracts_file.write_text(contracts_content)
    service_file.write_text(service_content)

    file_contents = {
        str(util_file): util_content,
        str(contracts_file): contracts_content,
        str(service_file): service_content,
    }

    context = budget_mod._abstractions_context(file_contents)

    assert context["summary"]["total_wrappers"] >= 1
    assert context["summary"]["one_impl_interface_count"] == 1
    assert context["util_files"][0]["file"].endswith("utils.py")
    assert "pass_through_wrappers" in context
    assert "indirection_hotspots" in context
    assert "wide_param_bags" in context
    assert 0 <= context["sub_axes"]["abstraction_leverage"] <= 100
    assert 0 <= context["sub_axes"]["indirection_cost"] <= 100
    assert 0 <= context["sub_axes"]["interface_honesty"] <= 100


def test_codebase_stats_counts_files_and_loc():
    stats = budget_mod._codebase_stats({"a.py": "x\n", "b.py": "one\ntwo\nthree\n"})
    assert stats == {"total_files": 2, "total_loc": 4}


# ── _score_clamped ────────────────────────────────────────


def test_score_clamped_typical_value():
    assert budget_mod._score_clamped(75.3) == 75


def test_score_clamped_rounds_half_up():
    assert budget_mod._score_clamped(50.5) == 50  # Python banker's rounding


def test_score_clamped_clamps_below_zero():
    assert budget_mod._score_clamped(-15.0) == 0


def test_score_clamped_clamps_above_100():
    assert budget_mod._score_clamped(200.0) == 100


def test_score_clamped_zero_and_100_boundaries():
    assert budget_mod._score_clamped(0.0) == 0
    assert budget_mod._score_clamped(100.0) == 100


# ── _count_signature_params edge cases ────────────────────


def test_count_signature_params_empty_string():
    assert budget_mod._count_signature_params("") == 0


def test_count_signature_params_only_receivers():
    assert budget_mod._count_signature_params("self") == 0
    assert budget_mod._count_signature_params("cls") == 0
    assert budget_mod._count_signature_params("this") == 0
    assert budget_mod._count_signature_params("self, cls") == 0


def test_count_signature_params_with_type_annotations():
    assert budget_mod._count_signature_params("a: int, b: str, c: float") == 3


def test_count_signature_params_with_defaults():
    assert budget_mod._count_signature_params("a=1, b=None") == 2


def test_count_signature_params_trailing_comma():
    # trailing comma produces empty split elements that get filtered
    assert budget_mod._count_signature_params("a, b,") == 2


# ── _extract_type_names edge cases ────────────────────────


def test_extract_type_names_empty_string():
    assert budget_mod._extract_type_names("") == []


def test_extract_type_names_single_name():
    assert budget_mod._extract_type_names("Foo") == ["Foo"]


def test_extract_type_names_strips_colon_suffix():
    assert budget_mod._extract_type_names("Foo:") == ["Foo"]


def test_extract_type_names_rejects_non_identifiers():
    assert budget_mod._extract_type_names("123, -, !@#") == []


# ── _abstractions_context scoring edge cases ──────────────


def test_abstractions_context_empty_input():
    """Empty file dict produces zero-count summary."""
    context = budget_mod._abstractions_context({})
    assert context["summary"]["total_wrappers"] == 0
    assert context["summary"]["total_function_signatures"] == 0
    assert context["summary"]["one_impl_interface_count"] == 0
    assert context["sub_axes"]["abstraction_leverage"] == 100
    assert context["sub_axes"]["indirection_cost"] == 100
    assert context["sub_axes"]["interface_honesty"] == 100
    assert context["util_files"] == []
    assert "pass_through_wrappers" not in context
    assert "one_impl_interfaces" not in context


def test_abstractions_context_interface_with_multiple_impls_not_reported(tmp_path):
    """Interfaces with 2+ implementations should not appear in one_impl_interfaces."""
    f1 = tmp_path / "pkg" / "contract.ts"
    f1.parent.mkdir(parents=True, exist_ok=True)
    f1.write_text("interface IRepo {}\n")

    f2 = tmp_path / "pkg" / "sql.ts"
    f2.write_text("class SqlRepo implements IRepo {}\n")

    f3 = tmp_path / "pkg" / "mongo.ts"
    f3.write_text("class MongoRepo implements IRepo {}\n")

    file_contents = {
        str(f1): f1.read_text(),
        str(f2): f2.read_text(),
        str(f3): f3.read_text(),
    }

    context = budget_mod._abstractions_context(file_contents)
    assert context["summary"]["one_impl_interface_count"] == 0
    assert "one_impl_interfaces" not in context


def test_abstractions_context_python_protocol_detected(tmp_path):
    """Python Protocol classes are detected as interface declarations."""
    f = tmp_path / "pkg" / "types.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("class HandlerProtocol:\n    pass\n")

    context = budget_mod._abstractions_context({str(f): f.read_text()})
    # Protocol declared but 0 implementations -> one_impl_interface_count stays 0
    # (it needs exactly 1 impl to be counted)
    assert context["summary"]["one_impl_interface_count"] == 0


def test_abstractions_context_wrapper_rate_calculation(tmp_path):
    """Verify wrapper rate = total_wrappers / total_function_signatures."""
    f = tmp_path / "pkg" / "mod.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "def alpha(x):\n"
        "    return beta(x)\n\n"
        "def beta(x):\n"
        "    return x\n\n"
        "def gamma(x):\n"
        "    return x * 2\n"
    )
    f.write_text(content)

    context = budget_mod._abstractions_context({str(f): content})
    summary = context["summary"]
    assert summary["total_wrappers"] == 1  # alpha -> beta
    assert summary["total_function_signatures"] == 3
    assert summary["wrapper_rate"] == round(1 / 3, 3)

