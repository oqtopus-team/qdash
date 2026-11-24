"""Inspecting runs: per-execution results, task results and figure/artifact handles."""

from __future__ import annotations

import builtins
import sys
import types
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from test_sdk_session import CHIP, Server, execute_body

from qdash.sdk import (
    Artifact,
    Execution,
    ExecutionResult,
    Figure,
    QDashNotFoundError,
    QDashTransportError,
    TaskResult,
)
from qdash.sdk.pipeline import CustomOneQubit, Pipeline, Qubits, TaskCall

if TYPE_CHECKING:
    from pathlib import Path

PNG = b"\x89PNG\r\n\x1a\n\x00binary\xff\x00"
FIGURE = "/app/calib_data/alice/2026/exec 1/fig/CheckT1 q0&x.png"


def task_entry(
    task_id: str, name: str = "CheckT1", qid: str = "0", status: str = "completed", **extra: Any
) -> dict[str, Any]:
    return {"task_id": task_id, "name": name, "qid": qid, "status": status, **extra}


def full_task() -> dict[str, Any]:
    return task_entry(
        "t-1",
        message="ok",
        input_parameters={"qubit_frequency": {"value": 5.1, "unit": "GHz", "value_type": "float"}},
        output_parameters={
            "t1": {"value": 31.5, "unit": "us", "error": 1.2, "value_type": "float"},
            "skipped": None,
        },
        output_parameter_names=["t1"],
        run_parameters={"shots": 1024, "time_range": {"value": [0, 1, 3], "value_type": "range"}},
        figure_path=[FIGURE, "/app/fig/second.png"],
        json_figure_path=["/app/fig/CheckT1.json"],
        raw_data_path=["/app/raw/CheckT1.nc"],
        invocation={"step_id": "coherence", "call_id": "t1-first"},
    )


