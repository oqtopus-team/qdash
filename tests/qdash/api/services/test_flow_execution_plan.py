"""The execution-plan preview reads saved sources literally and never runs them."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException

from qdash.api.services.flow_service.execution_plan import (
    manual_step_literals,
    resolve_execution_plan,
    uses_manual_rounds,
)
from qdash.api.services.flow_service.plan_preview import build_execution_plan
from qdash.api.services.flow_service.service import FlowService
from qdash.api.services.flow_service.source_store import FlowSourceStore
from qdash.api.services.flow_service.target_defaults import supported_target_modes
from qdash.api.services.manual_round_checks import ChipRoundModel
from qdash.common.mux_mapping import MuxMapping
from tests.qdash.api.services.test_flow_service import (
    _FakeFlowRepository,
    _make_flow,
    _StubCoordinator,
    _StubDeploymentClient,
)

UPDATED = datetime(2026, 11, 1, tzinfo=timezone.utc)
WIRING = [
    {"mux": mux, "ctrl": [f"Q{mux}A-2"], "read_out": f"Q{mux}A-1", "read_in": f"Q{mux}A-0"}
    for mux in range(4)
]
MODEL = ChipRoundModel(wiring=WIRING, coupling_ids=frozenset({"0-1", "4-5", "8-9", "1-0"}))

HEADER = """
from prefect import flow
from qdash.workflow import TaskCall
from qdash.workflow.service import CalibService
from qdash.workflow.service.steps import *
from qdash.workflow.service.targets import MuxTargets, QubitTargets
"""

MANUAL = (
    HEADER
    + """
ROUNDS = [["0", "8"], ["1", "9"]]


@flow
def my_flow(username, chip_id, project_id=None, flow_name=None, use_pairs=True):
    cal = CalibService(username, chip_id, project_id=project_id, flow_name=flow_name)
    one = CustomOneQubit(
        step_name="rabi",
        execution_mode="manual",
        rounds=ROUNDS,
        tasks=[TaskCall(name="CheckRabi"), TaskCall(name="CheckT1", call_id="t1")],
    )
    steps = [one]
    if use_pairs:
        steps = [
            one,
            CustomTwoQubit(
                step_name="cr",
                execution_mode="manual",
                rounds=[[("0", "1"), ("8", "9")]],
                tasks=[TaskCall(name="CheckCrossResonance")],
            ),
        ]
    return cal.run(QubitTargets(["0", "8", "1", "9"]), steps=steps)
"""
)


def _source(body: str, signature: str = "username, chip_id") -> str:
    indented = "\n".join(f"    {line}" if line else "" for line in body.strip().splitlines())
    return HEADER + f"\n\n@flow\ndef my_flow({signature}):\n" + indented + "\n"


def _plan(
    code: str, parameters: dict[str, Any] | None = None, model: ChipRoundModel = MODEL
) -> Any:
    loads: list[int] = []

    def chip_model() -> ChipRoundModel:
        loads.append(1)
        return model

    response = build_execution_plan(
        flow_name="my_flow",
        chip_id="chip-1",
        updated_at=UPDATED,
        code=code,
        function_name="my_flow",
        parameters=parameters or {},
        chip_model=chip_model,
    )
    assert len(loads) <= 1  # the chip is read at most once per preview
    return response


# ---------------------------------------------------------------------------
# Static extraction
# ---------------------------------------------------------------------------


def test_the_manual_example_resolves_to_its_exact_rounds() -> None:
    plan = _plan(MANUAL)
    assert plan.status == "resolved" and plan.reason is None
    [run] = plan.runs
    assert run.targets.qids == ["0", "8", "1", "9"]
    rabi, cr = run.steps
    assert (rabi.schedule, rabi.scope, rabi.tasks) == ("manual", "qubit", ["CheckRabi", "CheckT1"])
    assert [r.targets for r in rabi.rounds] == [["0", "8"], ["1", "9"]]
    assert [r.number for r in rabi.rounds] == [1, 2]
    assert (cr.schedule, cr.scope) == ("manual", "coupling")
    assert [r.targets for r in cr.rounds] == [["0-1", "8-9"]]
    assert "in the order written" in rabi.summary and "pulse timing" in rabi.summary
    assert rabi.issues == [] and rabi.unchecked == []
    assert not plan.target_override_allowed and plan.has_manual_rounds


def test_known_parameters_select_the_branch_that_runs() -> None:
    [run] = _plan(MANUAL, {"use_pairs": False}).runs
    assert [step.name for step in run.steps] == ["rabi"]


def test_the_bundled_fast_template_previews_both_configure_all_steps() -> None:
    # The fast template reconfigures before fine-tuning; each ConfigureAll keeps its own name.
    import qdash.workflow as workflow

    code = (Path(workflow.__file__).parent / "templates" / "fast_full_calibration.py").read_text()
    response = build_execution_plan(
        flow_name="fast_full_calibration",
        chip_id="chip-1",
        updated_at=UPDATED,
        code=code,
        function_name="fast_full_calibration",
        parameters={"mux_ids": [0, 1]},
        chip_model=lambda: MODEL,
    )
    assert response.status == "resolved" and response.reason is None
    [run] = response.runs
    names = [step.name for step in run.steps]
    assert names[:5] == [
        "configure_all",
        "one_qubit_check",
        "filter_by_status",
        "configure_all_before_fine_tune",
        "one_qubit_fine_tune",
    ]


def test_automatic_steps_are_described_not_computed() -> None:
    code = _source(
        """
