"""A chip created from the fake setup preset runs the fake calibration chain end to end.

The chip is created through the API exactly as the Create Chip dialog does on a deployment whose
backend is fake. The tests then check that Qubex itself reads the generated configuration as the
64-qubit, 16-MUX device the simulator runs, that QDash resolves every MUX to its four qubits, and
execute FakeBringUp followed by the rest of the Fake Backend Calibration template on
representative MUXes, including the highest one. Every task must complete and its outputs must be
stored in the calibration database. Running all 64 qubits would only repeat the same simulator
code; the configuration of all 64 is checked separately.

Prefect is replaced by a stub in the test suite, so the tasks run in-process; MongoDB is the
in-memory database of ``tests/conftest.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from qdash.common.fake_device import (
    FAKE_DEVICE_MUXES,
    FAKE_DEVICE_QUBITS,
    FAKE_QUBIT_FREQUENCIES,
    FAKE_READOUT_FREQUENCIES,
    fake_device_value,
)
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.dbmodel.user import UserDocument
from qdash.workflow.templates.fake_backend import FAKE_CALIBRATION_TASKS

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
PARAMS_TEMPLATES = REPO_ROOT / "config" / "domain" / "qubex-params"
CONFIG_TEMPLATES = REPO_ROOT / "config" / "domain" / "qubex-config"
CHIP_ID = "fake-64q"
PROJECT_ID = "fake_project"
USERNAME = "alice"
HEADERS = {"Authorization": "Bearer fake_token", "X-Project-Id": PROJECT_ID}


@pytest.fixture
def project(init_db: Any) -> None:
    user = UserDocument(
        username=USERNAME,
        hashed_password="hashed",
        access_token="fake_token",
        default_project_id=PROJECT_ID,
        system_info=SystemInfoModel(),
    )
    user.insert()
    ProjectDocument(
        project_id=PROJECT_ID,
        name="Fake Project",
        owner_user_id=user.user_id,
        owner_username=USERNAME,
    ).insert()
    ProjectMembershipDocument(
        project_id=PROJECT_ID,
        user_id=user.user_id,
        username=USERNAME,
        role=ProjectRole.OWNER,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by=USERNAME,
    ).insert()


@pytest.fixture
def fake_deployment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A fake-backend deployment whose API and workflow share one temporary config tree."""
    from qdash.api.dependencies import get_chip_config_scaffolder
    from qdash.api.main import app
    from qdash.api.services.chip import ChipConfigScaffolder
    from qdash.workflow import paths as workflow_paths
    from qdash.workflow.engine import task_runner
    from qdash.workflow.engine.backend import qubex_paths

    config_root = tmp_path / "qubex-config"
    config_root.mkdir()
    monkeypatch.setenv("DEFAULT_BACKEND", "fake")
    monkeypatch.chdir(tmp_path)
    app.dependency_overrides[get_chip_config_scaffolder] = lambda: ChipConfigScaffolder(
        config_base=config_root,
        templates_dir=PARAMS_TEMPLATES,
        config_templates_dir=CONFIG_TEMPLATES,
    )
    monkeypatch.setattr(
        qubex_paths, "_default_qubex_paths", qubex_paths.QubexPaths(config_base=config_root)
    )
    monkeypatch.setattr(
        workflow_paths,
        "_default_resolver",
        workflow_paths.PathResolver(calib_data_base=tmp_path / "calib_data"),
    )
    # The suite's Prefect stub leaves tasks as plain functions without ``with_options``.
    run_task = task_runner.execute_dynamic_task_by_qid_service
    monkeypatch.setattr(run_task, "with_options", lambda **_: run_task, raising=False)
    yield config_root
    app.dependency_overrides.pop(get_chip_config_scaffolder, None)


