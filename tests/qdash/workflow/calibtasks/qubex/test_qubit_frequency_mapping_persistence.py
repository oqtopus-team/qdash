"""Resonator candidates reach CheckQubitFrequencyMapping only from the latest complete attempt.

These tests run CheckResonatorSpectroscopy through the real TaskExecutor, MUX
distributor, task-result history, and qubit calibration documents (on mongomock),
then resolve the consumer's inputs from those documents.
"""

from __future__ import annotations

import copy
from contextlib import ExitStack, suppress
from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock, patch

import plotly.graph_objects as go
import pytest
from qubex.experiment.experiment_util import ExperimentUtil

from qdash.analysis.spectroscopy.estimate_resonator_frequency import Peak, Resonance
from qdash.common.mux_mapping import MuxMapping
from qdash.datamodel.execution import ExecutionModel, ExecutionStatusModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.cw.check_qubit_frequency_mapping import (
    CheckQubitFrequencyMapping,
)
from qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy import (
    CheckResonatorSpectroscopy,
)
from qdash.workflow.engine.task.backend_saver import BackendSaver
from qdash.workflow.engine.task.executor import TaskExecutor
from qdash.workflow.engine.task.history_recorder import TaskHistoryRecorder
from qdash.workflow.engine.task.result_processor import TaskResultProcessor
from qdash.workflow.engine.task.state_manager import TaskStateManager

if TYPE_CHECKING:
    from pathlib import Path

PROJECT_ID = "project-1"
CHIP_ID = "chip-1"
MUX_QIDS = ["0", "1", "2", "3"]
PRODUCER_MODULE = "qdash.workflow.calibtasks.qubex.cw.check_resonator_spectroscopy."
CONSUMER_MODULE = "qdash.workflow.calibtasks.qubex.cw.check_qubit_frequency_mapping."
FREQUENCIES_A = [10.21, 10.29, 10.36, 10.43]
FREQUENCIES_B = [10.22, 10.30, 10.37, 10.44]
POWERS = [-34.0, -30.0, -28.0, -26.0]


