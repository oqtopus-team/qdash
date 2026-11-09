"""Source target inspection must not execute user Python."""

import pytest

from qdash.api.services.flow_service.target_defaults import resolve_target_defaults


@pytest.mark.parametrize(
    "expression, expected",
    [
        (
            'MuxTargets(mux_ids=[0, 2], exclude_qids=["1"])',
            {"mux_ids": [0, 2], "exclude_qids": ["1"]},
        ),
        ('QubitTargets(["2", "3"])', {"qids": ["2", "3"]}),
    ],
)
def test_literal_defaults(expression, expected):
    result = resolve_target_defaults(f"def run():\n    target = {expression}", "run", {})
    assert result is not None
    for key, value in expected.items():
        assert getattr(result, key) == value


def test_service_construction_does_not_declare_targets():
    """CalibService takes no targets; only run() targets are defaults."""
    code = 'def run():\n    cal = CalibService("user", "chip", project_id="p")\n    cal.run(QubitTargets(["4"]), [])'
    result = resolve_target_defaults(code, "run", {})
    assert result is not None
    assert result.qids == ["4"]


def test_from_context_services_are_recognized():
    code = """
def run(qids=["7"]):
    cal = CalibService.from_context(resolve_calib_context("u", "c", backend="fake"))
    cal.run(QubitTargets(qids), steps=[])
"""
    result = resolve_target_defaults(code, "run", {})
    assert result is not None
    assert result.qids == ["7"]
    assert resolve_target_defaults(code.replace("QubitTargets(qids)", "make()"), "run", {}) is None


def test_parameter_and_local_binding_defaults():
    code = """
def run(mux_ids=[1, 2]):
    excluded = ["5"]
    targets = MuxTargets(mux_ids, exclude_qids=excluded)
"""
    result = resolve_target_defaults(code, "run", {"mux_ids": [3]})
    assert result is not None
    assert result.mux_ids == [3]
    assert result.exclude_qids == ["5"]


@pytest.mark.parametrize(
    "body",
    [
        "MuxTargets(load_targets())",
        "MuxTargets([0]); MuxTargets([1])",
        'MuxTargets([0]); QubitTargets(["1"])',
    ],
)
def test_dynamic_or_differing_defaults_remain_unknown(body):
    assert resolve_target_defaults(f"def run():\n    {body}", "run", {}) is None


@pytest.mark.parametrize(
    "mutation",
    [
        'if flag:\n        qids = ["2"]',
        'qids.append("2")',
        'qids[0] = "2"',
        'qids += ["2"]',
    ],
)
def test_mutated_defaults_are_not_reported_as_literals(mutation):
    # flag has no known value, so a conditional write cannot be resolved.
    code = f'def run(flag, qids=["1"]):\n    {mutation}\n    QubitTargets(qids)'
    assert resolve_target_defaults(code, "run", {}) is None


def test_required_argument_shadows_module_binding():
    code = 'qids = ["1"]\ndef run(qids):\n    QubitTargets(qids)'
    assert resolve_target_defaults(code, "run", {}) is None


@pytest.mark.parametrize(
    "body",
    [
        'alias = qids\n    alias.append("2")\n    QubitTargets(qids)',
        "random.shuffle(qids)\n    QubitTargets(qids)",
        "del qids[0]\n    QubitTargets(qids)",
        "qids, other = load()\n    QubitTargets(qids)",
        'for qid in ["2"]:\n        qids = [qid]\n    QubitTargets(qids)',
        'cal = CalibService("u", "c")\n    cal.run(AllMuxTargets(), [])',
        'cal = CalibService("u", "c")\n    cal.run(load_targets(), [])',
        'QubitTargets(qids)\n    cal = CalibService("u", "c")\n    cal.run(make(), [])',
        'CalibService("u", "c", **options)',
        "QubitTargets(*values)",
        "QubitTargets(None)",
    ],
)
def test_unknown_or_mutated_sources_remain_unknown(body):
    code = f'import random\ndef run(qids=["1"], options={{}}, values=[]):\n    {body}'
    assert resolve_target_defaults(code, "run", {}) is None


def test_module_helpers_and_global_mutation_remain_unknown():
    helper = 'QIDS = ["1"]\ndef helper():\n    QIDS.append("2")\ndef run():\n    QubitTargets(QIDS)'
    assert resolve_target_defaults(helper, "run", {}) is None
    targets = 'def make():\n    return MuxTargets([5])\ndef run():\n    QubitTargets(["1"])'
    assert resolve_target_defaults(targets, "run", {}) is None


def test_undeclared_parameters_do_not_shadow_module_bindings():
    code = 'QIDS = ["1"]\ndef run():\n    QubitTargets(QIDS)'
    result = resolve_target_defaults(code, "run", {"QIDS": ["9"]})
    assert result is not None
    assert result.qids == ["1"]


def test_template_style_branches_follow_known_parameters():
    code = """
def run(mux_ids=None, exclude_qids=None, qids=None):
    if mux_ids is None:
        raise ValueError("required")
    if exclude_qids is None:
        exclude_qids = []
    if mux_ids:
        targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids or [])
    else:
        targets = QubitTargets(qids=qids)
    with CalibService("u", "c") as cal:
        cal.run(targets, steps=[])
"""
    result = resolve_target_defaults(code, "run", {"mux_ids": [1, 2]})
    assert result is not None
    assert (result.mux_ids, result.exclude_qids) == ([1, 2], [])
    assert resolve_target_defaults(code, "run", {}) is None