def execution_body(
    status: str, tasks: list[dict[str, Any]], pipeline: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": "coherence", "status": status, "task": tasks, "note": {}}
    if pipeline is not None:
        payload["pipeline"] = pipeline
    return payload


def step(
    index: int, execution_id: str | None, status: str, kind: str = "calibration"
) -> dict[str, Any]:
    return {
        "index": index,
        "name": f"step{index}",
        "kind": kind,
        "execution_id": execution_id,
        "status": status,
    }


def progress(status: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": "coherence",
        "flow_run_id": "run-1",
        "root_execution_id": "exec-1",
        "status": status,
        "steps": steps,
    }


def test_execution_handle_and_result_metadata_send_no_request() -> None:
    server = Server(
        {("GET", "/executions/exec-1"): [httpx.Response(200, json=execution_body("failed", []))]}
    )
    with server.session() as qdash:
        handle = qdash.execution("exec-1")
        assert isinstance(handle, Execution)
        assert repr(handle) == "Execution(execution_id='exec-1')"
        assert server.requests == []
        with pytest.raises(ValueError):
            qdash.execution("")

        result = handle.get()
        assert len(server.requests) == 1
        repr(result)
        assert result.status == "failed"
        assert result.done and not result.succeeded
        assert result.tasks == []
    assert len(server.requests) == 1


def test_task_result_exposes_parameters_figures_and_artifacts_without_requests() -> None:
    server = Server(
        {
            ("GET", "/executions/exec-1"): [
                httpx.Response(200, json=execution_body("completed", [full_task()]))
            ]
        }
    )
    with server.session() as qdash:
        result = qdash.execution("exec-1").get()
        task = result.tasks[0]

        assert (task.task_id, task.name, task.qid, task.status) == (
            "t-1",
            "CheckT1",
            "0",
            "completed",
        )
        assert task.message == "ok"
        assert task.succeeded
        assert task.execution_id == "exec-1"
        assert task.call_id == "t1-first"
        t1 = task.output_parameters["t1"]
        assert (t1.value, t1.unit, t1.error) == (31.5, "us", 1.2)
        assert task.output_parameters["skipped"] is None
        assert task.input_parameters["qubit_frequency"].unit == "GHz"
        assert task.run_parameters["time_range"] == {"value": [0, 1, 3], "value_type": "range"}
        assert task.output_parameter_names == ["t1"]
        assert [type(fig) for fig in task.figures] == [Figure, Figure]
        assert task.figures[0].path == FIGURE
        assert task.figures[0].filename == "CheckT1 q0&x.png"
        assert [a.kind for a in task.json_figures] == ["json_figure"]
        assert [a.kind for a in task.raw_data] == ["raw_data"]
        assert result.task("t-1") is result.tasks[0]
        with pytest.raises(KeyError):
            result.task("missing")
        repr(task), repr(task.figures[0]), repr(task.raw_data[0])
    assert len(server.requests) == 1


def test_missing_optional_task_fields_are_empty() -> None:
    server = Server(
        {("GET", "/executions/exec-1"): [httpx.Response(200, json=execution_body("running", [{}]))]}
    )
    with server.session() as qdash:
        task = qdash.execution("exec-1").get().tasks[0]
    assert task.task_id is None and task.name is None and task.status is None
    assert task.input_parameters == {} and task.output_parameters == {}
    assert task.run_parameters == {} and task.note == {}
    assert task.figures == [] and task.json_figures == [] and task.raw_data == []
    assert task.output_parameter_names == [] and task.call_id is None
    assert not task.succeeded
    with pytest.raises(ValueError, match="task_id"):
        task.get()


def test_repeated_task_results_stay_distinct_by_task_id_and_invocation() -> None:
    tasks = [
        task_entry("t-1", status="failed", message="fit failed", invocation={"call_id": "a"}),
        task_entry("t-2", invocation={"call_id": "b"}),
    ]
    server = Server(
        {("GET", "/executions/exec-1"): [httpx.Response(200, json=execution_body("failed", tasks))]}
    )
    with server.session() as qdash:
        result = qdash.execution("exec-1").get()
    assert [(t.task_id, t.call_id, t.status) for t in result.tasks] == [
        ("t-1", "a", "failed"),
        ("t-2", "b", "completed"),
    ]
    assert result.task("t-1").message == "fit failed"


def saved_result(**extra: Any) -> dict[str, Any]:
    return {
        "task_id": "t-1",
        "task_name": "CheckT1",
        "qid": "0",
        "chip_id": CHIP,
        "status": "failed",
        "execution_id": "exec-9",
        "figure_path": [FIGURE],
        "json_figure_path": [],
        "raw_data_path": [],
        "input_parameters": {},
        "output_parameters": {"t1": {"value": 12.0, "unit": "us", "error": 0.5}},
        "message": "fit failed",
        "stack_trace": "Traceback ...",
        "source_task_id": "t-0",
        **extra,
    }


def test_task_result_reads_the_full_saved_result() -> None:
    server = Server({("GET", "/tasks/t-1/result"): [httpx.Response(200, json=saved_result())]})
    with server.session() as qdash:
        task = qdash.task_result("t-1")
        with pytest.raises(ValueError):
            qdash.task_result("")
    assert isinstance(task, TaskResult)
    assert (task.name, task.execution_id, task.chip_id) == ("CheckT1", "exec-9", CHIP)
    assert (task.status, task.message, task.stack_trace) == (
        "failed",
        "fit failed",
        "Traceback ...",
    )
    assert task.source_task_id == "t-0"
    t1 = task.output_parameters["t1"]
    assert t1 is not None and t1.error == 0.5
    assert task.run_parameters == {} and task.invocation is None
    assert server.requests[0].headers["X-Project-Id"] == "project-a"


def test_snapshot_task_get_reads_the_saved_result_and_404_translates() -> None:
    server = Server(
        {
            ("GET", "/executions/exec-1"): [
                httpx.Response(200, json=execution_body("completed", [task_entry("t-1")]))
            ],
            ("GET", "/tasks/t-1/result"): [httpx.Response(200, json=saved_result())],
            ("GET", "/tasks/gone/result"): [httpx.Response(404, json={"detail": "not found"})],
        }
    )
    with server.session() as qdash:
        full = qdash.execution("exec-1").get().tasks[0].get()
        assert full.stack_trace == "Traceback ..."
        with pytest.raises(QDashNotFoundError):
            qdash.task_result("gone")


def figure_server(response: httpx.Response) -> Server:
    return Server(
        {
            ("GET", "/executions/exec-1"): [
                httpx.Response(200, json=execution_body("completed", [full_task()]))
            ],
            ("GET", "/executions/figure"): [response],
            ("GET", "/executions/artifact"): [response],
        }
    )


def png_response() -> httpx.Response:
    return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})