cal = CalibService(username, chip_id)
cal.run(MuxTargets([0, 1]), steps=[
    OneQubitCheck(),
    FilterByStatus(),
    CustomOneQubit(step_name="ramsey", tasks=[TaskCall(name="CheckRamsey")], execution_mode="parallel_by_mux"),
    GenerateCRSchedule(max_parallel_ops=3),
    TwoQubitCalibration(max_parallel_ops=4),
])
"""
    )
    plan = _plan(code)
    assert plan.status == "resolved"
    check, status, ramsey, schedule, full = plan.runs[0].steps
    assert (check.schedule, check.rounds, check.tasks[:1]) == ("automatic", [], ["CheckRabi"])
    assert "at run time" in check.summary
    assert status.schedule == "none"
    assert ramsey.execution_mode == "parallel_by_mux" and ramsey.rounds == []
    assert schedule.schedule == "none" and "at most 3 pairs" in schedule.summary
    assert schedule.rounds == []
    assert full.schedule == "automatic" and "earlier GenerateCRSchedule" in full.summary
    assert "at most 4 pairs" not in full.summary
    assert "not regrouped" in full.summary
    assert plan.target_override_allowed


@pytest.mark.parametrize(
    ("body", "signature", "reason"),
    [
        (
            "cal = CalibService(username, chip_id)\nif flag:\n    cal.run(QubitTargets(['0']), [OneQubitCheck()])",
            "username, chip_id, flag",
            "if statement whose condition is only known at run time",
        ),
        (
            "cal = CalibService(username, chip_id)\nfor qid in ['0', '1']:\n    cal.run(QubitTargets([qid]), [OneQubitCheck()])",
            "username, chip_id",
            "inside a for block",
        ),
        (
            "cal = CalibService(username, chip_id)\nsteps = [OneQubitCheck()]\nsteps.append(OneQubitFineTune())\ncal.run(QubitTargets(['0']), steps)",
            "username, chip_id",
            "step list 'steps' is built or changed at run time",
        ),
        (
            "cal = CalibService(username, chip_id)\ncal.run(QubitTargets(['0']), make_steps())",
            "username, chip_id",
            "calls make_steps(), which is not followed",
        ),
        (
            "cal = CalibService(username, chip_id)\ncal.run(QubitTargets(['0']), [CustomOneQubit(tasks=[], execution_mode=mode)])",
            "username, chip_id, mode",
            "execution_mode of CustomOneQubit(...) is not a literal value",
        ),
        (
            "cal = CalibService(username, chip_id)\n[cal.run(QubitTargets([q]), [OneQubitCheck()]) for q in '01']",
            "username, chip_id",
            "comprehension",
        ),
        ("print('no pipeline')", "username, chip_id", "no CalibService.run"),
    ],
)
def test_dynamic_sources_are_unresolved_without_a_partial_plan(
    body: str, signature: str, reason: str
) -> None:
    plan = _plan(_source(body, signature))
    assert plan.status == "unresolved"
    assert reason in (plan.reason or "")
    assert plan.runs == []


RUN = "cal.run(QubitTargets(['0']), [OneQubitCheck()])"
RUN_TWO = "cal.run(QubitTargets(['1']), [OneQubitFineTune()])"


@pytest.mark.parametrize(
    ("body", "signature", "parameters", "reason"),
    [
        # A return on a runtime value may end a successful run before cal.run.
        (
            f"cal = CalibService(username, chip_id)\nif stop:\n    return None\n{RUN}",
            "username, chip_id, stop",
            {},
            "the return at line",
        ),
        (
            f"cal = CalibService(username, chip_id)\nif stop:\n    pass\nelse:\n    return None\n{RUN}",
            "username, chip_id, stop",
            {},
            "on a condition only known at run time",
        ),
        # Between two runs, the second one is uncertain: no partial plan.
        (
            f"cal = CalibService(username, chip_id)\n{RUN}\nif stop:\n    return None\n{RUN_TWO}",
            "username, chip_id, stop",
            {},
            "the return at line",
        ),
        # Nested inside a known branch, a loop, or a try block.
        (
            f"cal = CalibService(username, chip_id)\nif True:\n    if stop:\n        return None\n{RUN}",
            "username, chip_id, stop",
            {},
            "the return at line",
        ),
        (
            f"cal = CalibService(username, chip_id)\nfor q in qids:\n    if q == '0':\n        return None\n{RUN}",
            "username, chip_id, qids",
            {},
            "from inside a for block",
        ),
        (
            f"cal = CalibService(username, chip_id)\ntry:\n    x = int(value)\nexcept ValueError:\n    return None\n{RUN}",
            "username, chip_id, value",
            {},
            "from inside a try block",
        ),
        (
            f"cal = CalibService(username, chip_id)\ntry:\n    pass\nfinally:\n    return None\n{RUN}",
            "username, chip_id",
            {},
            "from inside a try block",
        ),
        # An exception a with block may suppress can skip the run inside it.
        (
            f"cal = CalibService(username, chip_id)\nwith guard:\n    if stop:\n        raise ValueError('x')\n    {RUN}",
            "username, chip_id, stop, guard",
            {},
            "may be suppressed by a with block",
        ),
        # A known condition decides; a known return before any run leaves nothing to show.
        (
            f"cal = CalibService(username, chip_id)\nif stop:\n    return None\n{RUN}",
            "username, chip_id, stop",
            {"stop": True},
            "returns at line",
        ),
        (
            f"cal = CalibService(username, chip_id)\nreturn None\n{RUN}",
            "username, chip_id",
            {},
            "returns at line",
        ),
        # A raise reached with the saved parameters fails the run there.
        (
            f"cal = CalibService(username, chip_id)\nraise RuntimeError('disabled')\n{RUN}",
            "username, chip_id",
            {},
            "raises an exception at line",
        ),
        (
            f"cal = CalibService(username, chip_id)\nif stop:\n    raise RuntimeError('x')\n{RUN}",
            "username, chip_id, stop=True",
            {},
            "raises an exception at line",
        ),
        (
            f"cal = CalibService(username, chip_id)\n{RUN}\nraise RuntimeError('after')",
            "username, chip_id",
            {},
            "raises an exception at line",
        ),
        (
            f"cal = CalibService(username, chip_id)\nassert stop\n{RUN}",
            "username, chip_id, stop=False",
            {},
            "raises an exception at line",
        ),
        # Calls that may end the entrypoint or run elsewhere are not followed.
        (
            f"import sys\ncal = CalibService(username, chip_id)\nif stop:\n    sys.exit(0)\n{RUN}",
            "username, chip_id, stop",
            {},
            "sys.exit(), which is not followed",
        ),
        (
            "cal = CalibService(username, chip_id)\nother = cal\nother.run(QubitTargets(['0']), [OneQubitCheck()])",
            "username, chip_id",
            {},
            "other.run(), which is not a CalibService",
        ),
    ],
)
def test_early_exits_never_leave_an_exact_plan(
    body: str, signature: str, parameters: dict[str, Any], reason: str
) -> None:
    plan = _plan(_source(body, signature), parameters)
    assert plan.status == "unresolved"
    assert reason in (plan.reason or ""), plan.reason
    assert plan.runs == []


def test_known_and_final_exits_keep_the_plan_exact() -> None:
    # A known false condition skips the return; the run happens.
    code = _source(
        f"cal = CalibService(username, chip_id)\nif stop:\n    return None\n{RUN}",
        "username, chip_id, stop=False",
    )
    assert [len(run.steps) for run in _plan(code).runs] == [1]
    # Code after an unconditional return never runs.
    code = _source(
        f"cal = CalibService(username, chip_id)\nreturn {RUN}\n{RUN_TWO}", "username, chip_id"
    )
    plan = _plan(code)
    assert plan.status == "resolved"
    assert [run.targets.qids for run in plan.runs] == [["0"]]
    # A return on a runtime value after the last run cannot skip a run.
    code = _source(
        f"cal = CalibService(username, chip_id)\nresult = {RUN}\nif not result:\n    return None\nreturn result",
        "username, chip_id",
    )
    assert _plan(code).status == "resolved"


def test_checks_that_may_raise_fail_the_run_without_changing_its_steps() -> None:
    # The usual guard: a failing check stops the run; a run that proceeds runs these steps.
    code = _source(
        """