@pytest.fixture(autouse=True)
def _qubex_qubit_indices(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the real Qubex create_qubit_subgroups resolve Qxx labels without a system."""
    from qubex.experiment import experiment_util

    system = SimpleNamespace(
        get_qubit=lambda label: SimpleNamespace(label=label, index=int(label[1:]))
    )
    monkeypatch.setattr(
        experiment_util,
        "SystemManager",
        SimpleNamespace(shared=lambda: SimpleNamespace(experiment_system=system)),
    )


@pytest.fixture
def chip_qubits(init_db: Any) -> None:
    for qid in MUX_QIDS:
        QubitDocument(
            project_id=PROJECT_ID,
            username="admin",
            qid=qid,
            chip_id=CHIP_ID,
            data={},
            system_info=SystemInfoModel(),
        ).insert()


def _backend() -> Any:
    return SimpleNamespace(name="fake", config={"project_id": PROJECT_ID, "chip_id": CHIP_ID})


def _execution_service(execution_id: str) -> MagicMock:
    service = MagicMock()
    service.project_id = PROJECT_ID
    service.chip_id = CHIP_ID
    service.execution_id = execution_id
    service.to_datamodel.return_value = ExecutionModel(
        project_id=PROJECT_ID,
        username="admin",
        name="frequency mapping",
        execution_id=execution_id,
        calib_data_path="/tmp/calib",
        note={},
        status=ExecutionStatusModel.RUNNING,
        tags=[],
        chip_id=CHIP_ID,
        start_at=None,
        end_at=None,
        elapsed_time=None,
        message="",
        system_info=SystemInfoModel(),
    )
    return service


def _age_recorded_attempts() -> None:
    """Move every recorded attempt back so the next execution starts strictly later."""
    for doc in TaskResultHistoryDocument.find({"project_id": PROJECT_ID}).run():
        if doc.start_at is not None:
            doc.start_at -= timedelta(minutes=10)
        if doc.end_at is not None:
            doc.end_at -= timedelta(minutes=10)
        doc.save()


def _run_producer(
    tmp_path: Path,
    execution_id: str,
    frequencies: list[float],
    powers: list[float],
    *,
    run_error: Exception | None = None,
    sibling_error_qid: str | None = None,
) -> bool:
    """Run detection-only CheckResonatorSpectroscopy for the MUX of qid 0.

    Returns whether the representative attempt succeeded.
    """
    _age_recorded_attempts()
    data_saver = MagicMock()
    data_saver.save_figures.return_value = ([], [])
    executor = TaskExecutor(
        state_manager=TaskStateManager(qids=MUX_QIDS),
        calib_dir=str(tmp_path),
        execution_id=execution_id,
        task_manager_id=f"tm-{execution_id}",
        result_processor=TaskResultProcessor(),
        history_recorder=TaskHistoryRecorder(chip_repo=MagicMock(), chip_history_repo=MagicMock()),
        data_saver=data_saver,
        mux_mapping=MuxMapping.legacy(),
    )
    producer = CheckResonatorSpectroscopy()
    producer.run_parameters = copy.deepcopy(producer.run_parameters)
    producer.run_parameters["detection_only"].value = True
    producer.run_parameters["frequency_range"].value = (10.0, 10.6, 0.002)
    producer._bare_shift_estimator_type = "config"
    raw_fig = go.Figure(
        go.Heatmap(x=[10.2, 10.3, 10.4, 10.5], y=[-60.0, -40.0], z=[[0.0] * 4, [0.0] * 4])
    )
    resonances = [
        Resonance(high_power_peaks=None, low_power_peak=Peak(x=i, y=1, prominence=1.0))
        for i in range(len(frequencies))
    ]
    real_postprocess = producer.postprocess

    def postprocess(backend: Any, exec_id: str, run_result: RunResult, qid: str) -> Any:
        if qid == sibling_error_qid:
            raise RuntimeError(f"distribution failed for qid={qid}")
        return real_postprocess(backend, exec_id, run_result, qid)

    with ExitStack() as stack:
        # Execution bookkeeping and parameter files are outside this contract.
        stack.enter_context(
            patch.object(executor, "_update_execution", side_effect=lambda service: service)
        )
        stack.enter_context(patch.object(BackendSaver, "_update_backend_params"))
        stack.enter_context(patch.object(producer, "prepare_run"))
        stack.enter_context(patch.object(producer, "extract_raw_data", return_value=[]))
        stack.enter_context(
            patch.object(producer, "_prepare_analysis_figure", return_value=raw_fig)
        )
        stack.enter_context(patch.object(producer, "postprocess", side_effect=postprocess))
        stack.enter_context(
            patch.object(
                producer,
                "run",
                side_effect=run_error,
                return_value=RunResult(raw_result={"fig": raw_fig}),
            )
        )
        stack.enter_context(
            patch(
                PRODUCER_MODULE + "estimate_resonator_frequency_from_figure",
                return_value=(resonances, [], frequencies),
            )
        )
        stack.enter_context(
            patch(PRODUCER_MODULE + "estimate_minimum_usable_power", return_value=-40.0)
        )
        stack.enter_context(patch(PRODUCER_MODULE + "estimate_optimal_powers", return_value=powers))
        stack.enter_context(patch(PRODUCER_MODULE + "create_marked_figure", return_value=raw_fig))
        try:
            _, result = executor.execute(
                cast("Any", producer),
                _backend(),
                "0",
                execution_service=_execution_service(execution_id),
            )
        except Exception:
            return False
    return bool(result.success)


def _run_consumer(qid: str = "1") -> MagicMock:
    """Resolve the consumer inputs from the database and run it up to the Qubex calls.

    The consumer keeps its default ``readout_grouping``, so it reads the candidates in
    one call per Qubex qubit subgroup.
    """
    consumer = CheckQubitFrequencyMapping()
    consumer.input_parameters = copy.deepcopy(consumer.input_parameters)
    consumer.run_parameters = copy.deepcopy(consumer.run_parameters)
    consumer.run_parameters["frequency_range"].value = (4.0, 4.5, 0.005)
    backend = _backend()
    consumer.preprocess(backend, qid)
    exp = MagicMock()
    exp.ctx.experiment_system.get_mux_by_qubit.return_value = SimpleNamespace(
        resonators=tuple(
            SimpleNamespace(label=f"RQ0{i}", is_valid=True) for i in range(len(MUX_QIDS))
        )
    )
    exp.ctx.resolve_qubit_label.side_effect = lambda label: "Q" + label[2:]
    exp.util = ExperimentUtil
    helper = MagicMock(return_value=SimpleNamespace(data={}, figures={}))
    with (
        patch.object(consumer, "get_experiment", return_value=exp),
        patch.object(consumer, "get_qubit_label", return_value=f"Q0{qid}"),
        patch(CONSUMER_MODULE + "load_multiplexed_readout_qubit_spectroscopy", return_value=helper),
    ):
        consumer.run(backend, qid)
    return helper


def _read_frequencies(helper: MagicMock) -> list[float]:
    """Return the candidate frequencies of every helper call in slot order."""
    called: dict[str, float] = {}
    for call in helper.call_args_list:
        called.update(call.kwargs["readout_frequencies"])
    return [called[slot] for slot in sorted(called)]


def _history(execution_id: str) -> dict[str, str]:
    return {
        doc.qid: doc.status
        for doc in TaskResultHistoryDocument.find(
            {"project_id": PROJECT_ID, "execution_id": execution_id}
        ).run()
    }


def test_latest_successful_detection_feeds_the_consumer(chip_qubits, tmp_path) -> None:
    """Map with the candidates that the latest complete detection-only run persisted."""
    assert _run_producer(tmp_path, "exec-A", FREQUENCIES_A, POWERS)

    helper = _run_consumer("1")

    assert _history("exec-A") == dict.fromkeys(MUX_QIDS, "completed")
    assert [list(call.kwargs["readout_frequencies"]) for call in helper.call_args_list] == [
        ["RQ00", "RQ03"],
        ["RQ01", "RQ02"],
    ]
    assert all(call.kwargs["readout_grouping"] == "subgroups" for call in helper.call_args_list)
    assert _read_frequencies(helper) == FREQUENCIES_A


def test_newer_successful_detection_replaces_the_older_set(chip_qubits, tmp_path) -> None:
    """Use the newer run's candidates once it completes for the whole MUX."""
    assert _run_producer(tmp_path, "exec-A", FREQUENCIES_A, POWERS)
    assert _run_producer(tmp_path, "exec-B", FREQUENCIES_B, POWERS)

    helper = _run_consumer("2")

    assert _read_frequencies(helper) == FREQUENCIES_B


@pytest.mark.parametrize(
    ("frequencies", "powers"),
    [
        ([10.22, 10.30, 10.37, 10.44], [-34.0, float("nan"), -28.0, -26.0]),
        ([], []),
    ],
)
@pytest.mark.parametrize("consumer_qid", ["0", "1"])
def test_failed_newer_detection_blocks_the_older_candidate_set(
    chip_qubits, tmp_path, frequencies, powers, consumer_qid
) -> None:
    """Reject success A after a failed detection B instead of silently mapping from A."""
    assert _run_producer(tmp_path, "exec-A", FREQUENCIES_A, POWERS)
    assert not _run_producer(tmp_path, "exec-B", frequencies, powers)

    # B failed on the representative and fanned out nothing; A's values remain.
    assert _history("exec-B") == {"0": "failed"}
    stored = QubitDocument.find_one({"project_id": PROJECT_ID, "qid": consumer_qid}).run()
    assert stored is not None
    assert stored.data["resonator_candidate_0_frequency"]["execution_id"] == "exec-A"

    with pytest.raises(ValueError, match="newer CheckResonatorSpectroscopy attempt"):
        _run_consumer(consumer_qid)


def test_measurement_failure_of_newer_attempt_blocks_the_older_set(chip_qubits, tmp_path) -> None:
    """Reject the older set when the newer attempt failed before postprocessing."""
    assert _run_producer(tmp_path, "exec-A", FREQUENCIES_A, POWERS)
    assert not _run_producer(
        tmp_path, "exec-B", FREQUENCIES_B, POWERS, run_error=RuntimeError("hardware")
    )

    with pytest.raises(ValueError, match="exec-B"):
        _run_consumer("3")


def test_partial_newer_attempt_is_not_used_by_any_qid(chip_qubits, tmp_path) -> None:
    """Reject a partial attempt B for every qid, including qids whose B values were stored."""
    assert _run_producer(tmp_path, "exec-A", FREQUENCIES_A, POWERS)
    assert _run_producer(tmp_path, "exec-B", FREQUENCIES_B, POWERS, sibling_error_qid="2")

    assert _history("exec-B") == {
        "0": "completed",
        "1": "completed",
        "2": "failed",
        "3": "completed",
    }
    for qid in MUX_QIDS:
        # qid 2 still holds A's values, which B superseded; the others hold B's.
        expected = "newer CheckResonatorSpectroscopy attempt" if qid == "2" else "failed for qid=2"
        with pytest.raises(ValueError, match=expected):
            _run_consumer(qid)


DRIVE_FREQUENCIES = [4.0, 4.1, 4.2, 4.3]
DRIVE_POWERS = [-20.0, -10.0]


def _mapping_payload() -> Any:
    """Return a well-formed run payload whose candidates carry flat phase maps."""
    from qdash.workflow.calibtasks.qubex.cw.check_qubit_frequency_mapping import (
        FrequencyMappingRunPayload,
        ResonatorCandidate,
        plan_readout_groups,
    )

    slots = [f"RQ0{i}" for i in range(len(FREQUENCIES_A))]
    amplitudes = [10 ** (power / 20) for power in POWERS]
    # One multiplexed acquisition keeps the payload to one helper result.
    readouts = plan_readout_groups(
        [ResonatorCandidate(i, FREQUENCIES_A[i], amplitudes[i]) for i in range(len(slots))], slots
    )
    assert {readout.readout_group for readout in readouts} == {0}
    zs = [[0.0] * len(DRIVE_FREQUENCIES) for _ in DRIVE_POWERS]
    data = {
        "target": "Q01",
        "readout_labels": slots,
        "frequency_range": DRIVE_FREQUENCIES,
        "power_range": DRIVE_POWERS,
        "readout_grouping": "multiplexed",
        "readout_groups": [slots],
        "candidates": {
            slot: {
                "readout_label": slot,
                "candidate_index": i,
                "readout_group_index": 0,
                "readout_frequency": FREQUENCIES_A[i],
                "readout_amplitude": amplitudes[i],
                "frequency_range": DRIVE_FREQUENCIES,
                "power_range": DRIVE_POWERS,
                "phases": zs,
            }
            for i, slot in enumerate(slots)
        },
    }
    return FrequencyMappingRunPayload(
        target="Q01",
        readouts=readouts,
        results=(SimpleNamespace(data=data),),
        frequency_range=DRIVE_FREQUENCIES,
        power_range=DRIVE_POWERS,
        readout_grouping="multiplexed",
    )


def _fake_analysis(moments: dict[str, float]) -> Any:
    def estimate(fig: Any, *_args: Any, **_kwargs: Any) -> Any:
        moment = moments.get(fig.layout.meta["readout_label"])
        f01 = (
            None
            if moment is None
            else SimpleNamespace(frequency=4.2, repr_db=-15.0, quality_level=4, moment=moment)
        )
        return go.Figure(fig), SimpleNamespace(f01=f01, f12=None, anharmonicity=None)

    return estimate


def _run_mapping_through_executor(tmp_path: Path, moments: dict[str, float]) -> list[Any]:
    """Execute the mapping task with the real executor and history; return saved figures."""
    saved: list[Any] = []

    def save_figures(figures: list[Any], *_args: Any, **_kwargs: Any) -> Any:
        saved.extend(figures)
        return (
            [f"/fig/mapping_{i}.png" for i in range(len(figures))],
            [f"/fig/mapping_{i}.json" for i in range(len(figures))],
        )

    data_saver = MagicMock()
    data_saver.save_figures.side_effect = save_figures
    executor = TaskExecutor(
        state_manager=TaskStateManager(qids=MUX_QIDS),
        calib_dir=str(tmp_path),
        execution_id="exec-map",
        task_manager_id="tm-exec-map",
        result_processor=TaskResultProcessor(),
        history_recorder=TaskHistoryRecorder(chip_repo=MagicMock(), chip_history_repo=MagicMock()),
        data_saver=data_saver,
        mux_mapping=MuxMapping.legacy(),
    )
    task = CheckQubitFrequencyMapping()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task.run_parameters["frequency_range"].value = (4.0, 4.35, 0.1)
    task.run_parameters["power_range"].value = (-20, 0, 10)
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(executor, "_update_execution", side_effect=lambda service: service)
        )
        stack.enter_context(patch.object(executor, "_validate_effective_inputs"))
        stack.enter_context(patch.object(BackendSaver, "_update_backend_params"))
        stack.enter_context(patch.object(task, "preprocess", return_value=None))
        stack.enter_context(patch.object(task, "prepare_run"))
        stack.enter_context(patch.object(task, "extract_raw_data", return_value=[]))
        stack.enter_context(
            patch.object(task, "run", return_value=RunResult(raw_result=_mapping_payload()))
        )
        stack.enter_context(
            patch(
                CONSUMER_MODULE + "estimate_and_mark_qubit_figure",
                side_effect=_fake_analysis(moments),
            )
        )
        # A rejected mapping raises after its artifacts and history are recorded.
        stack.enter_context(suppress(ValueError))
        executor.execute(
            cast("Any", task), _backend(), "1", execution_service=_execution_service("exec-map")
        )
    return saved


