"""Invalid topology targets and manual rounds are rejected before task execution."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml

from qdash.common.mux_mapping import MuxMappingError
from qdash.datamodel.task_call import TaskCall
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from tests.qdash.workflow.test_fake_chip_preset import CHIP_ID as PRESET_CHIP_ID
from tests.qdash.workflow.test_fake_chip_preset import (  # noqa: F401 - pytest fixtures
    HEADERS,
    PROJECT_ID,
    USERNAME,
    _create_fake_chip,
    fake_deployment,
    project,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi.testclient import TestClient

    from qdash.datamodel.one_qubit_execution_mode import OneQubitStepExecutionMode
    from qdash.workflow.service._internal.session import CalibSession

REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_TOPOLOGIES = REPO_ROOT / "config" / "domain" / "topologies"

CHIP = "topology-chip"
SPARSE_TOPOLOGY_ID = "synthetic-sparse-permuted"
# Invented for these tests. MUX IDs are sparse and declared out of order; members are permuted
# (slot 0 is not the lowest qubit), partial (MUX 9 skips 37, MUX 15 has two qubits) and need not
# follow ``qid // 4``. Qubits 37, 20 and 21 are standalone; any other qubit is unknown.
SPARSE_MUXES: dict[int, list[int]] = {
    15: [61, 60],
    3: [14, 12, 15, 13],
    9: [38, 36, 39],
}
SPARSE_QUBITS = sorted({q for members in SPARSE_MUXES.values() for q in members} | {20, 21, 37})
SPARSE_COUPLINGS = [[38, 36], [36, 37], [37, 39], [14, 12], [20, 21], [61, 60], [39, 61]]

QUBIT_TASKS = [TaskCall(name="FakeBringUp"), TaskCall(name="CheckRabi")]


def _write_sparse_topology(directory: Path) -> None:
    qubits = {qid: {"row": index // 8, "col": index % 8} for index, qid in enumerate(SPARSE_QUBITS)}
    data = {
        "id": SPARSE_TOPOLOGY_ID,
        "name": "Synthetic sparse permuted MUXes",
        "grid_size": 8,
        # The fake preset scaffolds a 64-qubit chip; this template defines only some of them.
        "num_qubits": 64,
        "muxes": SPARSE_MUXES,
        "qubits": qubits,
        "couplings": SPARSE_COUPLINGS,
    }
    (directory / f"{SPARSE_TOPOLOGY_ID}.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )


@pytest.fixture
def topologies(
    tmp_path: Path,
    fake_deployment: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Path]:
    """The public bundled templates plus the synthetic one, in a temporary directory.

    The execution lock reads ``wiring.yaml`` through ``CONFIG_PATH``, as a deployment does;
    point it at the same temporary configuration tree the workflow uses.
    """
    from qdash.common.config import topology

    monkeypatch.setenv("CONFIG_PATH", str(fake_deployment))
    directory = tmp_path / "topologies"
    directory.mkdir()
    for path in PUBLIC_TOPOLOGIES.glob("*.yaml"):
        shutil.copy(path, directory / path.name)
    _write_sparse_topology(directory)
    monkeypatch.setattr(topology, "_topologies_dir", lambda: directory)
    topology.load_topology.cache_clear()
    yield directory
    topology.load_topology.cache_clear()


@pytest.fixture
def lock_claims(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Every execution lock claim, recorded while the real lock document takes it."""
    claims: list[dict[str, Any]] = []
    original = ExecutionLockDocument.try_lock.__func__  # type: ignore[attr-defined]

    def recording(cls: Any, /, **kwargs: Any) -> bool:
        claims.append(kwargs)
        result: bool = original(cls, **kwargs)
        return result

    monkeypatch.setattr(ExecutionLockDocument, "try_lock", classmethod(recording))
    return claims


def _fake_chip(client: TestClient, topology_id: str, *, size: int = 64) -> None:
    """Create ``CHIP`` through the API with ``topology_id``, as the Create Chip dialog does.

    The fake preset only scaffolds the public 64-qubit topology, so a 64-qubit chip first gets
    the preset chip and then copies its virtual wiring (16 MUXes with four control ports
    each), the way a user starts a chip from an existing system. Other sizes get an empty
    configuration directory, which a chip without MUXes never reads.
    """
    config: dict[str, Any] = {"create": True}
    if size == 64:
        _create_fake_chip(client)
        config = {"source_system_id": PRESET_CHIP_ID}
    response = client.post(
        "/chips",
        headers=HEADERS,
        json={"chip_id": CHIP, "size": size, "topology_id": topology_id, "config": config},
    )
    assert response.status_code == 200, response.text
    assert response.json()["topology_id"] == topology_id


def _session() -> CalibSession:
    from qdash.workflow.service._internal.session import CalibSession
    from qdash.workflow.service._internal.settings import GitHubPolicy, SessionSettings

    return CalibSession(
        SessionSettings(
            username=USERNAME,
            chip_id=CHIP,
            project_id=PROJECT_ID,
            backend_name="fake",
            flow_name="topology_check",
            github=GitHubPolicy.disabled(),
        )
    )