if not qids:
    raise ValueError("qids is required")
assert len(qids) < 64
cal = CalibService(username, chip_id)
cal.run(QubitTargets(qids), [OneQubitCheck()])
""",
        "username, chip_id, qids",
    )
    plan = _plan(code)
    assert plan.status == "resolved"
    [run] = plan.runs
    assert run.targets is None and [step.name for step in run.steps] == ["one_qubit_check"]


def test_targets_the_dialog_may_override_are_not_read_from_saved_parameters() -> None:
    # Without manual rounds the dialog may replace qids, so the saved value is not trusted;
    # the guard on it is a runtime check.
    code = _source(
        """
if qids is None:
    raise ValueError("qids is required")
cal = CalibService(username, chip_id)
cal.run(QubitTargets(qids), [OneQubitCheck()])
""",
        "username, chip_id, qids=None",
    )
    plan = _plan(code, {"qids": None})
    assert plan.status == "resolved" and plan.runs[0].targets is None
    # With manual rounds no override is accepted, so the saved value decides.
    manual = code.replace(
        "[OneQubitCheck()]",
        "[CustomOneQubit(tasks=[TaskCall(name='CheckRabi')], execution_mode='manual', rounds=[['0']])]",
    )
    plan = _plan(manual, {"qids": None})
    assert plan.status == "unresolved" and "raises an exception at line" in (plan.reason or "")
    assert _plan(manual, {"qids": ["0"]}).runs[0].targets.qids == ["0"]


def test_helpers_defined_in_the_file_are_not_followed() -> None:
    code = MANUAL + "\n\ndef helper():\n    return []\n"
    code = code.replace("steps = [one]", "steps = [one] + helper()")
    plan = resolve_execution_plan(code, "my_flow", {})
    assert not plan.resolved and "helper" in (plan.reason or "")


def test_preview_never_imports_or_executes_the_source(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    code = f"open({str(marker)!r}, 'w').write('x')\nraise SystemExit(1)\n" + MANUAL
    plan = _plan(code)
    assert not marker.exists()
    assert plan.status == "resolved"


def test_syntax_errors_and_missing_entrypoints_are_reasons() -> None:
    assert "does not parse" in (_plan("def my_flow(:\n").reason or "")
    assert "my_flow() is not defined" in (_plan("x = 1\n").reason or "")


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def test_round_conflicts_make_the_plan_invalid() -> None:
    code = MANUAL.replace('[("0", "1"), ("8", "9")]', '[("1", "0"), ("2", "3")]').replace(
        '[["0", "8"], ["1", "9"]]', '[["0", "1"], ["8", "9"]]'
    )
    plan = _plan(code)
    assert plan.status == "invalid"
    rabi, cr = plan.runs[0].steps
    assert [(i.round, i.targets) for i in rabi.issues] == [(1, ["0", "1"]), (2, ["8", "9"])]
    messages = [issue.message for issue in cr.issues]
    assert any("2-3 is not a coupling" in m for m in messages)
    assert any("qubit 2, 3 of 2-3 is not among" in m for m in messages)


def test_candidates_are_checked_only_while_the_targets_are_still_the_candidates() -> None:
    code = _source(
        """
