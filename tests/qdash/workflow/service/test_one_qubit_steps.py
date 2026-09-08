from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from qdash.workflow.service.steps.one_qubit import CustomOneQubit

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService


def test_custom_one_qubit_direct_targets_reuse_step_execution(monkeypatch) -> None:
    from unittest.mock import MagicMock

    init = MagicMock(side_effect=AssertionError("must reuse the step Execution"))
    finish = MagicMock(side_effect=AssertionError("pipeline owns completion"))
    run = MagicMock(return_value={"1": {"status": "success"}})
    monkeypatch.setattr("qdash.workflow.service.calib_service.init_calibration", init)
    monkeypatch.setattr("qdash.workflow.service.calib_service.finish_calibration", finish)
    monkeypatch.setattr(
        "qdash.workflow.service._internal.scheduling_tasks.run_qubit_calibrations_parallel",
        run,
    )
    service = SimpleNamespace(
        username="alice",
        chip_id="64Qv3",
        backend_name="qubex",
        project_id="project-1",
        execution_id="exec-step",
        default_run_parameters={},
        tags=[],
        flow_name="simple_tasks",
        note={},
        record_stage_result=MagicMock(),
    )
    step = CustomOneQubit(step_name="simple_tasks", tasks=["CheckRabi"])
    result = step._execute_direct(cast("CalibService", service), ["1"])

    assert result == {"direct": {"1": {"status": "success"}}}
    config = run.call_args.kwargs["session_config"]
    assert config["execution_id"] == "exec-step"
    assert config["tags"] == []
    assert config["flow_name"] == "simple_tasks"
    service.record_stage_result.assert_called_once_with("simple_tasks", result)
    init.assert_not_called()
    finish.assert_not_called()


def test_custom_one_qubit_qubit_targets_use_scheduled_strategy(monkeypatch) -> None:
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import QubitTargets

    calls = []

    class FakeStrategy:
        def execute(self, service, config):
            calls.append(config)
            return {"scheduled": {"1": {"status": "success"}, "4": {"status": "success"}}}

    monkeypatch.setattr(
        "qdash.workflow.service.strategy.get_one_qubit_strategy",
        lambda mode: FakeStrategy(),
    )

    service = SimpleNamespace(
        username="alice",
        chip_id="64Qv3",
        backend_name="qubex",
        project_id="project-1",
        default_run_parameters={},
        tags=[],
        flow_name="simple_calibration",
        note={},
    )
    step = CustomOneQubit(step_name="simple_tasks", tasks=["CheckRabi"], mode="scheduled")

    step.execute(cast("CalibService", service), QubitTargets(["1", "4"]), StepContext())

    assert len(calls) == 1
    assert calls[0].mux_ids == [0, 1]
    assert calls[0].qids == ["1", "4"]
    assert calls[0].tasks == ["CheckRabi"]
    assert calls[0].flow_name == "simple_calibration_simple_tasks"


def test_one_qubit_check_qubit_targets_use_scheduled_strategy(monkeypatch) -> None:
    from qdash.workflow.service.steps.one_qubit import OneQubitCheck
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import QubitTargets

    calls = []

    class FakeStrategy:
        def execute(self, service, config):
            calls.append(config)
            return {"scheduled": {"2": {"status": "success"}, "5": {"status": "success"}}}

    monkeypatch.setattr(
        "qdash.workflow.service.strategy.get_one_qubit_strategy",
        lambda mode: FakeStrategy(),
    )

    service = SimpleNamespace(
        username="alice",
        chip_id="64Qv3",
        backend_name="qubex",
        project_id="project-1",
        default_run_parameters={},
        tags=[],
        flow_name="one_qubit",
        note={},
    )
    step = OneQubitCheck(mode="synchronized", tasks=["CheckRabi"])

    step.execute(cast("CalibService", service), QubitTargets(["2", "5"]), StepContext())

    assert len(calls) == 1
    assert calls[0].mux_ids == [0, 1]
    assert calls[0].qids == ["2", "5"]
    assert calls[0].tasks == ["CheckRabi"]
    assert calls[0].flow_name == "one_qubit_one_qubit_check"


@pytest.mark.parametrize("successful_qids", [[], ["1"]])
def test_fine_tune_respects_coarse_status_filter(monkeypatch, successful_qids) -> None:
    from unittest.mock import MagicMock

    from qdash.workflow.service.results import OneQubitResult, QubitCalibData
    from qdash.workflow.service.steps import FilterByStatus, OneQubitFineTune, StepContext
    from qdash.workflow.service.targets import QubitTargets

    coarse_result = OneQubitResult()
    for qid in ["0", "1"]:
        coarse_result.add_qubit(
            qid, QubitCalibData(status="success" if qid in successful_qids else "failed")
        )
    ctx = StepContext(candidate_qids=["0", "1"], one_qubit_check=coarse_result)
    service = cast("CalibService", SimpleNamespace(chip_id="64Q"))
    targets = QubitTargets(["0", "1"])
    ctx = FilterByStatus().execute(service, targets, ctx)
    execute = MagicMock(return_value={})
    step = OneQubitFineTune()
    monkeypatch.setattr(step, "_execute_with_qids", execute)

    step.execute(service, targets, ctx)

    if successful_qids:
        assert execute.call_args.args[1] == successful_qids
    else:
        execute.assert_not_called()
        assert ctx.one_qubit_fine_tune is not None
        assert ctx.one_qubit_fine_tune.qubits == {}
