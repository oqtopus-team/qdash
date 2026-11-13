"""Fake calibration runs follow the chip topology's MUX mapping end to end.

Each test creates the fake chip through the API, as the Create Chip dialog does on a fake
deployment, and points it at a topology template. A calibration pipeline then runs through the
real code path: target expansion, the box-aware one-qubit scheduler, the execution lock, worker
sessions, the ``FakeExperiment`` simulator, task execution, MUX result fan-out and persistence
in the in-memory calibration database of ``tests/conftest.py``.

Only process plumbing is replaced. The test suite stubs Prefect, so ``.submit`` runs each MUX
group in this process and the Dask runner is not started. The topology directory is a
temporary copy of the public bundled templates plus synthetic templates invented for these
tests; no lab configuration, database or hardware is used.

The synthetic topology reuses the fake preset's wiring (16 MUXes with four control ports each)
and declares sparse MUX IDs whose members are permuted, non-consecutive and partial, plus
standalone qubits that no MUX lists and qubits the topology does not define at all.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
import yaml

from qdash.common.mux_mapping import MuxMappingError
from qdash.datamodel.task import OutputParameterSpec
from qdash.datamodel.task_call import TaskCall
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.workflow.calibtasks.base import BaseTask, PostProcessResult, PreProcessResult, RunResult
from qdash.workflow.calibtasks.fake.base import FakeTask
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
SPARSE_STANDALONE = ["20", "21", "37"]
SPARSE_QUBITS = sorted({q for members in SPARSE_MUXES.values() for q in members} | {20, 21, 37})
SPARSE_COUPLINGS = [[38, 36], [36, 37], [37, 39], [14, 12], [20, 21], [61, 60], [39, 61]]

MUX_PROBE = "FakeMuxProbeForTest"
SYSTEM_PROBE = "FakeSystemProbeForTest"
COUPLING_PROBE = "FakeCouplingProbeForTest"
QUBIT_TASKS = [TaskCall(name="FakeBringUp"), TaskCall(name="CheckRabi")]


# --------------------------------------------------------------------------- fixtures


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
def in_process_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run Prefect ``.submit`` calls in this process instead of Dask worker processes.

    Only the process plumbing changes: each submitted MUX group, qubit or pair still opens a
    borrowed worker ``CalibSession`` with its own ``FakeBackend``.
    """
    from qdash.workflow.service._internal import scheduling_tasks

    class _Done:
        def __init__(self, value: Any) -> None:
            self._value = value

        def result(self) -> Any:
            return self._value

    monkeypatch.setattr(scheduling_tasks, "_get_dask_task_runner", lambda *_a, **_k: None)
    for name in (
        "calibrate_mux_qubits",
        "calibrate_single_qubit",
        "execute_coupling_pair",
        "calibrate_qubit_batch",
    ):
        function = getattr(scheduling_tasks, name)
        monkeypatch.setattr(
            function,
            "submit",
            lambda *args, _f=function, **kwargs: _Done(_f(*args, **kwargs)),
            raising=False,
        )


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


@pytest.fixture
def mux_probe() -> Iterator[type[BaseTask]]:
    """A MUX-level task registered for the fake backend only during the test.

    The fake backend offers no MUX-level task of its own, so this one stands in for
    ``CheckResonatorSpectroscopy``: it reads the representative qubit's resonator from
    ``FakeExperiment`` and publishes it for every member of the MUX.
    """

    class FakeMuxProbe(FakeTask):
        name: str = MUX_PROBE
        task_type: str = "qubit"
        is_mux_level: bool = True
        timeout: int = 60
        batch_runs: ClassVar[list[list[str]]] = []
        output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
            "mux_probe_representative": OutputParameterSpec(
                unit="", description="Representative qubit that measured the MUX"
            ),
        }

        def preprocess(self, backend: Any, qid: str) -> PreProcessResult:
            return PreProcessResult(input_parameters=self.input_parameters)

        def run(self, backend: Any, qid: str) -> RunResult:
            exp = backend.get_instance()
            label = exp.get_qubit_label(int(qid))
            assert label == f"Q{int(qid):02d}", (qid, label, exp.qubit_labels)
            exp.get_target(exp.get_resonator_label(int(qid)))
            return RunResult(raw_result={"representative": int(qid)})

        def batch_run(self, backend: Any, qids: list[str]) -> RunResult:
            # Like CheckResonatorSpectroscopy.batch_run: measure the first qid's MUX once.
            FakeMuxProbe.batch_runs.append(list(qids))
            return self.run(backend, qids[0])

        def postprocess(
            self, backend: Any, execution_id: str, run_result: RunResult, qid: str
        ) -> PostProcessResult:
            value = run_result.raw_result["representative"]
            self.output_parameters["mux_probe_representative"].value = value
            return PostProcessResult(output_parameters=self.attach_execution_id(execution_id))

    yield FakeMuxProbe
    BaseTask.registry.get("fake", {}).pop(MUX_PROBE, None)


