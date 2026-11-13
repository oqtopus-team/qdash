"""Source target inspection must not execute user Python."""

from pathlib import Path

import pytest

import qdash.workflow
from qdash.api.services.flow_service.target_defaults import (
    resolve_target_defaults,
    supported_target_modes,
)
from qdash.datamodel.flow_targets import TargetMode

TEMPLATES = Path(qdash.workflow.__file__).parent / "templates"


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


def test_literal_coupling_pairs_keep_their_direction():
    code = 'def run():\n    target = CouplingTargets([("63", "85"), ("85", "63")])'
    result = resolve_target_defaults(code, "run", {})
    assert result is not None
    assert result.coupling_pairs == [["63", "85"], ["85", "63"]]


@pytest.mark.parametrize(
    "expression",
    [
        "CouplingTargets(pairs=[pair for group in schedule for pair in group])",
        'CouplingTargets([("1", "1")])',
        'CouplingTargets([("1", "2", "3")])',
    ],
)
def test_dynamic_or_invalid_coupling_defaults_remain_unknown(expression):
    code = f"def run(schedule=[[('0', '1')]]):\n    target = {expression}"
    assert resolve_target_defaults(code, "run", {}) is None


PAIR_RUN = "CalibService(u, c).run({targets}, steps={steps})"
PAIRS = "CouplingTargets(p)"
AUTOMATIC = "[GenerateCRSchedule(), TwoQubitCalibration()]"


def _modes(body: str, prefix: str = "") -> list[TargetMode]:
    lines = "\n".join(f"    {line}" for line in body.splitlines())
    return supported_target_modes(f"{prefix}def run(u, c, p, s):\n{lines}\n", "run")


@pytest.mark.parametrize(
    ("body", "modes"),
    [
        (PAIR_RUN.format(targets=PAIRS, steps=AUTOMATIC), ["coupling_pairs"]),
        (
            f"t = {PAIRS}\nsteps = {AUTOMATIC}\nsteps.append(ConfigureAll())\n"
            "with CalibService(u, c) as cal:\n    cal.run(t, steps)",
            ["coupling_pairs"],
        ),
        # Automatic steps schedule only the directed target pairs.
        (PAIR_RUN.format(targets=PAIRS, steps="[TwoQubitCalibration()]"), ["coupling_pairs"]),
        # Building a schedule does not count unless the executed pipeline uses it.
        (
            f"unused = {AUTOMATIC}\n"
            + PAIR_RUN.format(targets=PAIRS, steps="[TwoQubitCalibration()]"),
            ["coupling_pairs"],
        ),
        (
            "GenerateCRSchedule()\n"
            + PAIR_RUN.format(targets=PAIRS, steps="[TwoQubitCalibration()]"),
            ["coupling_pairs"],
        ),
        (
            "steps = [GenerateCRSchedule()]\n" + PAIR_RUN.format(targets=PAIRS, steps="steps"),
            ["mux_ids", "qids"],
        ),
        (
            "MuxTargets([0])\n" + PAIR_RUN.format(targets=PAIRS, steps=AUTOMATIC),
            ["mux_ids", "qids"],
        ),
        (PAIR_RUN.format(targets="QubitTargets(q)", steps=AUTOMATIC), ["mux_ids", "qids"]),
        # Opaque or mutated step lists are rejected.
        (
            f"steps = {AUTOMATIC}\nsteps.pop(0)\n" + PAIR_RUN.format(targets=PAIRS, steps="steps"),
            ["mux_ids", "qids"],
        ),
        (
            f"steps = {AUTOMATIC}\nsteps.append(make())\nsteps.append(x)\n"
            + PAIR_RUN.format(targets=PAIRS, steps="steps"),
            ["mux_ids", "qids"],
        ),
        (
            f"steps = {AUTOMATIC}\nedit(steps)\n" + PAIR_RUN.format(targets=PAIRS, steps="steps"),
            ["mux_ids", "qids"],
        ),
        (
            "if s:\n    steps = "
            + AUTOMATIC
            + "\nelse:\n    steps = [OpaqueStep()]\n"
            + PAIR_RUN.format(targets=PAIRS, steps="steps"),
            ["mux_ids", "qids"],
        ),
        (PAIR_RUN.format(targets=PAIRS, steps="build_steps()"), ["mux_ids", "qids"]),
        (PAIR_RUN.format(targets="p", steps=AUTOMATIC), ["mux_ids", "qids"]),
        (
            "for g in s:\n    " + PAIR_RUN.format(targets=PAIRS, steps=AUTOMATIC),
            ["mux_ids", "qids"],
        ),
        (f"targets = {PAIRS}\nsteps = {AUTOMATIC}", ["mux_ids", "qids"]),
        ("QubitTargets(q)", ["mux_ids", "qids"]),
    ],
)
def test_supported_target_modes(body, modes):
    assert _modes(body) == modes
    assert supported_target_modes("def run(:", "run") == ["mux_ids", "qids"]


def test_target_modes_ignore_unused_module_helpers():
    scheduled = PAIR_RUN.format(targets=PAIRS, steps=AUTOMATIC)
    unscheduled = PAIR_RUN.format(targets=PAIRS, steps="[OpaqueStep()]")
    helper = "def helper(u, c, p, s):\n    {}\n\n\n"
    # An unused scheduled helper does not enable pairs for the real entrypoint.
    assert _modes(unscheduled, helper.format(scheduled)) == ["mux_ids", "qids"]
    # An unused MUX helper does not disable a valid entrypoint.
    mux_helper = helper.format("CalibService(u, c).run(MuxTargets([0]), steps=[])")
    assert _modes(scheduled, mux_helper) == ["coupling_pairs"]
    # A helper the entrypoint calls may run its own pipeline.
    assert _modes(f"helper(u, c, p, s)\n{scheduled}", mux_helper) == ["mux_ids", "qids"]
    # Module-level pipelines run on import.
    assert _modes(scheduled, "MuxTargets([0])\n") == ["mux_ids", "qids"]