cal = CalibService(username, chip_id)
cal.run(QubitTargets(["0", "8", "4"]), steps=[
    CustomOneQubit(step_name="a", tasks=[TaskCall(name="CheckRabi")], execution_mode="manual", rounds=[["0", "8"]]),
    FilterByStatus(),
    CustomOneQubit(step_name="b", tasks=[TaskCall(name="CheckT1")], execution_mode="manual", rounds=[["0"]]),
])
"""
    )
    first, _, second = _plan(code).runs[0].steps
    assert [issue.message for issue in first.issues] == [
        "current qubits 4 are in no round; add them to a round or remove them from the targets"
    ]
    assert second.issues == []
    assert any("checked when it starts" in reason for reason in second.unchecked)


def test_mux_targets_use_the_wiring_and_missing_wiring_is_reported() -> None:
    code = _source(
        """
cal = CalibService(username, chip_id)
cal.run(MuxTargets([0, 2], exclude_qids=["2", "3", "10", "11"]), steps=[
    CustomOneQubit(tasks=[TaskCall(name="CheckRabi")], execution_mode="manual", rounds=[["0", "8"], ["1", "9"]]),
])
"""
    )
    assert _plan(code).status == "resolved"
    plan = _plan(code, model=ChipRoundModel(wiring=None, wiring_error="no wiring"))
    [step] = plan.runs[0].steps
    assert plan.status == "resolved" and "no wiring" in step.unchecked


def test_known_invalid_manual_literals_block_an_unresolved_plan() -> None:
    code = _source(
        """