@pytest.fixture
def system_probe() -> Iterator[type[BaseTask]]:
    """A system task registered for the fake backend only during the test."""

    class FakeSystemProbe(FakeTask):
        name: str = SYSTEM_PROBE
        task_type: str = "system"
        timeout: int = 60

        def preprocess(self, backend: Any, qid: str) -> PreProcessResult:
            return PreProcessResult(input_parameters=self.input_parameters)

        def run(self, backend: Any, qid: str) -> RunResult:
            return RunResult(raw_result={})

        def postprocess(
            self, backend: Any, execution_id: str, run_result: RunResult, qid: str
        ) -> PostProcessResult:
            return PostProcessResult(output_parameters={})

    yield FakeSystemProbe
    BaseTask.registry.get("fake", {}).pop(SYSTEM_PROBE, None)


@pytest.fixture
def coupling_probe() -> Iterator[type[BaseTask]]:
    """A coupling task registered for the fake backend only during the test.

    The fake backend offers no two-qubit task, so this one checks that the pair's
    ``FakeExperiment`` simulates both qubits and records which pair it measured.
    """

    class FakeCouplingProbe(FakeTask):
        name: str = COUPLING_PROBE
        task_type: str = "coupling"
        timeout: int = 60
        output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
            "coupling_probe_control": OutputParameterSpec(
                unit="", description="Control qubit of the measured pair"
            ),
        }

        def preprocess(self, backend: Any, qid: str) -> PreProcessResult:
            return PreProcessResult(input_parameters=self.input_parameters)

        def run(self, backend: Any, qid: str) -> RunResult:
            exp = backend.get_instance()
            control, target = (int(part) for part in qid.split("-"))
            labels = [exp.get_qubit_label(control), exp.get_qubit_label(target)]
            assert labels == [f"Q{control:02d}", f"Q{target:02d}"], (qid, exp.qubit_labels)
            for label in labels:
                exp.get_target(label)
            return RunResult(raw_result={"control": control})

        def postprocess(
            self, backend: Any, execution_id: str, run_result: RunResult, qid: str
        ) -> PostProcessResult:
            value = run_result.raw_result["control"]
            self.output_parameters["coupling_probe_control"].value = value
            return PostProcessResult(output_parameters=self.attach_execution_id(execution_id))

    yield FakeCouplingProbe
    BaseTask.registry.get("fake", {}).pop(COUPLING_PROBE, None)


# --------------------------------------------------------------------------- helpers


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