def test_target_modes_follow_the_named_entrypoint():
    source = (
        f"def other(u, c, p, s):\n    {PAIR_RUN.format(targets=PAIRS, steps=AUTOMATIC)}\n\n"
        "def run(u, c):\n    CalibService(u, c).run(QubitTargets(['0']), steps=[])\n"
    )
    assert supported_target_modes(source, "other") == ["coupling_pairs"]
    assert supported_target_modes(source, "run") == ["mux_ids", "qids"]
    assert supported_target_modes(source, "missing") == ["mux_ids", "qids"]


def test_automatic_two_qubit_template_accepts_pairs():
    source = (TEMPLATES / "two_qubit_pairs.py").read_text()
    assert supported_target_modes(source, "two_qubit_pairs") == ["coupling_pairs"]
    two_qubit = (TEMPLATES / "two_qubit.py").read_text()
    assert supported_target_modes(two_qubit, "two_qubit") == ["mux_ids", "qids"]


@pytest.mark.parametrize(
    "steps", ["[]", "[GenerateCRSchedule()]", "[OpaqueStep()]", "[ConfigureAll()]"]
)
def test_unused_pair_step_does_not_enable_pair_overrides(steps):
    assert _modes(
        "unused = TwoQubitCalibration()\n" + PAIR_RUN.format(targets=PAIRS, steps=steps)
    ) == ["mux_ids", "qids"]


def test_each_run_requires_a_pair_step():
    assert _modes(
        PAIR_RUN.format(targets=PAIRS, steps=AUTOMATIC)
        + "\n"
        + PAIR_RUN.format(targets=PAIRS, steps="[]")
    ) == ["mux_ids", "qids"]


@pytest.mark.parametrize("initial", ["[]", "[GenerateCRSchedule()]"])
@pytest.mark.parametrize("pair", ["TwoQubitCalibration()", "CustomTwoQubit(tasks=[])"])
@pytest.mark.parametrize(
    "addition",
    [
        "steps.append({pair})",
        "steps.extend([{pair}])",
        "steps.insert(0, {pair})",
        "steps += [{pair}]",
    ],
)
def test_pair_additions_enable_overrides(initial, pair, addition):
    assert _modes(
        f"steps = {initial}\n{addition.format(pair=pair)}\n"
        + PAIR_RUN.format(targets=PAIRS, steps="steps")
    ) == ["coupling_pairs"]


@pytest.mark.parametrize(
    "body",
    [
        "steps = []\n{run}\nsteps.append(TwoQubitCalibration())",
        "steps = []\nif s:\n    steps.append(TwoQubitCalibration())\n{run}",
        "steps = []\nif s:\n    steps += [TwoQubitCalibration()]\n{run}",
        "steps = []\nsteps.append(TwoQubitCalibration())\nsteps = []\n{run}",
        "steps = [TwoQubitCalibration()]\nif s:\n    steps = []\n{run}",
        "steps = []\n{run}\nsteps.extend([TwoQubitCalibration()])\n{run}",
        "steps = [TwoQubitCalibration()]\n{run}\nsteps = []\n{run}",
        "steps = []\nsteps.append(TwoQubitCalibration())\nsteps.clear()\n{run}",
        "steps = []\nsteps.append(TwoQubitCalibration())\nalias = steps\n{run}",
        "steps = alias = []\nsteps.append(TwoQubitCalibration())\nalias.clear()\n{run}",
        "steps = []\nsteps.append(TwoQubitCalibration())\nedit(steps)\n{run}",
        "steps = []\nsteps.append(TwoQubitCalibration())\nsteps[0] = ConfigureAll()\n{run}",
        "steps = []\nsteps.extend(build_steps())\nsteps.append(TwoQubitCalibration())\n{run}",
        "steps = []\nsteps.append(OpaqueStep())\nsteps.append(TwoQubitCalibration())\n{run}",
        "steps = []\nif s:\n    steps.append(TwoQubitCalibration())\nelse:\n    {run}",
    ],
)
def test_pair_additions_require_guaranteed_presence_at_every_run(body):
    assert _modes(body.format(run=PAIR_RUN.format(targets=PAIRS, steps="steps"))) == [
        "mux_ids",
        "qids",
    ]


@pytest.mark.parametrize(
    "body",
    [
        "steps = []\nsteps.append(TwoQubitCalibration())\n{run}\nsteps.append(ConfigureAll())\n{run}",
        "steps = []\nif s:\n    steps.append(TwoQubitCalibration())\n    {run}",
        "steps = []\nif s:\n    steps.append(TwoQubitCalibration())\n    {run}\nelse:\n    steps.append(CustomTwoQubit(tasks=[]))\n    {run}",
        "steps = [TwoQubitCalibration()]\nif s:\n    steps.append(ConfigureAll())\n{run}",
        "steps = [TwoQubitCalibration()]\n{run}\nsteps = []\nsteps.append(CustomTwoQubit(tasks=[]))\n{run}",
        "pair = TwoQubitCalibration()\nsteps = [pair]\n{run}",
    ],
)
def test_pair_presence_follows_enclosing_blocks_and_each_run(body):
    assert _modes(body.format(run=PAIR_RUN.format(targets=PAIRS, steps="steps"))) == [
        "coupling_pairs"
    ]


def test_manual_pair_addition_still_disallows_overrides():
    assert (
        _modes(
            'steps = []\nsteps.append(CustomTwoQubit(execution_mode="manual", rounds=[]))\n'
            + PAIR_RUN.format(targets=PAIRS, steps="steps")
        )
        == []
    )
