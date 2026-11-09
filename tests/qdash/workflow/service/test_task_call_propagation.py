"""Call identity reaches every scheduling path, and each path keeps its own barriers.

The parallel runners normally fan out to Dask processes. Here they run the same
worker functions (``calibrate_mux_qubits``, ``calibrate_single_qubit``,
``execute_coupling_pair``, ``calibrate_qubit_batch`` paths) in-process, with
the isolated session replaced by a recording fake, so the test sees exactly
which call each target executed, in which order, and with which identity.
"""

from __future__ import annotations

import itertools
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

import qdash.workflow.calibtasks.qubex  # noqa: F401 - registers the qubex tasks
from qdash.datamodel.task_call import TaskCall
from qdash.workflow.service._internal import scheduling_tasks
from qdash.workflow.service.results import OneQubitResult
from qdash.workflow.service.steps import (
    BringUp,
    CustomOneQubit,
    CustomTwoQubit,
    FilterByStatus,
    StepContext,
)
from qdash.workflow.service.targets import MuxTargets, QubitTargets

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService

REPEATED = [
    TaskCall(name="CheckRamsey", call_id="ramsey_coarse", run={"detuning": 0.001}),
    TaskCall(name="CheckRamsey", call_id="ramsey_fine", run={"detuning": 0.0002}),
]


class RecordingSession:
    """A worker session that records calls and fails where it is told to."""

    backend_name = "qubex"

    def __init__(self, log: list[tuple[str, str, str, str]], fail: set[tuple[str, str]]) -> None:
        self.log = log
        self.fail = fail
        self.parameters: dict[str, Any] = {}
        self.ids = itertools.count()

    def execute_task(
        self, task_name: str, qid: str, *, parameters: Any = None, invocation: Any = None
    ) -> dict[str, Any]:
        task_id = f"task-{next(self.ids)}-{qid}-{invocation.call_id}"
        self.log.append((invocation.step_id, invocation.call_id, task_name, qid))
        self.parameters[invocation.call_id] = parameters
        assert invocation.plan_digest == "digest-1"
        if (invocation.call_id, qid) in self.fail:
            error = ValueError("rejected")
            error.qdash_task_ids = {qid: task_id}  # type: ignore[attr-defined]
            raise error
        return {"task_id": task_id}

    def execute_task_batch(
        self, task_name: str, qids: list[str], *, parameters: Any = None, invocation: Any = None
    ) -> dict[str, dict[str, Any]]:
        results = {}
        self.parameters[invocation.call_id] = parameters
        for qid in qids:
            self.log.append((invocation.step_id, invocation.call_id, task_name, qid))
            failed = (invocation.call_id, qid) in self.fail
            results[qid] = {
                "task_id": f"task-{next(self.ids)}-{qid}-{invocation.call_id}",
                "status": "failed" if failed else "success",
            }
        return results

    def finish_calibration(self, **_: Any) -> None:
        pass