def _recorded_mux_groups(monkeypatch: pytest.MonkeyPatch) -> list[list[list[str]]]:
    """Record the groups of every parallel MUX run while letting it run."""
    from qdash.workflow.service import strategy
    from qdash.workflow.service._internal.scheduling_tasks import (
        run_mux_calibrations_parallel as original,
    )

    calls: list[list[list[str]]] = []

    def recording(mux_groups: list[list[str]], *args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append([list(group) for group in mux_groups])
        result: dict[str, Any] = original(mux_groups, *args, **kwargs)
        return result

    monkeypatch.setattr(strategy, "run_mux_calibrations_parallel", recording)
    return calls


def _assert_completed(task_names: list[str], qids: list[str]) -> None:
    by_key = _results()
    for task_name in task_names:
        for qid in qids:
            result = by_key.get((task_name, qid))
            assert result is not None, (task_name, qid, sorted(by_key))
            assert result.status == "completed", (task_name, qid, result.message)


def _stored(qid: str, name: str) -> Any:
    qubit = QubitDocument.find_one({"project_id": PROJECT_ID, "chip_id": CHIP, "qid": qid}).run()
    assert qubit is not None, qid
    return qubit.data.get(name, {}).get("value")


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


# ------------------------------------------------------------------ public topology


def test_public_mux_targets_run_on_the_fake_backend(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    in_process_workers: None,
    lock_claims: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fake preset's public 64-qubit topology: MUX 2 and 15 expand to their four qubits."""
    from qdash.workflow.service.targets import MuxTargets

    _fake_chip(test_client, "square-lattice-mux-64")
    groups = _recorded_mux_groups(monkeypatch)

    _session().run_pipeline(MuxTargets(mux_ids=[2, 15]), [_step(QUBIT_TASKS)])

    expected = [["8", "9", "10", "11"], ["60", "61", "62", "63"]]
    assert groups == [expected]
    qids = [qid for group in expected for qid in group]
    _assert_completed(["FakeBringUp", "CheckRabi"], qids)
    assert set(_results()) == {(t, q) for t in ("FakeBringUp", "CheckRabi") for q in qids}
    for qid in qids:
        assert _stored(qid, "qubit_frequency") is not None
    # MUX targets reserve exactly their MUXes' wiring, not the whole chip.
    [claim] = lock_claims
    assert claim["exclusive"] is False
    assert {"mux:2", "mux:15"} <= set(claim["resources"])
    assert not any(
        r.startswith("mux:") and r not in {"mux:2", "mux:15"} for r in claim["resources"]
    )
    execution = ExecutionHistoryDocument.find_one({"project_id": PROJECT_ID, "chip_id": CHIP}).run()
    assert execution is not None
    assert execution.status == "completed"


# --------------------------------------------------------------- synthetic topology


def test_sparse_permuted_mux_targets_run_their_declared_members(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    in_process_workers: None,
    lock_claims: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sparse MUX IDs expand to their declared members in slot order, never to ``qid // 4``."""
    from qdash.workflow.service.targets import MuxTargets

    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)
    groups = _recorded_mux_groups(monkeypatch)
    simulated = _record_fake_connects(monkeypatch)

    targets = MuxTargets(mux_ids=[9, 15])
    mapping = _session().mux_mapping
    assert targets.to_qids(CHIP, mux_mapping=mapping) == ["36", "38", "39", "60", "61"]
    _session().run_pipeline(targets, [_step(QUBIT_TASKS)])

    # One parallel stage; each MUX keeps its declared slot order.
    assert groups == [[["38", "36", "39"], ["61", "60"]]]
    qids = ["38", "36", "39", "61", "60"]
    _assert_completed(["FakeBringUp", "CheckRabi"], qids)
    # Qubit 37 sits between 36 and 39 but is standalone; 62 and 63 are unknown here.
    assert {qid for _, qid in _results()} == set(qids)
    # Each worker simulates exactly its MUX group's qubits.
    assert ("Q38", "Q36", "Q39") in simulated
    assert ("Q61", "Q60") in simulated
    [claim] = lock_claims
    assert claim["exclusive"] is False
    assert {r for r in claim["resources"] if r.startswith("mux:")} == {"mux:9", "mux:15"}


def test_mux_task_fans_out_to_the_declared_members(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    in_process_workers: None,
    mux_probe: type[BaseTask],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A MUX task runs on slot 0 and its result reaches exactly the MUX's declared members."""
    from qdash.workflow.service.targets import MuxTargets

    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)

    _session().run_pipeline(MuxTargets(mux_ids=[3, 9]), [_step([TaskCall(name=MUX_PROBE)])])

    by_key = _results()
    probe_qids = {qid for name, qid in by_key if name == MUX_PROBE}
    assert probe_qids == {"14", "12", "15", "13", "38", "36", "39"}
    for members, representative in ((["14", "12", "15", "13"], 14), (["38", "36", "39"], 38)):
        for qid in members:
            result = by_key[(MUX_PROBE, qid)]
            assert result.status == "completed", (qid, result.message)
            value = result.output_parameters["mux_probe_representative"]["value"]
            assert value == representative, qid
    # The representatives ran the task; every other member got the fan-out.
    for qid in ("12", "15", "13", "36", "39"):
        assert "MUX distribution" in (by_key[(MUX_PROBE, qid)].message or "")
    # Standalone 37 and legacy neighbours outside the topology receive nothing.
    assert not probe_qids & {"37", "40", "62", "63"}


def test_mixed_mux_and_standalone_qubits_all_run_under_a_chip_lock(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    in_process_workers: None,
    lock_claims: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Qubit targets keep standalone qubits: they run after the MUX stage, one at a time."""
    from qdash.workflow.service.targets import AllQubitTargets, QubitTargets

    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)
    groups = _recorded_mux_groups(monkeypatch)

    targets = QubitTargets(qids=["36", "37", "38", "20", "60"])
    _session().run_pipeline(targets, [_step(QUBIT_TASKS)])

    # MUX members first (MUX 9 and MUX 15 in parallel, each in slot order), then the
    # standalone qubits in a stage of their own, one after another in a single group.
    assert groups == [[["38", "36"], ["60"]], [["20", "37"]]]
    _assert_completed(["FakeBringUp", "CheckRabi"], ["36", "37", "38", "20", "60"])
    # A standalone qubit's hardware is not in the wiring, so the run claims the whole chip.
    [claim] = lock_claims
    assert claim["exclusive"] is True

    # AllQubitTargets keeps every known qubit, multiplexed or standalone.
    assert AllQubitTargets().to_qids(CHIP, mux_mapping=_session().mux_mapping) == [
        str(q) for q in SPARSE_QUBITS
    ]


def test_parallel_by_round_mode_rounds_by_declared_slot(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    in_process_workers: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rounds put qubits of one local slot together; standalone qubits run alone."""
    from qdash.workflow.service import strategy
    from qdash.workflow.service._internal.scheduling_tasks import (
        run_qubit_calibrations_parallel as original,
    )
    from qdash.workflow.service.targets import QubitTargets

    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)
    rounds: list[list[str]] = []

    def recording(qids: list[str], *args: Any, **kwargs: Any) -> dict[str, Any]:
        rounds.append(list(qids))
        result: dict[str, Any] = original(qids, *args, **kwargs)
        return result

    monkeypatch.setattr(strategy, "run_qubit_calibrations_parallel", recording)
    targets = ["36", "37", "38", "20", "60", "61"]

    _session().run_pipeline(
        QubitTargets(qids=targets), [_step(QUBIT_TASKS, mode="parallel_by_round")]
    )

    # MUX 9 and 15 are odd, so the checkerboard runs slot 2 first; neither selection has a
    # slot-2 qubit. Slot 0 (38 and 61, not the legacy 36 and 60) runs together, then slot 1,
    # then each standalone qubit in a round of its own.
    assert rounds == [["38", "61"], ["36", "60"], ["20"], ["37"]]
    _assert_completed(["FakeBringUp", "CheckRabi"], targets)
    assert {qid for _, qid in _results()} == set(targets)


def test_all_standalone_topology_runs_every_qubit_serially(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    in_process_workers: None,
    lock_claims: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public linear-16 template declares no MUX: qubit targets run one at a time."""
    from qdash.workflow.service.targets import AllMuxTargets, QubitTargets

    _fake_chip(test_client, "linear-16", size=16)
    groups = _recorded_mux_groups(monkeypatch)

    _session().run_pipeline(QubitTargets(qids=["5", "2", "11"]), [_step(QUBIT_TASKS)])

    # One stage, one group: the qubits run one after another, never in parallel.
    assert groups == [[["2", "5", "11"]]]
    _assert_completed(["FakeBringUp", "CheckRabi"], ["2", "5", "11"])
    [claim] = lock_claims
    assert claim["exclusive"] is True
    with pytest.raises(ValueError, match="declares no MUX"):
        AllMuxTargets().to_qids(CHIP, mux_mapping=_session().mux_mapping)


# ------------------------------------------------------------- rejected targets


def test_mux_task_on_a_standalone_qubit_fails_without_running(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    in_process_workers: None,
    mux_probe: type[BaseTask],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qdash.workflow.service.targets import QubitTargets

    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)

    ctx = _session().run_pipeline(
        QubitTargets(qids=["37"]), [_step([TaskCall(name=MUX_PROBE), TaskCall(name="FakeBringUp")])]
    )

    result = ctx["metadata"]["check"].get_qubit("37")
    [probe] = [call for call in result.calls if call.name == MUX_PROBE]
    assert probe.status == "failed"
    assert "standalone" in (probe.error or "")
    by_key = _results()
    # The probe never ran, so no task result exists for it; the qubit task after it still ran.
    assert (MUX_PROBE, "37") not in by_key
    assert by_key[("FakeBringUp", "37")].status == "completed"

    session = _session()
    with session.owned_execution(["37"]), pytest.raises(MuxMappingError, match="standalone"):
        session.execute_task(MUX_PROBE, "37")
    assert (MUX_PROBE, "37") not in _results()


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
    in_process_workers: None,
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


# -------------------------------------------------------------------- couplings


def test_coupling_targets_follow_the_topology_without_drops(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
) -> None:
    """Coupling targets of a MUX or qubit selection keep every declared pair it covers."""
    from qdash.common.mux_mapping import resolve_chip_mux_mapping
    from qdash.workflow.service.targets import AllQubitTargets, MuxTargets, QubitTargets

    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)
    mapping = resolve_chip_mux_mapping(PROJECT_ID, CHIP)

    def pairs(ids: list[str]) -> set[frozenset[str]]:
        return {frozenset(cid.split("-")) for cid in ids}

    declared = {frozenset((str(a), str(b))) for a, b in SPARSE_COUPLINGS}
    every = AllQubitTargets().to_coupling_ids(CHIP, project_id=PROJECT_ID, mux_mapping=mapping)
    assert pairs(every) == declared
    assert len(every) == len(declared)

    in_mux_9 = MuxTargets(mux_ids=[9]).to_coupling_ids(
        CHIP, project_id=PROJECT_ID, mux_mapping=mapping
    )
    assert pairs(in_mux_9) == {frozenset(("38", "36"))}
    standalone_pair = QubitTargets(qids=["20", "21", "37", "36"]).to_coupling_ids(
        CHIP, project_id=PROJECT_ID, mux_mapping=mapping
    )
    assert pairs(standalone_pair) == {frozenset(("20", "21")), frozenset(("36", "37"))}


def test_coupling_step_runs_every_declared_pair_of_the_selection(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    in_process_workers: None,
    coupling_probe: type[BaseTask],
    lock_claims: list[dict[str, Any]],
) -> None:
    """In-MUX, cross-MUX and standalone pairs all run on the fake backend; none is dropped."""
    from qdash.workflow.service.steps import CustomTwoQubit
    from qdash.workflow.service.targets import QubitTargets

    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)
    selection = ["20", "21", "36", "37", "38", "39", "60", "61"]

    _session().run_pipeline(
        QubitTargets(qids=selection),
        [CustomTwoQubit(step_name="pairs", tasks=[TaskCall(name=COUPLING_PROBE)])],
    )

    declared = {
        frozenset((str(a), str(b)))
        for a, b in SPARSE_COUPLINGS
        if str(a) in selection and str(b) in selection
    }
    by_key = _results()
    ran = {qid for name, qid in by_key if name == COUPLING_PROBE}
    assert {frozenset(pair.split("-")) for pair in ran} == declared
    assert len(ran) == len(declared)
    for pair in ran:
        result = by_key[(COUPLING_PROBE, pair)]
        assert result.status == "completed", (pair, result.message)
        control = result.output_parameters["coupling_probe_control"]["value"]
        assert control == int(pair.split("-")[0]), pair
    # Standalone qubits 20, 21 and 37 have no wiring, so the run claims the whole chip.
    [claim] = lock_claims
    assert claim["exclusive"] is True


def test_topology_edit_during_a_run_keeps_the_planned_mapping(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    in_process_workers: None,
    mux_probe: type[BaseTask],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A chip topology edited after planning changes neither workers nor MUX fan-out.

    The owner plans MUX 3 and 9 with the sparse topology. Before any worker starts, the
    chip is pointed at a template that reorders both MUXes (a different slot 0) and moves
    standalone qubit 37 into MUX 9. Every worker receives the owner's mapping through a
    JSON round trip of its ``WorkerSpec``, as a Dask worker would, and never reads the
    edited topology.
    """
    from qdash.common.mux_mapping import resolve_chip_mux_mapping
    from qdash.dbmodel.chip import ChipDocument
    from qdash.workflow.service import strategy
    from qdash.workflow.service._internal import scheduling_tasks
    from qdash.workflow.service._internal.session import borrowed_session
    from qdash.workflow.service._internal.settings import WorkerSpec
    from qdash.workflow.service.targets import MuxTargets

    mutated_id = "synthetic-sparse-reordered"
    data = yaml.safe_load((topologies / f"{SPARSE_TOPOLOGY_ID}.yaml").read_text(encoding="utf-8"))
    data.update(id=mutated_id, muxes={3: [12, 13, 14, 15], 9: [36, 37, 38, 39], 15: [60, 61]})
    (topologies / f"{mutated_id}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)

    run_groups = scheduling_tasks.run_mux_calibrations_parallel

    def edit_topology_then_run(mux_groups: list[list[str]], *args: Any, **kwargs: Any) -> Any:
        chip = ChipDocument.find_one({"project_id": PROJECT_ID, "chip_id": CHIP}).run()
        assert chip is not None
        chip.topology_id = mutated_id
        chip.save()
        return run_groups(mux_groups, *args, **kwargs)

    worker_mappings: list[Any] = []
    borrow = borrowed_session

    def serialized_borrow(spec: WorkerSpec, qids: list[str]) -> Any:
        restored = WorkerSpec.model_validate_json(spec.model_dump_json())
        assert restored == spec
        worker_mappings.append(getattr(restored, "mux_mapping", None))
        return borrow(restored, qids)

    monkeypatch.setattr(strategy, "run_mux_calibrations_parallel", edit_topology_then_run)
    monkeypatch.setattr(scheduling_tasks, "borrowed_session", serialized_borrow)

    _session().run_pipeline(MuxTargets(mux_ids=[3, 9]), [_step([TaskCall(name=MUX_PROBE)])])

    # The edit took effect: a fresh resolution now sees the reordered MUXes.
    edited = resolve_chip_mux_mapping(PROJECT_ID, CHIP)
    assert edited.qids_of(3)[0] == "12"
    assert edited.qids_of(9) == ("36", "37", "38", "39")
    # Representatives and fan-out follow the planned slots and members.
    by_key = _results()
    probe_qids = {qid for name, qid in by_key if name == MUX_PROBE}
    assert probe_qids == {"14", "12", "15", "13", "38", "36", "39"}
    for members, representative in ((["14", "12", "15", "13"], 14), (["38", "36", "39"], 38)):
        for qid in members:
            result = by_key[(MUX_PROBE, qid)]
            assert result.status == "completed", (qid, result.message)
            assert result.output_parameters["mux_probe_representative"]["value"] == representative
    # Every worker ran with the planned mapping.
    assert worker_mappings
    for snapshot in worker_mappings:
        assert snapshot is not None
        assert snapshot.topology_id == SPARSE_TOPOLOGY_ID
        assert snapshot.to_mapping().qids_of(9) == ("38", "36", "39")


def test_mux_fanout_never_resolves_a_repaired_topology(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    mux_probe: type[BaseTask],
    system_probe: type[BaseTask],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fake owner whose topology failed to resolve pins no mapping for MUX fan-out.

    The session claims the whole chip and keeps ``CalibConfig.mux_mapping`` unset. The
    topology is then repaired, so a fresh resolution would succeed; a MUX-level task run
    through the engine, past the session's target checks, still fails before it runs and
    writes no result for any MUX member, and nothing reads the chip topology again.
    """
    from qdash.common import mux_mapping as mux_mapping_module
    from qdash.dbmodel.chip import ChipDocument

    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)
    chip = ChipDocument.find_one({"project_id": PROJECT_ID, "chip_id": CHIP}).run()
    assert chip is not None
    chip.topology_id = "synthetic-missing"
    chip.save()

    session = _session()
    with session.owned_execution(["14"]):
        orchestrator = session._orchestrator
        assert orchestrator is not None
        assert orchestrator.config.mux_mapping is None

        chip.topology_id = SPARSE_TOPOLOGY_ID
        chip.save()
        lookups: list[tuple[Any, ...]] = []
        resolve = mux_mapping_module.resolve_chip_mux_mapping

        def recording(*args: Any) -> Any:
            lookups.append(args)
            return resolve(*args)

        monkeypatch.setattr(mux_mapping_module, "resolve_chip_mux_mapping", recording)
        # A system task fans nothing out and still runs without a pinned mapping.
        assert "task_id" in session.execute_task(SYSTEM_PROBE, "system")
        # The session keeps its failed resolution instead of reading the repair.
        with pytest.raises(MuxMappingError, match="synthetic-missing"):
            session.execute_task(MUX_PROBE, "14")
        # The task runner reports the engine's MuxMappingError as a task failure.
        with pytest.raises(RuntimeError, match="no pinned MUX mapping"):
            orchestrator.run_task(MUX_PROBE, "14")
        # The batch path holds the same invariant: no batch_run, no saved result.
        with pytest.raises(RuntimeError, match="no pinned MUX mapping"):
            orchestrator.run_task_batch(MUX_PROBE, ["38", "36"])
        assert lookups == []
    assert mux_probe.batch_runs == []  # type: ignore[attr-defined]

    by_key = _results()
    assert by_key[(SYSTEM_PROBE, "")].status == "completed"
    assert by_key[(MUX_PROBE, "14")].status == "failed"
    for member in ("12", "15", "13"):
        assert (MUX_PROBE, member) not in by_key
    for qid in ("38", "36"):
        result = by_key[(MUX_PROBE, qid)]
        assert result.status == "failed", qid
        assert "no pinned MUX mapping" in (result.message or ""), qid
        assert not result.output_parameters, qid
    assert (MUX_PROBE, "39") not in by_key


def test_pinned_mux_batch_runs_once_for_the_declared_members(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    mux_probe: type[BaseTask],
) -> None:
    """With a pinned mapping, a MUX-level batch through the orchestrator still runs once."""
    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)

    session = _session()
    with session.owned_execution(["38", "36", "39"]):
        orchestrator = session._orchestrator
        assert orchestrator is not None
        assert orchestrator.config.mux_mapping is not None
        results = orchestrator.run_task_batch(MUX_PROBE, ["38", "36", "39"])

    assert set(results) == {"38", "36", "39"}
    assert mux_probe.batch_runs == [["38", "36", "39"]]  # type: ignore[attr-defined]
    by_key = _results()
    for qid in ("38", "36", "39"):
        result = by_key[(MUX_PROBE, qid)]
        assert result.status == "completed", (qid, result.message)
        assert result.output_parameters["mux_probe_representative"]["value"] == 38, qid


# ----------------------------------------------------------------------- manual rounds


def test_manual_rounds_run_as_written_on_the_topology_mapping(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    topologies: Path,
    test_client: TestClient,
    in_process_workers: None,
    lock_claims: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual rounds keep their written order; a standalone qubit runs in a round of its own."""
    from qdash.workflow.service._internal import scheduling_tasks
    from qdash.workflow.service.steps import CustomOneQubit
    from qdash.workflow.service.targets import QubitTargets

    _fake_chip(test_client, SPARSE_TOPOLOGY_ID)
    original = scheduling_tasks.run_qubit_calibrations_parallel
    rounds: list[list[str]] = []

    def recording(qids: list[str], *args: Any, **kwargs: Any) -> dict[str, Any]:
        rounds.append(list(qids))
        result: dict[str, Any] = original(qids, *args, **kwargs)
        return result

    monkeypatch.setattr(scheduling_tasks, "run_qubit_calibrations_parallel", recording)
    # Slot 1 of MUX 9 (36) runs after slot 0 of MUX 15 (61): the written order, not slot order.
    written = [["61", "38"], ["37"], ["36"]]
    targets = ["38", "61", "36", "37"]
    step = CustomOneQubit(
        step_name="check",
        tasks=QUBIT_TASKS,
        execution_mode="manual",
        rounds=written,
        continue_on_failure=True,
    )

    _session().run_pipeline(QubitTargets(qids=targets), [step])

    assert rounds == written
    _assert_completed(["FakeBringUp", "CheckRabi"], targets)
    assert len(lock_claims) == 1


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
    in_process_workers: None,
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
    in_process_workers: None,
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