def _step(tasks: list[TaskCall], mode: OneQubitStepExecutionMode = "parallel_by_mux") -> Any:
    from qdash.workflow.service.steps import CustomOneQubit

    return CustomOneQubit(
        step_name="check", tasks=tasks, execution_mode=mode, continue_on_failure=True
    )


def _results() -> dict[tuple[str, str], TaskResultHistoryDocument]:
    results = TaskResultHistoryDocument.find({"project_id": PROJECT_ID, "chip_id": CHIP}).run()
    return {(result.name, result.qid): result for result in results}


def _record_fake_connects(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """The qubit labels of every ``FakeExperiment`` connected from now on."""
    from qdash.workflow.engine.backend.fake_qubex import FakeExperiment

    connected: list[Any] = []
    connect = FakeExperiment.connect

    def recording(self: FakeExperiment, *args: Any, **kwargs: Any) -> Any:
        connected.append(tuple(self.qubit_labels))
        return connect(self, *args, **kwargs)

    monkeypatch.setattr(FakeExperiment, "connect", recording)
    return connected


@pytest.mark.parametrize(
    ("task_name", "target", "batch"),
    [
        ("FakeBringUp", "40", False),
        ("FakeBringUp", "62", True),
        ("CheckRabi", "36-40", False),
    ],
    ids=["unknown-single", "unknown-batch", "unknown-coupling"],
)
def test_unknown_targets_are_rejected_before_the_fake_backend_runs(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    task_name: str,
    target: str,
    batch: bool,
) -> None:
    """Qubits the topology does not define never reach the orchestrator or the simulator.

    The fake chip's wiring and the legacy layout both cover qubits 40 and 62, so only the
    topology check can stop them.
    """
    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)
    session = _session()

    with session.owned_execution(["36"]):
        connected = _record_fake_connects(monkeypatch)
        executed: list[Any] = []
        orchestrator = session._orchestrator
        assert orchestrator is not None
        for method in ("run_task", "run_task_batch"):
            original = getattr(orchestrator, method)

            def recording(*args: Any, _original: Any = original, **kwargs: Any) -> Any:
                executed.append(args)
                return _original(*args, **kwargs)

            monkeypatch.setattr(orchestrator, method, recording)
        with pytest.raises(MuxMappingError, match="not defined in the chip topology"):
            if batch:
                session.execute_task_batch(task_name, ["36", target])
            else:
                session.execute_task(task_name, target)
        assert executed == []
        assert connected == []
    assert (task_name, target) not in _results()


def test_unknown_mux_targets_are_rejected_before_any_execution(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    lock_claims: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MUX 0 exists in the wiring and in the legacy layout, but not in this topology."""
    from qdash.workflow.service.targets import MuxTargets

    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)
    connected = _record_fake_connects(monkeypatch)

    with pytest.raises(MuxMappingError, match="MUX 0"):
        _session().run_pipeline(MuxTargets(mux_ids=[0, 9]), [_step(QUBIT_TASKS)])

    assert connected == []
    assert lock_claims == []
    assert _results() == {}


@pytest.mark.parametrize(
    ("targets", "written", "reason"),
    [
        # 38 is in MUX 9 and 20 is standalone; qid // 4 would put 20 in MUX 5.
        (["38", "20", "36"], [["38", "20"], ["36"]], "20 is standalone"),
        # 38 and 36 are both members of MUX 9.
        (["38", "36"], [["38", "36"]], "share MUX 9"),
    ],
)
def test_manual_rounds_against_the_topology_fail_before_any_hardware(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    lock_claims: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    targets: list[str],
    written: list[list[str]],
    reason: str,
) -> None:
    from qdash.common.manual_rounds import ManualRoundsError
    from qdash.workflow.service.steps import CustomOneQubit
    from qdash.workflow.service.targets import QubitTargets

    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)
    connected = _record_fake_connects(monkeypatch)
    step = CustomOneQubit(
        step_name="check", tasks=QUBIT_TASKS, execution_mode="manual", rounds=written
    )

    with pytest.raises(ManualRoundsError, match=reason):
        _session().run_pipeline(QubitTargets(qids=targets), [step])

    assert connected == []
    assert lock_claims == []
    assert _results() == {}


def test_manual_pair_rounds_keep_standalone_pairs_alone(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    lock_claims: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """20-21 joins two standalone qubits: the CR scheduler never groups it, nor may a round."""
    from qdash.common.manual_rounds import ManualRoundsError
    from qdash.workflow.service.steps import CustomTwoQubit
    from qdash.workflow.service.targets import QubitTargets

    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)
    connected = _record_fake_connects(monkeypatch)
    step = CustomTwoQubit(
        step_name="cr",
        tasks=[TaskCall(name="CheckCrossResonance")],
        execution_mode="manual",
        rounds=[[("14", "12"), ("20", "21")]],
    )

    with pytest.raises(ManualRoundsError, match="20-21 uses standalone qubit 20, 21"):
        _session().run_pipeline(QubitTargets(qids=["14", "12", "20", "21"]), [step])

    assert connected == []
    assert lock_claims == []