def test_figure_read_returns_bytes_with_auth_and_encoded_path() -> None:
    server = figure_server(png_response())
    with server.session() as qdash:
        figure = qdash.execution("exec-1").get().tasks[0].figures[0]
        assert figure.read() == PNG

    request = server.requests[-1]
    assert request.url.path == "/executions/figure"
    assert request.url.params["path"] == FIGURE
    assert "&x.png" not in request.url.query.decode()
    assert request.headers["Authorization"] == "Bearer api-token"
    assert request.headers["X-Project-Id"] == "project-a"
    assert request.headers["Accept"].startswith("image/png")


def test_artifacts_read_through_the_artifact_route() -> None:
    server = figure_server(
        httpx.Response(200, content=b"CDF\x01", headers={"content-type": "application/x-netcdf"})
    )
    with server.session() as qdash:
        task = qdash.execution("exec-1").get().tasks[0]
        assert task.raw_data[0].read() == b"CDF\x01"
        assert task.json_figures[0].read() == b"CDF\x01"
    assert [r.url.params["path"] for r in server.requests[1:]] == [
        "/app/raw/CheckT1.nc",
        "/app/fig/CheckT1.json",
    ]
    assert {r.url.path for r in server.requests[1:]} == {"/executions/artifact"}


def test_figure_errors_translate() -> None:
    server = figure_server(httpx.Response(404, text="missing"))
    with server.session() as qdash:
        figure = qdash.execution("exec-1").get().tasks[0].figures[0]
        with pytest.raises(QDashNotFoundError):
            figure.read()


def test_html_in_place_of_a_file_is_an_error() -> None:
    server = figure_server(
        httpx.Response(200, text="<html>sign in</html>", headers={"content-type": "text/html"})
    )
    with server.session() as qdash:
        figure = qdash.execution("exec-1").get().tasks[0].figures[0]
        with pytest.raises(QDashTransportError, match="HTML"):
            figure.read()


def test_save_writes_bytes_and_respects_overwrite(tmp_path: Path) -> None:
    server = figure_server(png_response())
    with server.session() as qdash:
        figure = qdash.execution("exec-1").get().tasks[0].figures[0]
        target = tmp_path / "t1.png"
        assert figure.save(target) == target
        assert target.read_bytes() == PNG

        requests = len(server.requests)
        with pytest.raises(FileExistsError):
            figure.save(target)
        with pytest.raises(IsADirectoryError):
            figure.save(tmp_path)
        assert len(server.requests) == requests  # rejected before any fetch

        target.write_bytes(b"old")
        assert figure.save(str(target), overwrite=True) == target
        assert target.read_bytes() == PNG


def test_failed_fetch_writes_nothing(tmp_path: Path) -> None:
    server = figure_server(httpx.Response(404, json={"detail": "gone"}))
    with server.session() as qdash:
        figure = qdash.execution("exec-1").get().tasks[0].figures[0]
        with pytest.raises(QDashNotFoundError):
            figure.save(tmp_path / "t1.png")
    assert not (tmp_path / "t1.png").exists()


def test_show_displays_the_png_with_ipython(monkeypatch: pytest.MonkeyPatch) -> None:
    shown: list[Any] = []

    class Image:
        def __init__(self, *, data: bytes, format: str) -> None:
            self.data, self.format = data, format

    display_module = types.ModuleType("IPython.display")
    display_module.Image = Image  # type: ignore[attr-defined]
    display_module.display = shown.append  # type: ignore[attr-defined]
    ipython = types.ModuleType("IPython")
    ipython.display = display_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "IPython", ipython)
    monkeypatch.setitem(sys.modules, "IPython.display", display_module)

    server = figure_server(png_response())
    with server.session() as qdash:
        for fig in qdash.execution("exec-1").get().tasks[0].figures:
            fig.show()
    assert [(image.data, image.format) for image in shown] == [(PNG, "png"), (PNG, "png")]