cal = CalibService(username, chip_id)
steps = [CustomTwoQubit(tasks=[TaskCall(name="CheckCrossResonance")], execution_mode="manual", rounds=[[("0", "0")]], max_parallel_ops=4)]
steps.append(OneQubitCheck())
cal.run(QubitTargets(["0"]), steps)
"""
    )
    plan = _plan(code)
    assert plan.status == "invalid" and plan.runs == []
    assert any("max_parallel_ops" in issue.message for issue in plan.issues)


def test_manual_literals_disable_target_overrides() -> None:
    assert uses_manual_rounds(MANUAL)
    found = manual_step_literals(MANUAL)
    # ROUNDS is a module constant: without the entrypoint's bindings it is not literal.
    assert [(step.name, step.literal) for step in found] == [("rabi", False), ("cr", True)]
    assert supported_target_modes(MANUAL, "my_flow") == []
    plain = MANUAL.replace('execution_mode="manual",', "").replace("rounds=", "_rounds=")
    assert not uses_manual_rounds(plain)
    assert supported_target_modes(plain, "my_flow") == ["mux_ids", "qids"]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class _ChipRepository:
    def __init__(self, chips: set[str]) -> None:
        self.chips = chips
        self.calls: list[str] = []
        self.topology_id: str | None = None

    def find_by_id(self, project_id: str, chip_id: str) -> Any:
        self.calls.append(f"find:{project_id}:{chip_id}")
        if chip_id not in self.chips:
            return None
        return SimpleNamespace(chip_id=chip_id, topology_id=self.topology_id)

    def get_coupling_ids(self, project_id: str, chip_id: str) -> list[str]:
        self.calls.append(f"couplings:{project_id}:{chip_id}")
        return ["0-1", "8-9"]


def _service(tmp_path: Path, code: str, chips: set[str]) -> tuple[FlowService, Any, Any]:
    path = tmp_path / "my_flow.py"
    path.write_text(code)
    repo = _FakeFlowRepository(flow=_make_flow(path, updated_at=UPDATED))
    coordinator = _StubCoordinator()
    chip_repo = _ChipRepository(chips)
    service = FlowService(
        flow_repository=cast("Any", repo),
        coordinator=cast("Any", coordinator),
        source_store=FlowSourceStore(tmp_path),
        deployment_client=cast("Any", _StubDeploymentClient()),
        chip_repository=cast("Any", chip_repo),
    )
    return service, repo, chip_repo


@pytest.mark.asyncio
async def test_service_previews_the_saved_source_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "qdash.api.services.manual_round_checks.load_wiring_entries", lambda path, chip: WIRING
    )
    service, repo, chips = _service(tmp_path, MANUAL, {"chip-1"})
    before = (tmp_path / "my_flow.py").read_text()

    plan = await service.get_execution_plan("my_flow", "alice", "project-1", None)

    assert plan.status == "resolved" and plan.chip_id == "chip-1"
    assert plan.source_updated_at == UPDATED
    assert chips.calls == ["find:project-1:chip-1", "couplings:project-1:chip-1"]
    # Nothing is written, dispatched or scheduled.
    assert repo.created == [] and repo.updated == [] and repo.deleted == []
    assert (tmp_path / "my_flow.py").read_text() == before


@pytest.mark.asyncio
async def test_service_rejects_unknown_flows_and_chips(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path, MANUAL, {"chip-1"})
    with pytest.raises(HTTPException) as error:
        await service.get_execution_plan("my_flow", "alice", "project-1", "other-chip")
    assert error.value.status_code == 404 and "other-chip" in str(error.value.detail)

    empty, _, _ = _service(tmp_path, MANUAL, set())
    cast("Any", empty)._flow_repo.flow = None
    with pytest.raises(HTTPException) as error:
        await empty.get_execution_plan("my_flow", "alice", "project-1", "chip-1")
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_execute_rejects_target_overrides_for_manual_flows(tmp_path: Path) -> None:
    from qdash.api.schemas.flow import ExecuteFlowRequest
    from qdash.datamodel.flow_targets import FlowTargetOverride

    service, _, _ = _service(tmp_path, MANUAL, {"chip-1"})
    request = ExecuteFlowRequest(target_override=FlowTargetOverride(qids=["0"]))
    with pytest.raises(HTTPException) as error:
        await service.execute_flow("my_flow", request, "alice", "project-1")
    assert error.value.status_code == 400
    assert "Target overrides are not accepted" in str(error.value.detail)
    assert cast("Any", service)._coordinator.run_calls == []


# ---------------------------------------------------------------------------
# Topology MUX mapping
# ---------------------------------------------------------------------------

# Synthetic topology: sparse MUX IDs, MUX 9 owns 41 (``qid // 4`` would say MUX 10)
# and qubit 20 is standalone.
SPARSE_MODEL = ChipRoundModel(
    wiring=[
        {"mux": 9, "ctrl": ["Q9A-0", "Q9A-1", "Q9A-2"], "read_out": "R9A-0"},
        {"mux": 2, "ctrl": ["Q2A-0"], "read_out": "R2A-0"},
    ],
    coupling_ids=frozenset({"36-41"}),
    mux_mapping=MuxMapping.from_groups(
        {9: ["36", "41", "38"], 2: ["5"]}, known_qids=["36", "41", "38", "5", "20"]
    ),
)


def _sparse_source(rounds: str) -> str:
    return _source(
        f"""