def _mapping_history() -> TaskResultHistoryDocument:
    doc = TaskResultHistoryDocument.find_one(
        {"project_id": PROJECT_ID, "name": "CheckQubitFrequencyMapping"}
    ).run()
    assert doc is not None
    return doc


def _persisted_meta(saved: list[Any], index: int = 0) -> dict[str, Any]:
    """Read one saved figure's metadata back from its JSON, as an evaluation reads it."""
    import json

    meta: dict[str, Any] = json.loads(saved[index].to_json())["layout"]["meta"]
    return meta


def _persisted_evidence(saved: list[Any]) -> dict[str, Any]:
    """Read the evidence back the way an evaluation reads the first JSON figure."""
    evidence: dict[str, Any] = _persisted_meta(saved)["qubit_frequency_mapping"]
    return evidence


def test_selected_mapping_persists_reviewable_evidence(chip_qubits, tmp_path) -> None:
    """Save the selected candidate's figure first, with the evidence, then the summary."""
    saved = _run_mapping_through_executor(tmp_path, {"RQ02": 12000.0, "RQ00": 2000.0})

    doc = _mapping_history()
    assert doc.status == "completed"
    assert doc.figure_path[0] == "/fig/mapping_0.png"
    assert doc.json_figure_path[0] == "/fig/mapping_0.json"
    assert len(doc.figure_path) == 1 + 2 * len(MUX_QIDS)
    assert doc.output_parameters["resonator_candidate_index"]["value"] == 2
    evidence = _persisted_evidence(saved)
    assert evidence["outcome"] == "selected"
    assert evidence["score_ratio"] == pytest.approx(6.0)
    assert evidence["proposal"]["published"] is True
    assert [row["moment"] for row in evidence["candidates"]] == [2000.0, None, 12000.0, None]
    assert [row["readout_frequency"] for row in evidence["candidates"]] == FREQUENCIES_A
    first = _persisted_meta(saved, 0)
    assert first["qubit_frequency_mapping_figure"] == "selected"
    assert first["qdash_figure_role"] == "marked"
    assert first["readout_label"] == "RQ02"
    assert first["candidate_index"] == 2
    summary = _persisted_meta(saved, 1)
    assert summary["qubit_frequency_mapping_figure"] == "summary"
    assert summary["qubit_frequency_mapping"] == evidence