def test_show_without_ipython_explains_and_fetches_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def no_ipython(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("IPython"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_ipython)
    server = figure_server(png_response())
    with server.session() as qdash:
        figure = qdash.execution("exec-1").get().tasks[0].figures[0]
        with pytest.raises(ImportError, match="IPython"):
            figure.show()
    assert ("GET", "/executions/figure") not in server.paths()
    assert not hasattr(Figure, "_repr_png_")


def test_run_executions_reads_each_started_step_once_in_order() -> None:
    steps = [
        step(3, "exec-3", "running"),
        step(1, "exec-1", "completed"),
        step(2, None, "skipped", kind="transform"),
        step(4, "exec-3", "running"),
        step(5, None, "pending"),
    ]
    server = Server(
        {
            ("GET", "/executions/exec-1"): [
                httpx.Response(
                    200,
                    json=execution_body(
                        "completed", [task_entry("t-1")], progress("running", steps)
                    ),
                )
            ],
            ("GET", "/executions/exec-3"): [
                httpx.Response(
                    200, json=execution_body("running", [task_entry("t-3", status="running")])
                )
            ],
        }
    )
    with server.session() as qdash:
        run = qdash.run("exec-1")
        assert run.get().status == "running"
        server.requests.clear()

        executions = run.executions()

    assert server.paths() == [("GET", "/executions/exec-1"), ("GET", "/executions/exec-3")]
    assert all(isinstance(e, ExecutionResult) for e in executions)
    assert [(e.execution_id, e.status) for e in executions] == [
        ("exec-1", "completed"),
        ("exec-3", "running"),
    ]
    assert [e.step.index for e in executions if e.step] == [1, 3]
    assert executions[1].tasks[0].execution_id == "exec-3"


def test_run_executions_without_pipeline_returns_the_one_execution() -> None:
    server = Server(
        {
            ("GET", "/executions/exec-1"): [
                httpx.Response(200, json=execution_body("failed", [task_entry("t-1")]))
            ]
        }
    )
    with server.session() as qdash:
        executions = qdash.run("exec-1").executions()
    assert [(e.execution_id, e.status, e.step) for e in executions] == [("exec-1", "failed", None)]
    assert len(server.requests) == 1


def test_root_not_named_by_steps_is_kept_first() -> None:
    server = Server(
        {
            ("GET", "/executions/exec-1"): [
                httpx.Response(
                    200,
                    json=execution_body(
                        "completed", [], progress("completed", [step(1, "exec-2", "completed")])
                    ),
                )
            ],
            ("GET", "/executions/exec-2"): [
                httpx.Response(200, json=execution_body("completed", []))
            ],
        }
    )
    with server.session() as qdash:
        executions = qdash.run("exec-1").executions()
    assert [e.execution_id for e in executions] == ["exec-1", "exec-2"]


def pipeline() -> Pipeline:
    return Pipeline(
        name="coherence",
        targets=Qubits(["0"]),
        steps=[CustomOneQubit(step_name="coherence", tasks=[TaskCall(name="CheckT1")])],
    )


def test_calibration_and_pipeline_runs_inspect_their_executions() -> None:
    body = execution_body(
        "completed",
        [task_entry("t-1")],
        progress("completed", [step(1, "exec-1", "completed")]),
    )
    server = Server(
        {
            ("POST", "/calibration-pipelines/execute"): [httpx.Response(202, json=execute_body())],
            ("GET", "/executions/exec-1"): [httpx.Response(200, json=body)],
        }
    )
    with server.session() as qdash:
        run = qdash.chip(CHIP).calibrate(pipeline())
        assert [e.tasks[0].task_id for e in run.executions()] == ["t-1"]
        pipeline_run = qdash.pipelines.execute(pipeline(), chip_id=CHIP)
        assert [e.execution_id for e in pipeline_run.executions()] == ["exec-1"]
        # The existing return contracts are unchanged.
        assert pipeline_run.get().pipeline is not None
        assert run.get().status == "completed"


def test_workflow_run_inspects_its_executions() -> None:
    response = {
        "execution_id": "exec-1",
        "flow_run_id": "run-1",
        "flow_run_url": "http://prefect/run-1",
        "qdash_ui_url": "http://qdash/executions/exec-1",
        "message": "started",
    }
    server = Server(
        {
            ("POST", "/flows/coherence/execute"): [httpx.Response(200, json=response)],
            ("GET", "/executions/exec-1"): [
                httpx.Response(200, json=execution_body("completed", [full_task()]))
            ],
        }
    )
    with server.session() as qdash:
        run = qdash.workflows.run("coherence")
        (execution,) = run.executions()
    assert execution.tasks[0].output_parameters["t1"].value == 31.5


def test_artifact_handles_are_plain_objects() -> None:
    assert issubclass(Figure, Artifact)
