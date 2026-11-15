"""A UI-saved 2Q Automatic Pairs flow runs its directed pairs end to end on the fake backend.

The flow is saved and executed through the API exactly as the workflow editor does: the template
source comes from the template catalog, and the saved default parameters hold only the username
and chip ID. The test records the parameters and run context the API hands to Prefect, then runs
the saved entrypoint file with exactly those values. CalibService, the target override, the CR
scheduler on the wiring of a fake chip created through the API and TwoQubitCalibration all run
for real, with the in-memory MongoDB of ``tests/conftest.py``.

What is stubbed:

- Prefect: the suite replaces it, so the API's dispatch is recorded instead of creating a flow
  run, ``prefect.context`` exposes the recorded run context, and flow functions run in-process.
- Deployment registration: no Prefect deployment service runs; the stub returns an ID.
- Per-pair task execution: the fake backend has no two-qubit tasks, so the per-pair runner that
  would start a worker process records each pair instead of running CheckCrossResonance.
"""

from __future__ import annotations

import importlib.util
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from qdash.api.services.flow_service.execution import DispatchResult
from tests.qdash.workflow.test_fake_chip_preset import (  # noqa: F401 - pytest fixtures
    CHIP_ID,
    HEADERS,
    PROJECT_ID,
    REPO_ROOT,
    USERNAME,
    _create_fake_chip,
    fake_deployment,
    project,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from fastapi.testclient import TestClient

FLOW_NAME = "pairs_2q"
TEMPLATES_DIR = REPO_ROOT / "src" / "qdash" / "workflow" / "templates"
TEMPLATE_ID = "two_qubit_pairs"


class _RecordingDeployment:
    async def register(self, **kwargs: Any) -> str:
        return "deployment-1"

    async def delete(self, *_: Any, **__: Any) -> None:
        return None


class _RecordingCoordinator:
    """Record what the API would send to Prefect instead of creating a flow run."""

    def __init__(self) -> None:
        self.runs: list[dict[str, Any]] = []

    async def dispatch_run(self, **kwargs: Any) -> DispatchResult:
        self.runs.append(kwargs)
        return DispatchResult(
            flow_run_id="flow-run-1",
            flow_run_url="http://localhost:4200/runs/flow-run/flow-run-1",
            execution_id="exec-1",
            qdash_ui_url="http://localhost:5714/execution/exec-1",
        )

    async def delete_deployment(self, *_: Any) -> None:
        return None


@pytest.fixture
def coordinator(tmp_path: Path) -> Iterator[_RecordingCoordinator]:
    from qdash.api.dependencies import get_chip_repository, get_flow_repository, get_flow_service
    from qdash.api.main import app
    from qdash.api.services.flow_service.service import FlowService
    from qdash.api.services.flow_service.source_store import FlowSourceStore
    from qdash.api.services.flow_service.templates import TemplateCatalog

    recorder = _RecordingCoordinator()
    service = FlowService(
        flow_repository=get_flow_repository(),
        coordinator=recorder,  # type: ignore[arg-type]
        source_store=FlowSourceStore(tmp_path / "user_flows"),
        deployment_client=_RecordingDeployment(),  # type: ignore[arg-type]
        chip_repository=get_chip_repository(),
        templates=TemplateCatalog(TEMPLATES_DIR),
    )
    app.dependency_overrides[get_flow_service] = lambda: service
    yield recorder
    app.dependency_overrides.pop(get_flow_service, None)


@pytest.fixture
def executed_pairs(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record each coupling group the pipeline sends to the per-pair worker processes."""
    from qdash.workflow.service._internal import scheduling_tasks

    groups: list[list[str]] = []

    def run_group(coupling_qids: list[str], plan: Any, worker: Any) -> dict[str, Any]:
        assert worker.settings.backend_name == "fake"
        groups.append(list(coupling_qids))
        return {qid: {} for qid in coupling_qids}

    monkeypatch.setattr(scheduling_tasks, "run_coupling_calibrations_parallel", run_group)
    return groups


def _save_template_flow(client: TestClient) -> dict[str, Any]:
    """Save the template as the workflow editor does and return the flow details."""
    template = client.get(f"/flows/templates/{TEMPLATE_ID}", headers=HEADERS)
    assert template.status_code == 200, template.text
    template_body = template.json()
    response = client.post(
        "/flows",
        headers=HEADERS,
        json={
            "name": FLOW_NAME,
            "description": "",
            "code": template_body["code"],
            "flow_function_name": template_body["function_name"],
            "chip_id": CHIP_ID,
            "tags": [],
            "default_parameters": {"username": USERNAME, "chip_id": CHIP_ID},
        },
    )
    assert response.status_code == 200, response.text
    details = client.get(f"/flows/{FLOW_NAME}", headers=HEADERS)
    assert details.status_code == 200, details.text
    body: dict[str, Any] = details.json()
    return body


def _run_dispatched_flow(
    file_path: str,
    function_name: str,
    run: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    """Run the saved entrypoint with the parameters and context the API dispatched."""
    context = SimpleNamespace(flow_run=SimpleNamespace(context=run.get("context") or {}))
    monkeypatch.setitem(
        sys.modules,
        "prefect.context",
        SimpleNamespace(FlowRunContext=SimpleNamespace(get=lambda: context)),
    )
    spec = importlib.util.spec_from_file_location(f"user_flow_{FLOW_NAME}", file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, function_name)(**run["parameters"])


def _execute(
    client: TestClient,
    coordinator: _RecordingCoordinator,
    monkeypatch: pytest.MonkeyPatch,
    body: dict[str, Any],
) -> tuple[dict[str, Any], Any]:
    from qdash.dbmodel.flow import FlowDocument

    response = client.post(f"/flows/{FLOW_NAME}/execute", headers=HEADERS, json=body)
    assert response.status_code == 200, response.text
    run = coordinator.runs[-1]
    flow = FlowDocument.find_one({"project_id": PROJECT_ID, "name": FLOW_NAME}).run()
    assert flow is not None
    result = _run_dispatched_flow(flow.file_path, flow.flow_function_name, run, monkeypatch)
    return run, result


@pytest.fixture
def saved_flow(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    test_client: TestClient,
    coordinator: _RecordingCoordinator,
) -> dict[str, Any]:
    _create_fake_chip(test_client)
    return _save_template_flow(test_client)


def test_the_saved_template_offers_only_pair_overrides(saved_flow: dict[str, Any]) -> None:
    assert saved_flow["default_parameters"] == {"username": USERNAME, "chip_id": CHIP_ID}
    assert saved_flow["target_modes"] == ["coupling_pairs"]


def _assert_hardware_safe(groups: list[list[str]]) -> None:
    """No group may run pairs that share a qubit, a MUX, or a conflicting MUX module."""
    import yaml

    from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths
    from qdash.workflow.engine.scheduler.cr_utils import (
        build_mux_conflict_map,
        build_qubit_to_mux_map,
    )

    wiring = yaml.safe_load(get_qubex_paths().wiring_yaml(CHIP_ID).read_text())
    muxes = wiring[CHIP_ID] if CHIP_ID in wiring else [m for g in wiring.values() for m in g]
    qid_to_mux = build_qubit_to_mux_map(muxes)
    conflicts = build_mux_conflict_map(muxes)
    for group in groups:
        for index, first in enumerate(group):
            for second in group[index + 1 :]:
                qubits_a, qubits_b = set(first.split("-")), set(second.split("-"))
                assert not qubits_a & qubits_b, (first, second)
                muxes_a = {qid_to_mux[q] for q in qubits_a}
                muxes_b = {qid_to_mux[q] for q in qubits_b}
                blocked = muxes_a | {c for m in muxes_a for c in conflicts.get(m, set())}
                assert not blocked & muxes_b, (first, second)


def _executed(groups: list[list[str]]) -> list[str]:
    return sorted(pair for group in groups for pair in group)


def test_selected_pairs_run_in_their_direction_on_the_fake_backend(
    saved_flow: dict[str, Any],
    test_client: TestClient,
    coordinator: _RecordingCoordinator,
    executed_pairs: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pairs = [["0", "1"], ["1", "0"], ["4", "5"]]
    run, result = _execute(
        test_client, coordinator, monkeypatch, {"target_override": {"coupling_pairs": pairs}}
    )

    # The API forwards the selection to the template parameter of the same name
    # and to the run context.
    assert run["parameters"]["coupling_pairs"] == pairs
    assert run["context"]["qdash_target_override"]["coupling_pairs"] == pairs

    # Exactly the selected directed pairs run, 1-0 as well as 0-1, and no other pair.
    assert _executed(executed_pairs) == ["0-1", "1-0", "4-5"]
    assert sorted(result["two_qubit"].couplings) == ["0-1", "1-0", "4-5"]
    # The run grouped the pairs by the fake chip's wiring instead of one pair per
    # group: 0-1 and 4-5 (MUX 0 and 1) run together, 1-0 shares qubits with 0-1.
    assert len(executed_pairs) == 2
    assert any({"0-1", "4-5"} <= set(group) for group in executed_pairs)
    _assert_hardware_safe(executed_pairs)


def test_selected_pairs_replace_the_saved_pairs(
    saved_flow: dict[str, Any],
    test_client: TestClient,
    coordinator: _RecordingCoordinator,
    executed_pairs: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, _ = _execute(
        test_client,
        coordinator,
        monkeypatch,
        {
            "parameters": {"coupling_pairs": [["4", "5"], ["0", "1"]]},
            "target_override": {"coupling_pairs": [["5", "4"]]},
        },
    )

    assert run["parameters"]["coupling_pairs"] == [["5", "4"]]
    assert executed_pairs == [["5-4"]]


def test_without_an_override_the_saved_pairs_are_grouped_automatically(
    saved_flow: dict[str, Any],
    test_client: TestClient,
    coordinator: _RecordingCoordinator,
    executed_pairs: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pairs = [["0", "1"], ["4", "5"], ["5", "4"]]
    run, result = _execute(
        test_client, coordinator, monkeypatch, {"parameters": {"coupling_pairs": pairs}}
    )

    assert "context" not in run
    # Only the listed pairs run; 0-1 and 4-5 share a group, 5-4 shares qubits with 4-5.
    assert _executed(executed_pairs) == ["0-1", "4-5", "5-4"]
    assert len(executed_pairs) == 2
    assert any({"0-1", "4-5"} <= set(group) for group in executed_pairs)
    _assert_hardware_safe(executed_pairs)
    assert sorted(result["two_qubit"].couplings) == ["0-1", "4-5", "5-4"]


def test_the_preview_describes_automatic_groups_of_the_listed_pairs(
    saved_flow: dict[str, Any],
    test_client: TestClient,
) -> None:
    response = test_client.get(
        f"/flows/{FLOW_NAME}/execution-plan", headers=HEADERS, params={"chip_id": CHIP_ID}
    )
    assert response.status_code == 200, response.text
    plan = response.json()

    assert plan["status"] == "resolved"
    assert plan["target_override_allowed"] is True
    [run] = plan["runs"]
    [step] = run["steps"]
    assert step["type"] == "TwoQubitCalibration"
    assert step["schedule"] == "automatic"
    assert step["rounds"] == []
    assert "exactly the listed directed pairs" in step["summary"]
    assert "at most 10 pairs" in step["summary"]


def test_without_pairs_the_run_fails_before_calibrating(
    saved_flow: dict[str, Any],
    test_client: TestClient,
    coordinator: _RecordingCoordinator,
    executed_pairs: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="Specify coupling_pairs"):
        _execute(test_client, coordinator, monkeypatch, {})

    assert executed_pairs == []


def test_unknown_pairs_are_rejected_before_dispatch(
    saved_flow: dict[str, Any],
    test_client: TestClient,
    coordinator: _RecordingCoordinator,
) -> None:
    response = test_client.post(
        f"/flows/{FLOW_NAME}/execute",
        headers=HEADERS,
        json={"target_override": {"coupling_pairs": [["0", "63"]]}},
    )

    assert response.status_code == 400
    assert "0-63" in response.json()["detail"]
    assert coordinator.runs == []


def test_unknown_saved_pairs_stop_the_run_before_any_pair(
    saved_flow: dict[str, Any],
    test_client: TestClient,
    coordinator: _RecordingCoordinator,
    executed_pairs: list[list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="not found on chip"):
        _execute(
            test_client,
            coordinator,
            monkeypatch,
            {"parameters": {"coupling_pairs": [["0", "1"], ["0", "63"]]}},
        )

    assert executed_pairs == []