cal = CalibService(username, chip_id)
cal.run(MuxTargets([9, 2], exclude_qids=["38"]), steps=[
    CustomOneQubit(tasks=[TaskCall(name="CheckRabi")], execution_mode="manual", rounds={rounds}),
])
"""
    )


def test_preview_resolves_mux_targets_and_rounds_with_the_topology_mapping() -> None:
    plan = _plan(_sparse_source('[["36", "5"], ["41"]]'), model=SPARSE_MODEL)
    assert plan.status == "resolved"
    [step] = plan.runs[0].steps
    assert step.issues == [] and step.unchecked == []
    assert [r.targets for r in step.rounds] == [["36", "5"], ["41"]]

    shared = _plan(_sparse_source('[["36", "41"], ["5"]]'), model=SPARSE_MODEL)
    assert shared.status == "invalid"
    [step] = shared.runs[0].steps
    assert any("share MUX 9" in issue.message for issue in step.issues)


def test_preview_rejects_rounds_against_an_unusable_topology() -> None:
    model = ChipRoundModel(
        wiring=None, mapping_error="the MUX mapping of chip 'chip-1' is unusable"
    )
    plan = _plan(_sparse_source('[["36"]]'), model=model)
    assert plan.status == "invalid"
    [step] = plan.runs[0].steps
    assert [issue.message for issue in step.issues] == [
        "the MUX mapping of chip 'chip-1' is unusable"
    ]


def test_round_model_of_a_topology_without_muxes_reads_no_wiring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qdash.api.services import manual_round_checks

    mapping = MuxMapping.from_groups({}, known_qids=["0", "1"])
    monkeypatch.setattr(manual_round_checks, "resolve_chip_mux_mapping", lambda p, c: mapping)

    def no_config() -> Any:
        raise AssertionError("a topology without MUXes must not read wiring.yaml")

    monkeypatch.setattr(manual_round_checks, "resolve_config_base_path", no_config)
    model = manual_round_checks.load_chip_round_model("project", "chip-1", None)
    assert model.wiring == [] and model.mux_mapping is mapping and model.mapping_error is None


def test_round_model_keeps_an_unusable_topology_as_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from qdash.api.services import manual_round_checks
    from qdash.common.mux_mapping import MuxMappingError

    def broken(project_id: str, chip_id: str) -> MuxMapping:
        raise MuxMappingError("Topology 'gone' not found")

    monkeypatch.setattr(manual_round_checks, "resolve_chip_mux_mapping", broken)
    monkeypatch.setattr(manual_round_checks, "resolve_config_base_path", lambda: tmp_path)
    model = manual_round_checks.load_chip_round_model("project", "chip-1", None)
    assert model.mux_mapping is None
    assert model.mapping_error is not None and "Topology 'gone' not found" in model.mapping_error


@pytest.mark.asyncio
async def test_service_preview_uses_the_topology_of_the_chip_it_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from qdash.api.services.flow_service import service as service_module

    wiring = SPARSE_MODEL.wiring
    monkeypatch.setattr(
        "qdash.api.services.manual_round_checks.load_wiring_entries", lambda path, chip: wiring
    )
    requested: list[str | None] = []

    def resolve(topology_id: str | None) -> MuxMapping:
        requested.append(topology_id)
        assert SPARSE_MODEL.mux_mapping is not None
        return SPARSE_MODEL.mux_mapping

    monkeypatch.setattr(service_module, "resolve_topology_mux_mapping", resolve)
    service, _, chips = _service(tmp_path, _sparse_source('[["36", "41"], ["5"]]'), {"chip-1"})
    chips.topology_id = "synthetic-sparse"

    plan = await service.get_execution_plan("my_flow", "alice", "project-1", None)

    assert requested == ["synthetic-sparse"]
    assert plan.status == "invalid"
    [step] = plan.runs[0].steps
    assert any("share MUX 9" in issue.message for issue in step.issues)


@pytest.mark.parametrize(
    "target", ['CouplingTargets([("0", "1")])', 'QubitTargets(["0", "1"])', "MuxTargets([0])"]
)
def test_automatic_preview_distinguishes_pair_selection(target):
    plan = _plan(
        _source(
            f"cal = CalibService(username, chip_id)\ncal.run({target}, [TwoQubitCalibration(max_parallel_ops=2)])"
        )
    )
    assert plan.status == "resolved"
    [step] = plan.runs[0].steps
    assert step.rounds == []
    assert "at most 2 pairs" in step.summary
    if target.startswith("CouplingTargets"):
        assert "no pair is added or reversed" in step.summary
    else:
        assert "picks the pairs among the candidate qubits" in step.summary


def test_bundled_manual_template_previews_and_disallows_overrides():
    import qdash.workflow as workflow

    code = (Path(workflow.__file__).parent / "templates" / "two_qubit_manual_rounds.py").read_text()
    plan = build_execution_plan(
        flow_name="manual",
        chip_id="chip-1",
        updated_at=UPDATED,
        code=code,
        function_name="two_qubit_manual_rounds",
        parameters={},
        chip_model=lambda: MODEL,
    )
    assert plan.status == "resolved", plan.reason
    assert not plan.target_override_allowed
    assert supported_target_modes(code, "two_qubit_manual_rounds") == []
    [step] = plan.runs[0].steps
    assert step.schedule == "manual"
    assert [r.targets for r in step.rounds] == [["0-1", "4-5"], ["8-9"]]