def test_ambiguous_mapping_persists_evidence_without_calibration(chip_qubits, tmp_path) -> None:
    """Fail an ambiguous mapping with a one-line message and the full evidence saved."""
    saved = _run_mapping_through_executor(tmp_path, {"RQ02": 12000.0, "RQ01": 9000.0})

    doc = _mapping_history()
    assert doc.status == "failed"
    assert doc.output_parameters == {}
    assert doc.figure_path[0] == "/fig/mapping_0.png"
    # The evaluation context keeps only the first line of the task message.
    assert "\n" not in doc.message
    assert "Ambiguous qubit response" in doc.message
    for index, frequency in enumerate(FREQUENCIES_A):
        assert f"candidate {index} (RQ0{index}, {frequency:.6f} GHz" in doc.message
    assert "moment=12000" in doc.message and "moment=9000" in doc.message
    stored = QubitDocument.find_one({"project_id": PROJECT_ID, "qid": "1"}).run()
    assert stored is not None
    assert "resonator_frequency" not in stored.data
    evidence = _persisted_evidence(saved)
    assert evidence["outcome"] == "rejected"
    assert evidence["runner_up"]["candidate_index"] == 1
    assert evidence["proposal"]["resonator_candidate_index"] == 2
    assert evidence["proposal"]["published"] is False
    assert _persisted_meta(saved, 0)["qubit_frequency_mapping_figure"] == "summary"
    assert all(
        _persisted_meta(saved, index).get("qubit_frequency_mapping_figure") != "selected"
        for index in range(len(saved))
    )
