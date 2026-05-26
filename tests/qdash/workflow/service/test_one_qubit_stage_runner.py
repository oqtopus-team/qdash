from types import SimpleNamespace
from typing import Any, cast

from qdash.workflow.service.calib_service import CalibService
from qdash.workflow.service.one_qubit_stage_runner import OneQubitStageRunner


def _service() -> CalibService:
    return cast(
        "CalibService",
        SimpleNamespace(
            username="alice",
            chip_id="144Q-test",
            backend_name="qubex",
            project_id="project-1",
            default_run_parameters={"interval": {"value": 1024}},
            tags=["tag-1"],
            note={"kind": "test"},
        ),
    )


def test_collect_qids_preserves_order_and_filters_duplicates() -> None:
    runner = OneQubitStageRunner(_service())
    schedule = SimpleNamespace(
        stages=[
            SimpleNamespace(parallel_groups=[["0", "4"], ["1"]]),
            SimpleNamespace(parallel_groups=[["4", "8"]]),
        ]
    )

    assert runner.collect_scheduled_qids(schedule, allowed_qids=["4", "8"]) == ["4", "8"]


def test_execute_scheduled_mux_schedule_uses_parent_session_config(
    monkeypatch: Any,
) -> None:
    runner = OneQubitStageRunner(_service())
    calls: list[dict[str, Any]] = []

    def run_mux_calibrations_parallel(
        *, mux_groups: list[list[str]], tasks: list[str], session_config: dict[str, Any]
    ) -> dict[str, Any]:
        calls.append({"mux_groups": mux_groups, "tasks": tasks, "session_config": session_config})
        return {
            qid: {tasks[0]: {"ok": True}, "status": "success"}
            for group in mux_groups
            for qid in group
        }

    monkeypatch.setattr(
        "qdash.workflow.service.one_qubit_stage_runner.run_mux_calibrations_parallel",
        run_mux_calibrations_parallel,
    )
    schedule = SimpleNamespace(
        stages=[
            SimpleNamespace(box_type="A", parallel_groups=[["0", "4"], ["1"]]),
            SimpleNamespace(box_type="B", parallel_groups=[["8"]]),
        ]
    )
    session_config = runner.build_session_config(execution_id="exec-1", flow_name="flow-1")

    result = runner.execute_scheduled_mux_schedule(
        schedule,
        tasks=["CheckResonatorSpectroscopy"],
        session_config=session_config,
        allowed_qids=["0", "8"],
    )

    assert calls[0]["mux_groups"] == [["0"]]
    assert calls[0]["session_config"]["execution_id"] == "exec-1"
    assert calls[1]["mux_groups"] == [["8"]]
    assert result == {
        "Box_A": {"0": {"CheckResonatorSpectroscopy": {"ok": True}, "status": "success"}},
        "Box_B": {"8": {"CheckResonatorSpectroscopy": {"ok": True}, "status": "success"}},
    }


def test_execute_simultaneous_spectroscopy_schedule_batches_current_session(
    monkeypatch: Any,
) -> None:
    runner = OneQubitStageRunner(_service())
    calls: list[tuple[str, list[str]]] = []

    class FakeSession:
        def execute_task_batch(self, task_name: str, qids: list[str]) -> dict[str, dict[str, Any]]:
            calls.append((task_name, qids))
            return {qid: {"task_id": f"task-{qid}"} for qid in qids}

    def get_session() -> FakeSession:
        return FakeSession()

    monkeypatch.setattr(
        "qdash.workflow.service.one_qubit_stage_runner.get_session",
        get_session,
    )
    schedule = SimpleNamespace(
        steps=[
            SimpleNamespace(step_index=0, parallel_qids=["0", "4"]),
            SimpleNamespace(step_index=1, parallel_qids=["1", "5"]),
        ]
    )

    result = runner.execute_simultaneous_spectroscopy_schedule(
        schedule,
        tasks=["CheckSimultaneousQubitSpectroscopy"],
        allowed_qids=["0", "5"],
    )

    assert calls == [
        ("CheckSimultaneousQubitSpectroscopy", ["0"]),
        ("CheckSimultaneousQubitSpectroscopy", ["5"]),
    ]
    assert result == {
        "step_0": {"0": {"CheckSimultaneousQubitSpectroscopy": {"task_id": "task-0"}}},
        "step_1": {"5": {"CheckSimultaneousQubitSpectroscopy": {"task_id": "task-5"}}},
    }


def test_execute_simultaneous_spectroscopy_schedule_uses_isolated_batch(
    monkeypatch: Any,
) -> None:
    runner = OneQubitStageRunner(_service())
    calls: list[dict[str, Any]] = []

    def run_qubit_batch_calibration_isolated(
        *, qids: list[str], tasks: list[str], session_config: dict[str, Any]
    ) -> dict[str, Any]:
        calls.append({"qids": qids, "tasks": tasks, "session_config": session_config})
        return {qid: {tasks[0]: {"task_id": f"task-{qid}"}} for qid in qids}

    monkeypatch.setattr(
        "qdash.workflow.service.one_qubit_stage_runner.run_qubit_batch_calibration_isolated",
        run_qubit_batch_calibration_isolated,
    )
    schedule = SimpleNamespace(
        steps=[
            SimpleNamespace(step_index=0, parallel_qids=["0", "4"]),
            SimpleNamespace(step_index=1, parallel_qids=["1", "5"]),
        ]
    )
    session_config = runner.build_session_config(execution_id="exec-1", flow_name="flow-1")

    result = runner.execute_simultaneous_spectroscopy_schedule(
        schedule,
        tasks=["CheckSimultaneousQubitSpectroscopy"],
        allowed_qids=["0", "5"],
        session_config=session_config,
    )

    assert calls == [
        {
            "qids": ["0"],
            "tasks": ["CheckSimultaneousQubitSpectroscopy"],
            "session_config": session_config,
        },
        {
            "qids": ["5"],
            "tasks": ["CheckSimultaneousQubitSpectroscopy"],
            "session_config": session_config,
        },
    ]
    assert result == {
        "step_0": {"0": {"CheckSimultaneousQubitSpectroscopy": {"task_id": "task-0"}}},
        "step_1": {"5": {"CheckSimultaneousQubitSpectroscopy": {"task_id": "task-5"}}},
    }
