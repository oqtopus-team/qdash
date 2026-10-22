from types import SimpleNamespace
from typing import Any, cast

from qdash.workflow.service._internal.scheduling_tasks import _create_isolated_session
from qdash.workflow.service._internal.worker_session import build_isolated_session_config
from qdash.workflow.service.calib_service import CalibService


def _parent_service() -> CalibService:
    return cast(
        "CalibService",
        SimpleNamespace(
            username="alice",
            chip_id="chip-1",
            backend_name="fake",
            project_id="project-1",
            execution_id="exec-1",
            default_run_parameters={"interval": {"value": 1024}},
            task_run_parameters={"CheckAdaptiveChevron": {"shots": {"value": 256}}},
            source_execution_id="source-exec-1",
            source_task_id="source-task-1",
            snapshot_exempt_tasks={"ConfigureQubit"},
            parameter_overrides={
                "input": {"control_amplitude": 0.0625},
            },
            force_update_params=True,
            persist_output_parameters=False,
            tags=["test"],
            flow_name="one-qubit",
            note={"kind": "test"},
        ),
    )


def test_build_isolated_session_config_preserves_execution_settings() -> None:
    service = _parent_service()

    config = build_isolated_session_config(service)

    assert config["parameter_overrides"] == {"input": {"control_amplitude": 0.0625}}
    assert config["source_execution_id"] == "source-exec-1"
    assert config["source_task_id"] == "source-task-1"
    assert config["snapshot_exempt_tasks"] == ["ConfigureQubit"]
    assert config["force_update_params"] is True
    assert config["persist_output_parameters"] is False
    assert config["execution_id"] == "exec-1"


def test_build_isolated_session_config_copies_mutable_settings() -> None:
    service = _parent_service()

    config = build_isolated_session_config(service)
    parameter_overrides = service.parameter_overrides
    note = service.note
    assert parameter_overrides is not None
    assert note is not None
    parameter_overrides["input"]["control_amplitude"] = 0.1
    service.task_run_parameters["CheckAdaptiveChevron"]["shots"]["value"] = 512
    note["kind"] = "changed"
    service.snapshot_exempt_tasks.add("ConfigureMUX")

    assert config["parameter_overrides"] == {"input": {"control_amplitude": 0.0625}}
    assert config["task_run_parameters"]["CheckAdaptiveChevron"]["shots"]["value"] == 256
    assert config["note"] == {"kind": "test"}
    assert config["snapshot_exempt_tasks"] == ["ConfigureQubit"]


def test_create_isolated_session_passes_parent_execution_settings(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}
    sentinel = object()

    def fake_calib_service(**kwargs: Any) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        "qdash.workflow.service.calib_service.CalibService",
        fake_calib_service,
    )
    config = build_isolated_session_config(_parent_service())

    result = _create_isolated_session(config, ["0"])

    assert result is sentinel
    assert captured["parameter_overrides"] == {"input": {"control_amplitude": 0.0625}}
    assert captured["source_execution_id"] == "source-exec-1"
    assert captured["source_task_id"] == "source-task-1"
    assert captured["snapshot_exempt_tasks"] == {"ConfigureQubit"}
    assert captured["force_update_params"] is True
    assert captured["persist_output_parameters"] is False
    assert captured["use_lock"] is False
    assert captured["skip_execution"] is True