def _service() -> CalibService:
    return cast(
        "CalibService",
        SimpleNamespace(
            username="alice",
            chip_id="64Q",
            backend_name="qubex",
            execution_id="exec-1",
            project_id="project-1",
            default_run_parameters={},
            task_parameters={},
            configuration_mode=None,
            tags=[],
            flow_name="flow",
            note={},
            plan_digest="digest-1",
            record_stage_result=lambda *args: None,
        ),
    )


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Run the Dask fan-out in-process with recording isolated sessions."""
    from qdash.workflow.service import strategy

    log: list[tuple[str, str, str, str]] = []
    fail: set[tuple[str, str]] = set()
    sessions: list[RecordingSession] = []
    groups: list[list[str]] = []

    def isolated(session_config: dict[str, Any], qids: list[str]) -> RecordingSession:
        session = RecordingSession(log, fail)
        sessions.append(session)
        return session

    monkeypatch.setattr(scheduling_tasks, "_create_isolated_session", isolated)

    def mux_parallel(*, mux_groups: list[list[str]], plan: Any, session_config: Any) -> Any:
        groups.extend(mux_groups)
        results: dict[str, Any] = {}
        for group in mux_groups:
            results.update(scheduling_tasks.calibrate_mux_qubits(group, plan, session_config))
        return results

    def qubit_parallel(*, qids: list[str], plan: Any, session_config: Any) -> Any:
        groups.append(list(qids))
        return dict(
            scheduling_tasks.calibrate_single_qubit(qid, plan, session_config) for qid in qids
        )

    def coupling_parallel(*, coupling_qids: list[str], plan: Any, session_config: Any) -> Any:
        groups.append(list(coupling_qids))
        return dict(
            scheduling_tasks.execute_coupling_pair(cqid, plan, session_config)
            for cqid in coupling_qids
        )

    monkeypatch.setattr(strategy, "run_mux_calibrations_parallel", mux_parallel)
    monkeypatch.setattr(strategy, "run_qubit_calibrations_parallel", qubit_parallel)
    monkeypatch.setattr(scheduling_tasks, "run_coupling_calibrations_parallel", coupling_parallel)
    monkeypatch.setattr(
        "qdash.workflow.service.strategy.OneQubitStrategy._get_wiring_config_path",
        lambda self, chip_id: "wiring.yaml",
    )
    return SimpleNamespace(log=log, fail=fail, sessions=sessions, groups=groups)


def _schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    from qdash.workflow.service import strategy

    schedule = SimpleNamespace(
        # Box-scheduled MUX groups and synchronized rounds over the same four qubits.
        stages=[SimpleNamespace(box_type="A", parallel_groups=[["0", "1"], ["4", "5"]])],
        steps=[
            SimpleNamespace(box_type="A", parallel_qids=["0", "4"], step_index=0),
            SimpleNamespace(box_type="A", parallel_qids=["1", "5"], step_index=1),
        ],
        total_steps=2,
        metadata={},
    )
    scheduler = SimpleNamespace(
        generate_from_mux=lambda **_: schedule,
        generate_synchronized_from_mux=lambda **_: schedule,
        generate_simultaneous_spectroscopy_batches_from_mux=lambda **_: schedule,
    )
    monkeypatch.setattr(strategy, "OneQubitScheduler", lambda **_: scheduler)


def _per_target(log: list[tuple[str, str, str, str]], qid: str) -> list[str]:
    return [call_id for _, call_id, _, target in log if target == qid]


@pytest.mark.parametrize("mode", ["synchronized", "scheduled"])
def test_parallel_modes_run_every_call_per_target_in_order(
    recorder: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    _schedule(monkeypatch)
    recorder.fail.add(("ramsey_coarse", "4"))
    step = CustomOneQubit(step_name="ramsey", mode=mode, tasks=list(REPEATED))

    ctx = step.execute(_service(), QubitTargets(["0", "1", "4", "5"]), StepContext())

    result = ctx.get_step_result("ramsey")
    assert result is not None
    for qid in ("0", "1", "5"):
        assert _per_target(recorder.log, qid) == ["ramsey_coarse", "ramsey_fine"]
        calls = result.get_qubit(qid).calls  # type: ignore[union-attr]
        assert [call.status for call in calls] == ["success", "success"]
        assert len({call.task_id for call in calls}) == 2
    # Fail-fast is per target: qubit 4 stops after its coarse call, the others continue.
    assert _per_target(recorder.log, "4") == ["ramsey_coarse"]
    assert [call.status for call in result.get_qubit("4").calls] == ["failed", "skipped"]  # type: ignore[union-attr]
    assert {step_id for step_id, *_ in recorder.log} == {"ramsey"}
    # Each call carried its own settings to the worker.
    for session in recorder.sessions:
        for call in REPEATED:
            if call.resolved_call_id in session.parameters:
                assert session.parameters[call.resolved_call_id] == call.settings()
    # 4 targets x 2 calls, minus the call skipped after qubit 4's failure.
    task_ids = {
        call.task_id
        for data in result.qubits.values()  # type: ignore[union-attr]
        for call in data.calls
        if call.task_id
    }
    assert len(task_ids) == 7
    if mode == "scheduled":
        # One worker per MUX group runs its qubits one after another.
        assert recorder.groups == [["0", "1"], ["4", "5"]]
        assert len(recorder.sessions) == 2
    else:
        # Synchronized rounds; each qubit has its own worker.
        assert recorder.groups == [["0", "4"], ["1", "5"]]
        assert len(recorder.sessions) == 4


def test_serial_mode_runs_calls_in_the_parent_session(
    recorder: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from qdash.workflow.service.session_context import clear_current_session, set_current_session

    _schedule(monkeypatch)
    parent = RecordingSession(recorder.log, recorder.fail)
    set_current_session(cast("CalibService", parent))
    try:
        step = CustomOneQubit(step_name="ramsey", mode="serial", tasks=list(REPEATED))
        ctx = step.execute(_service(), QubitTargets(["0", "1"]), StepContext())
    finally:
        clear_current_session()

    assert recorder.sessions == []
    assert [(call_id, qid) for _, call_id, _, qid in recorder.log] == [
        ("ramsey_coarse", "0"),
        ("ramsey_fine", "0"),
        ("ramsey_coarse", "1"),
        ("ramsey_fine", "1"),
    ]
    assert ctx.get_step_result("ramsey").get_qubit("1").call("ramsey_fine").status == "success"  # type: ignore[union-attr]


def test_mux_tasks_run_on_representatives_and_are_skipped_on_the_others(
    recorder: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _schedule(monkeypatch)
    step = BringUp(
        mode="scheduled",
        tasks=[
            TaskCall(name="CheckResonatorSpectroscopy"),
            TaskCall(name="CheckT1"),
        ],
    )

    ctx = step.execute(_service(), MuxTargets(mux_ids=[0, 1]), StepContext())

    result = ctx.get_step_result("bringup")
    assert result is not None
    assert _per_target(recorder.log, "0") == ["CheckResonatorSpectroscopy", "CheckT1"]
    assert _per_target(recorder.log, "1") == ["CheckT1"]
    skipped = result.get_qubit("1").call("CheckResonatorSpectroscopy")  # type: ignore[union-attr]
    assert skipped is not None
    assert (skipped.status, skipped.reason, skipped.task_id) == (
        "skipped",
        "not_mux_representative",
        None,
    )
    # 2 representatives x 2 calls + 2 members x 1 call.
    assert len(recorder.log) == 6
    assert result.get_qubit("1").status == "success"  # type: ignore[union-attr]


def test_batch_mode_runs_each_call_once_per_batch(
    recorder: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _schedule(monkeypatch)
    parent = RecordingSession(recorder.log, recorder.fail)
    recorder.fail.add(("spec_coarse", "4"))
    monkeypatch.setattr("qdash.workflow.service.one_qubit_stage_runner.get_session", lambda: parent)
    step = CustomOneQubit(
        step_name="spectroscopy",
        mode="simultaneous_spectroscopy",
        tasks=[
            TaskCall(name="CheckQubitSpectroscopy", call_id="spec_coarse"),
            TaskCall(name="CheckQubitSpectroscopy", call_id="spec_fine", run={"shots": 2048}),
        ],
    )
    ctx = step.execute(_service(), QubitTargets(["0", "1", "4", "5"]), StepContext())

    # One batch per schedule round and call; qubit 4 leaves after its failed coarse call.
    assert [(call_id, qid) for _, call_id, _, qid in recorder.log] == [
        ("spec_coarse", "0"),
        ("spec_coarse", "4"),
        ("spec_fine", "0"),
        ("spec_coarse", "1"),
        ("spec_coarse", "5"),
        ("spec_fine", "1"),
        ("spec_fine", "5"),
    ]
    result = ctx.get_step_result("spectroscopy")
    assert [c.status for c in result.get_qubit("4").calls] == ["failed", "skipped"]  # type: ignore[union-attr]
    assert parent.parameters["spec_fine"]["run"] == {"shots": {"value": 2048}}


@pytest.mark.parametrize("continue_after_missing", [False, True])
def test_batch_missing_target_is_failed_and_obeys_call_policy(
    recorder: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    continue_after_missing: bool,
) -> None:
    _schedule(monkeypatch)
    parent = RecordingSession(recorder.log, recorder.fail)
    execute_batch = parent.execute_task_batch

    def incomplete_batch(*args: Any, **kwargs: Any) -> dict[str, dict[str, Any]]:
        results = execute_batch(*args, **kwargs)
        if kwargs["invocation"].call_id == "spec_coarse":
            results.pop("4", None)
        return results

    monkeypatch.setattr(parent, "execute_task_batch", incomplete_batch)
    monkeypatch.setattr("qdash.workflow.service.one_qubit_stage_runner.get_session", lambda: parent)
    step = CustomOneQubit(
        step_name="spectroscopy",
        mode="simultaneous_spectroscopy",
        tasks=[
            TaskCall(
                name="CheckQubitSpectroscopy",
                call_id="spec_coarse",
                on_failure="continue" if continue_after_missing else "stop",
            ),
            TaskCall(name="CheckQubitSpectroscopy", call_id="spec_fine"),
        ],
    )
    ctx = step.execute(_service(), QubitTargets(["0", "4"]), StepContext())
    result = ctx.get_step_result("spectroscopy")
    assert isinstance(result, OneQubitResult)
    missing = result.get_qubit("4")
    assert missing is not None
    assert missing.status == "failed"
    assert missing.calls[0].status == "failed"
    assert missing.calls[0].task_id is None
    assert "returned no result for target 4" in (missing.calls[0].error or "")
    assert missing.calls[1].status == ("success" if continue_after_missing else "skipped")
    assert _per_target(recorder.log, "4") == (
        ["spec_coarse", "spec_fine"] if continue_after_missing else ["spec_coarse"]
    )
    unaffected = result.get_qubit("0")
    assert unaffected is not None
    assert [call.status for call in unaffected.calls] == ["success", "success"]


def test_batch_mode_rejects_input_overrides_before_any_batch(
    recorder: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _schedule(monkeypatch)
    step = CustomOneQubit(
        step_name="spectroscopy",
        mode="simultaneous_spectroscopy",
        tasks=[TaskCall(name="CheckQubitSpectroscopy", input={"qubit_frequency": 5.0})],
    )

    with pytest.raises(ValueError, match="calibration input overrides"):
        step.execute(_service(), QubitTargets(["0", "1"]), StepContext())
    assert recorder.log == []


def test_two_qubit_calls_carry_identity_per_coupling(recorder: SimpleNamespace) -> None:
    recorder.fail.add(("zx90_check_coarse", "0-1"))
    calls = [
        TaskCall(name="CheckZX90", call_id="zx90_check_coarse"),
        TaskCall(name="CheckZX90", call_id="zx90_check_fine", on_failure="continue"),
    ]
    step = CustomTwoQubit(step_name="zx90", tasks=calls)
    ctx = StepContext(candidate_qids=["0", "1", "4", "5"])
    ctx.metadata["cr_schedule"] = [[("0", "1"), ("4", "5")]]

    ctx = step.execute(_service(), QubitTargets([]), ctx)

    result = ctx.get_step_result("zx90")
    assert result is not None
    # on_failure="continue" on the fine call does not rescue the coarse failure's
    # stop: the coarse call inherits the step's fail-fast policy.
    assert _per_target(recorder.log, "0-1") == ["zx90_check_coarse"]
    assert _per_target(recorder.log, "4-5") == ["zx90_check_coarse", "zx90_check_fine"]
    assert [c.status for c in result.get_coupling("0-1").calls] == ["failed", "skipped"]  # type: ignore[union-attr]
    assert result.successful_couplings() == ["4-5"]  # type: ignore[union-attr]


def test_pipeline_filter_reads_the_custom_step_call(
    recorder: SimpleNamespace, monkeypatch: Any
) -> None:
    _schedule(monkeypatch)
    recorder.fail.add(("ramsey_fine", "1"))
    service = _service()
    ctx = StepContext(candidate_qids=["0", "1"])
    step = CustomOneQubit(
        step_name="ramsey", mode="scheduled", tasks=list(REPEATED), continue_on_failure=True
    )
    ctx = step.execute(service, QubitTargets(["0", "1"]), ctx)
    ctx = FilterByStatus(step="ramsey", call_id="ramsey_fine").execute(
        service, QubitTargets(["0", "1"]), ctx
    )
    assert ctx.candidate_qids == ["0"]
    ctx.candidate_qids = ["0", "1"]
    ctx = FilterByStatus(step="ramsey", call_id="ramsey_coarse").execute(
        service, QubitTargets(["0", "1"]), ctx
    )
    assert ctx.candidate_qids == ["0", "1"]


def test_coherence_check_second_ramsey_settings_reach_only_its_call(
    recorder: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both coherence-check steps run per target, and only the long Ramsey carries overrides."""
    import importlib

    template = importlib.import_module("qdash.workflow.templates.coherence_check")
    captured: dict[str, Any] = {}

    class CapturingCalibService:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["kwargs"] = kwargs

        def run(self, targets: Any, *, steps: list[Any]) -> None:
            captured["targets"] = targets
            captured["steps"] = steps

    monkeypatch.setattr(template, "CalibService", CapturingCalibService)
    template.coherence_check(username="alice", chip_id="64Q", qids=["0", "1", "4", "5"])
    _schedule(monkeypatch)

    ctx = StepContext()
    for step in captured["steps"]:
        ctx = step.execute(_service(), captured["targets"], ctx)

    for qid in ("0", "1", "4", "5"):
        assert [
            (step_id, call_id) for step_id, call_id, _, target in recorder.log if target == qid
        ] == [
            ("coherence_check", "Configure"),
            ("coherence_check", "CheckChevron"),
            ("coherence_check", "CheckRabi"),
            ("coherence_check", "CheckT1"),
            ("coherence_check", "CheckT2Echo"),
            ("coherence_check", "CheckRamsey"),
            ("long_ramsey_check", "Configure"),
            ("long_ramsey_check", "CheckRabi"),
            ("long_ramsey_check", "ramsey_long"),
        ]
    # The step boundary keeps every first pass complete before any second pass starts.
    step_ids = [step_id for step_id, *_ in recorder.log]
    assert step_ids == sorted(step_ids, key=["coherence_check", "long_ramsey_check"].index)
    for step_id in ("coherence_check", "long_ramsey_check"):
        assert all(
            data.status == "success"
            for data in ctx.get_step_result(step_id).qubits.values()  # type: ignore[union-attr]
        )

    # Templates carry every setting on its call, so no per-task defaults exist
    # that could leak one Ramsey's settings into the other call.
    assert "task_parameters" not in captured["kwargs"]
    first_ramsey = captured["steps"][0].tasks[-1]
    long_ramsey = captured["steps"][1].tasks[-1]
    first_run = {
        "time_range": {"value": (0, 10_001, 100), "value_type": "np.arange"},
        "detuning": {"value": 0.001},
    }
    long_run = {
        "time_range": {"value": (0, 50_001, 500), "value_type": "np.arange"},
        "detuning": {"value": 0.0002},
    }
    assert first_ramsey.settings()["run"] == first_run
    assert long_ramsey.settings()["run"] == long_run

    # Workers receive each call's own settings keyed by its call id, and the
    # long Ramsey overrides never reach the first Ramsey call (or vice versa).
    first_sessions = [s for s in recorder.sessions if "CheckRamsey" in s.parameters]
    long_sessions = [s for s in recorder.sessions if "ramsey_long" in s.parameters]
    assert first_sessions
    assert long_sessions
    for session in first_sessions:
        assert session.parameters["CheckRamsey"] == first_ramsey.settings()
        assert session.parameters["CheckRamsey"]["run"] == first_run
    for session in long_sessions:
        assert session.parameters["ramsey_long"] == long_ramsey.settings()
        assert session.parameters["ramsey_long"]["run"] == long_run