def _create_fake_chip(client: TestClient) -> dict[str, Any]:
    sources = client.get("/chips/config-sources", headers=HEADERS)
    assert sources.status_code == 200
    [preset] = sources.json()["presets"]
    assert preset["preset_id"] == "fake"
    assert preset["workflow_template_id"] == "fake_calibration"

    response = client.post(
        "/chips",
        headers=HEADERS,
        json={
            "chip_id": CHIP_ID,
            "size": preset["n_qubits"],
            "topology_id": preset["topology_id"],
            "config": {"preset": "fake"},
        },
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_generated_configuration_describes_the_simulated_device(
    project: None, fake_deployment: Path, test_client: TestClient
) -> None:
    config_loader = pytest.importorskip("qubex.system.config_loader")

    body = _create_fake_chip(test_client)
    assert body["config"]["status"] == "created"
    assert body["config"]["preset"] == "fake"
    assert body["size"] == FAKE_DEVICE_QUBITS == 64
    assert body["topology_id"] == "square-lattice-mux-64"

    chip_dir = fake_deployment / CHIP_ID
    for name in ("chip.yaml", "system.yaml", "wiring.yaml", "box.yaml", "skew.yaml"):
        assert "VIRTUAL HARDWARE" in (chip_dir / "config" / name).read_text(encoding="utf-8")

    loader = config_loader.ConfigLoader(
        system_id=CHIP_ID,
        config_dir=chip_dir / "config",
        params_dir=chip_dir / "params",
    )
    system = loader.get_experiment_system()
    qubits = list(system.quantum_system.qubits)
    assert [qubit.label for qubit in qubits] == [f"Q{index:02d}" for index in range(64)]
    for index, qubit in enumerate(qubits):
        assert qubit.control_frequency_ge == pytest.approx(
            fake_device_value(FAKE_QUBIT_FREQUENCIES, index)
        )
    resonators = list(system.quantum_system.resonators)
    assert len(resonators) == FAKE_DEVICE_QUBITS
    for index, resonator in enumerate(resonators):
        assert resonator.readout_frequency == pytest.approx(
            fake_device_value(FAKE_READOUT_FREQUENCIES, index)
        )
    assert len(list(system.quantum_system.muxes)) == FAKE_DEVICE_MUXES
    boxes = list(system.control_system.boxes)
    assert len(boxes) == FAKE_DEVICE_MUXES
    assert all(box.address.startswith("192.0.2.") for box in boxes)


def test_every_mux_resolves_to_its_four_qubits(
    project: None, fake_deployment: Path, test_client: TestClient
) -> None:
    from qdash.workflow.service.targets import MuxTargets

    _create_fake_chip(test_client)

    for mux in range(FAKE_DEVICE_MUXES):
        expected = sorted(str(qid) for qid in range(4 * mux, 4 * mux + 4))
        assert MuxTargets(mux_ids=[mux]).to_qids(CHIP_ID) == expected
    all_qids = MuxTargets(mux_ids=list(range(FAKE_DEVICE_MUXES))).to_qids(CHIP_ID)
    assert sorted(all_qids, key=int) == [str(qid) for qid in range(FAKE_DEVICE_QUBITS)]


def test_a_high_numbered_subset_simulates_the_same_device(
    project: None, fake_deployment: Path, test_client: TestClient
) -> None:
    """A session on the last MUX sees the parameters the full device gives those qubits."""
    from qdash.workflow.engine.backend.fake_qubex import FakeExperiment

    _create_fake_chip(test_client)
    full = FakeExperiment(qubits=list(range(FAKE_DEVICE_QUBITS)))
    subset = FakeExperiment(qubits=[61, 63])
    for qubit in (61, 63):
        label = f"Q{qubit:02d}"
        frequency = fake_device_value(FAKE_QUBIT_FREQUENCIES, qubit)
        assert subset.get_target(label).frequency == pytest.approx(frequency)
        assert full.get_target(label).frequency == subset.get_target(label).frequency
        assert subset.get_target(f"R{label}").frequency == pytest.approx(
            fake_device_value(FAKE_READOUT_FREQUENCIES, qubit)
        )


@pytest.mark.parametrize("mux_ids", [[0], [9, 15]], ids=["mux0", "mux9-15"])
def test_fake_chip_runs_bring_up_and_the_fake_calibration_chain(
    project: None, fake_deployment: Path, test_client: TestClient, mux_ids: list[int]
) -> None:
    from qdash.workflow.engine.backend.fake_qubex import FakeExperiment
    from qdash.workflow.service import CalibService
    from qdash.workflow.service.targets import MuxTargets

    _create_fake_chip(test_client)
    assert ChipDocument.find_one({"project_id": PROJECT_ID, "chip_id": CHIP_ID}).run() is not None

    qids = MuxTargets(mux_ids=mux_ids).to_qids(CHIP_ID)
    assert sorted(qids, key=int) == [
        str(4 * mux + offset) for mux in mux_ids for offset in range(4)
    ]

    service = CalibService(
        USERNAME,
        CHIP_ID,
        qids=qids,
        backend_name="fake",
        project_id=PROJECT_ID,
        enable_github=False,
        flow_name="fake_calibration",
    )
    exp = service.backend.get_instance() if service.backend else None
    assert isinstance(exp, FakeExperiment)
    assert Path(exp.config_path) == fake_deployment / CHIP_ID / "config"

    for task_name in FAKE_CALIBRATION_TASKS:
        for qid in qids:
            service.execute_task(task_name, qid)
    service.finish_calibration()

    results = list(
        TaskResultHistoryDocument.find({"project_id": PROJECT_ID, "chip_id": CHIP_ID}).run()
    )
    by_task = {(result.name, result.qid): result for result in results}
    for task_name in FAKE_CALIBRATION_TASKS:
        for qid in qids:
            result = by_task[(task_name, qid)]
            assert result.status == "completed", (task_name, qid, result.message)
            assert result.output_parameters, (task_name, qid)

    execution = ExecutionHistoryDocument.find_one(
        {"project_id": PROJECT_ID, "chip_id": CHIP_ID}
    ).run()
    assert execution is not None
    assert execution.status == "completed"

    for qid in qids:
        qubit = QubitDocument.find_one(
            {"project_id": PROJECT_ID, "chip_id": CHIP_ID, "qid": qid}
        ).run()
        assert qubit is not None
        stored = qubit.data
        assert stored["qubit_frequency"]["value"] == pytest.approx(
            fake_device_value(FAKE_QUBIT_FREQUENCIES, int(qid)), abs=1e-3
        )
        for name in ("hpi_amplitude", "pi_amplitude", "t1", "t2_echo", "t2_star"):
            assert stored[name]["value"] is not None, (qid, name)


class _RecordingStageService:
    """The parts of CalibService the scheduled one-qubit strategy reads."""

    def __init__(self) -> None:
        self.username = USERNAME
        self.chip_id = CHIP_ID
        self.backend_name = "fake"
        self.project_id = PROJECT_ID
        self.execution_id = "exec-1"
        self.default_run_parameters: dict[str, Any] = {}
        self.task_parameters: dict[str, Any] = {}
        self.tags: list[str] = []
        self.flow_name = "fake_calibration"
        self.note = None
        self.stage_results: dict[str, Any] = {}

    def record_stage_result(self, stage_name: str, result: dict[str, Any]) -> None:
        self.stage_results[stage_name] = result


def _template_run(monkeypatch: pytest.MonkeyPatch, **params: Any) -> tuple[Any, Any]:
    """The targets and the single step the Fake Backend Calibration template builds."""
    from qdash.workflow.templates import fake_backend

    class _Recorder:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def run(self, targets: Any, *, steps: list[Any]) -> tuple[Any, Any]:
            [step] = steps
            return targets, step

        backend = None

    monkeypatch.setattr(fake_backend, "CalibService", _Recorder)
    result: tuple[Any, Any] = fake_backend.fake_calibration(
        username=USERNAME, chip_id=CHIP_ID, **params
    )
    return result


def _mux_qids(mux: int) -> list[str]:
    return [str(4 * mux + offset) for offset in range(4)]


@pytest.mark.parametrize(
    ("params", "expected_muxes", "excluded"),
    [
        ({}, list(range(FAKE_DEVICE_MUXES)), set()),
        ({"mux_ids": [9, 15]}, [9, 15], set()),
        ({"mux_ids": [9, 15], "exclude_qids": ["37"]}, [9, 15], {"37"}),
        # Qubit IDs passed by older callers do not change the MUX selection.
        ({"mux_ids": [15], "qids": ["0", "1"]}, [15], set()),
    ],
    ids=["all-16-mux", "mux9-15", "mux9-15-exclude-37", "qids-ignored"],
)
def test_the_template_runs_through_the_hardware_box_scheduler(
    project: None,
    fake_deployment: Path,
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    params: dict[str, Any],
    expected_muxes: list[int],
    excluded: set[str],
) -> None:
    """The fake template's MUX targets go through the scheduler the hardware templates use.

    The fake preset wires each MUX to its own QuEL-1 A box, so the box-aware scheduler puts
    every selected MUX in one Box A stage as its own parallel group, with the MUX's qubits in
    order inside the group, exactly as it would for a hardware chip with that wiring.
    """
    from qdash.workflow.engine import OneQubitScheduler
    from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths
    from qdash.workflow.service import strategy
    from qdash.workflow.service.steps.pipeline import StepContext

    _create_fake_chip(test_client)
    targets, step = _template_run(monkeypatch, **params)
    assert step.mode == "scheduled"

    expected_groups = [
        [qid for qid in _mux_qids(mux) if qid not in excluded] for mux in expected_muxes
    ]
    assert sorted(targets.to_qids(CHIP_ID), key=int) == [
        qid for group in expected_groups for qid in group
    ]

    # The schedule the hardware scheduler derives from the generated wiring.
    schedule = OneQubitScheduler(
        chip_id=CHIP_ID, wiring_config_path=str(get_qubex_paths().wiring_yaml(CHIP_ID))
    ).generate_from_mux(mux_ids=targets.mux_ids, exclude_qids=targets.exclude_qids)
    [stage] = schedule.stages
    assert stage.box_type == "A"
    assert stage.mux_ids == set(expected_muxes)
    assert stage.parallel_groups == expected_groups

    # Executing the step hands exactly those MUX groups to the parallel MUX runner.
    calls: list[list[list[str]]] = []

    def _record_mux_run(
        mux_groups: list[list[str]], tasks: list[str], session_config: dict[str, Any], **_: Any
    ) -> dict[str, Any]:
        calls.append(mux_groups)
        assert tasks == FAKE_CALIBRATION_TASKS
        assert session_config["backend_name"] == "fake"
        return {qid: {"status": "success"} for group in mux_groups for qid in group}

    monkeypatch.setattr(strategy, "run_mux_calibrations_parallel", _record_mux_run)
    service = _RecordingStageService()
    ctx = step.execute(service, targets, StepContext())

    assert calls == [expected_groups]
    assert list(service.stage_results) == ["1q_scheduled"]
    assert sorted(ctx.metadata["calibration"].successful_qids(), key=int) == [
        qid for group in expected_groups for qid in group
    ]
