from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock, patch

import pytest

from qdash.datamodel.task import (
    OutputParameterSpec,
    ParameterModel,
)
from qdash.workflow.engine.backend.fake import FakeBackend
from qdash.workflow.engine.backend.persistence import PersistencePolicy
from qdash.workflow.engine.task.backend_saver import BackendSaver, resolve_publish_targets

if TYPE_CHECKING:
    from qdash.workflow.engine.execution.service import ExecutionService
    from qdash.workflow.engine.task.types import TaskProtocol


def test_save_mux_qid_syncs_backend_params_for_distributed_outputs() -> None:
    output_parameters = {
        "readout_frequency": ParameterModel(value=6.123, unit="GHz"),
        "readout_amplitude": ParameterModel(value=0.017, unit="a.u."),
    }
    state_manager = MagicMock()
    task_model = SimpleNamespace(output_parameters=output_parameters)
    state_manager.get_task.return_value = task_model
    execution_service = cast(
        "ExecutionService",
        SimpleNamespace(
            chip_id="chip-1",
            project_id="proj-1",
        ),
    )
    task = MagicMock()
    task.backend = "qubex"
    task.get_name.return_value = "CheckResonatorSpectroscopy"
    task.get_task_type.return_value = "qubit"
    backend = MagicMock()
    backend.persistence_policy = PersistencePolicy.QUBEX_COMPATIBLE
    updater = MagicMock()

    saver = BackendSaver(
        state_manager=state_manager,
        username="alice",
        calib_dir="/tmp/calib",
        task_manager_id="tm-1",
    )

    with (
        patch("qdash.repository.MongoQubitCalibrationRepository") as repo_cls,
        patch("qdash.workflow.engine.task.backend_saver.get_params_updater", return_value=updater),
    ):
        repo_cls.return_value.get_calibration_data_for_update.return_value = {
            "readout_frequency": {"value": 5.987, "unit": "GHz"}
        }
        saver.save_mux_qid(task, execution_service, "1", backend)

    repo_cls.return_value.update_calib_data.assert_called_once_with(
        username="alice",
        qid="1",
        chip_id="chip-1",
        output_parameters=output_parameters,
        project_id="proj-1",
    )
    updater.update.assert_called_once_with("1", output_parameters)
    assert task_model.output_parameters["readout_frequency"]["value"] == 6.123
    assert task_model.output_parameters["readout_frequency"]["previous_database_value"] == 5.987
    assert task_model.output_parameters["readout_amplitude"]["previous_database_value"] is None
    assert task_model.output_parameters["readout_amplitude"]["database_updated"] is True


def test_save_calibration_stages_outputs_when_persistence_is_disabled() -> None:
    output_parameters = {
        "drive_amplitude": ParameterModel(value=0.12, unit="a.u."),
    }
    state_manager = MagicMock()
    task_model = SimpleNamespace(output_parameters=output_parameters)
    state_manager.get_task.return_value = task_model
    execution_service = cast(
        "ExecutionService",
        SimpleNamespace(
            execution_id="exec-1",
            chip_id="chip-1",
            project_id="proj-1",
        ),
    )
    task = MagicMock()
    task.backend = "qubex"
    task.get_name.return_value = "CheckQubitSpectroscopy"
    task.get_task_type.return_value = "qubit"
    task.is_qubit_task.return_value = True
    task.is_coupling_task.return_value = False
    backend = MagicMock()
    backend.persistence_policy = PersistencePolicy.QUBEX_COMPATIBLE
    backend.name = "qubex"
    updater = MagicMock()

    saver = BackendSaver(
        state_manager=state_manager,
        username="alice",
        calib_dir="/tmp/calib",
        task_manager_id="tm-1",
        update_calibration_parameters=False,
    )

    with (
        patch("qdash.repository.MongoQubitCalibrationRepository") as qubit_repo_cls,
        patch("qdash.repository.MongoCouplingCalibrationRepository") as coupling_repo_cls,
        patch(
            "qdash.workflow.engine.task.backend_saver.get_params_updater",
            return_value=updater,
        ),
    ):
        saver.save(task, execution_service, "1", backend, success=True)

    backend.update_note.assert_called_once()
    qubit_repo_cls.return_value.update_calib_data.assert_not_called()
    coupling_repo_cls.return_value.update_calib_data.assert_not_called()
    updater.update.assert_not_called()
    assert task_model.output_parameters["drive_amplitude"]["value"] == 0.12
    assert task_model.output_parameters["drive_amplitude"]["database_updated"] is False


def test_save_mux_qid_marks_outputs_when_persistence_is_disabled() -> None:
    output_parameters = {
        "readout_frequency": ParameterModel(value=6.123, unit="GHz"),
    }
    task_model = SimpleNamespace(output_parameters=output_parameters)
    state_manager = MagicMock()
    state_manager.get_task.return_value = task_model
    execution_service = cast(
        "ExecutionService",
        SimpleNamespace(chip_id="chip-1", project_id="proj-1"),
    )
    task = MagicMock()
    task.backend = "qubex"
    task.get_name.return_value = "CheckResonatorSpectroscopy"
    task.get_task_type.return_value = "qubit"
    backend = MagicMock()
    backend.persistence_policy = PersistencePolicy.QUBEX_COMPATIBLE

    saver = BackendSaver(
        state_manager=state_manager,
        username="alice",
        calib_dir="/tmp/calib",
        task_manager_id="tm-1",
        update_calibration_parameters=False,
    )

    with patch("qdash.repository.MongoQubitCalibrationRepository") as repo_cls:
        saver.save_mux_qid(task, execution_service, "1", backend)

    repo_cls.return_value.update_calib_data.assert_not_called()
    backend.update.assert_not_called()
    assert task_model.output_parameters["readout_frequency"]["value"] == 6.123
    assert task_model.output_parameters["readout_frequency"]["database_updated"] is False


def test_save_calibration_records_previous_database_value_for_persisted_output() -> None:
    output_parameters = {
        "drive_amplitude": ParameterModel(value=0.12, unit="a.u."),
    }
    task_model = SimpleNamespace(output_parameters=output_parameters)
    state_manager = MagicMock()
    state_manager.get_task.return_value = task_model
    execution_service = cast(
        "ExecutionService",
        SimpleNamespace(
            execution_id="exec-1",
            chip_id="chip-1",
            project_id="proj-1",
        ),
    )
    task = MagicMock()
    task.backend = "qubex"
    task.get_name.return_value = "CheckQubitSpectroscopy"
    task.get_task_type.return_value = "qubit"
    task.is_qubit_task.return_value = True
    task.is_coupling_task.return_value = False
    backend = MagicMock()
    backend.persistence_policy = PersistencePolicy.QUBEX_COMPATIBLE
    backend.name = "qubex"

    saver = BackendSaver(
        state_manager=state_manager,
        username="alice",
        calib_dir="/tmp/calib",
        task_manager_id="tm-1",
    )

    with (
        patch("qdash.repository.MongoQubitCalibrationRepository") as qubit_repo_cls,
        patch("qdash.repository.MongoCouplingCalibrationRepository"),
        patch("qdash.workflow.engine.task.backend_saver.get_params_updater", return_value=None),
    ):
        qubit_repo_cls.return_value.get_calibration_data_for_update.return_value = {
            "drive_amplitude": {"value": 0.08, "unit": "a.u."}
        }
        saver.save(task, execution_service, "1", backend, success=True)

    qubit_repo_cls.return_value.update_calib_data.assert_called_once_with(
        username="alice",
        qid="1",
        chip_id="chip-1",
        output_parameters=output_parameters,
        project_id="proj-1",
    )
    assert task_model.output_parameters["drive_amplitude"]["value"] == 0.12
    assert task_model.output_parameters["drive_amplitude"]["previous_database_value"] == 0.08
    assert task_model.output_parameters["drive_amplitude"]["database_updated"] is True


def test_save_calibration_records_previous_database_value_for_coupling() -> None:
    output_parameters = {"coupling_strength": ParameterModel(value=0.03, unit="GHz")}
    task_model = SimpleNamespace(output_parameters=output_parameters)
    state_manager = MagicMock()
    state_manager.get_task.return_value = task_model
    execution_service = cast(
        "ExecutionService",
        SimpleNamespace(execution_id="exec-1", chip_id="chip-1", project_id="proj-1"),
    )
    task = MagicMock()
    task.backend = "qubex"
    task.get_name.return_value = "CheckCoupling"
    task.get_task_type.return_value = "coupling"
    task.is_qubit_task.return_value = False
    task.is_coupling_task.return_value = True
    backend = MagicMock()
    backend.persistence_policy = PersistencePolicy.QUBEX_COMPATIBLE
    backend.name = "qubex"
    saver = BackendSaver(state_manager, "alice", "/tmp/calib", "tm-1")

    with (
        patch("qdash.repository.MongoQubitCalibrationRepository"),
        patch("qdash.repository.MongoCouplingCalibrationRepository") as coupling_repo_cls,
    ):
        coupling_repo_cls.return_value.get_calibration_data_for_update.return_value = {
            "coupling_strength": {"value": 0.02, "unit": "GHz"}
        }
        saver.save(task, execution_service, "0-1", backend, success=True)

    assert task_model.output_parameters["coupling_strength"]["previous_database_value"] == 0.02
    coupling_repo_cls.return_value.get_calibration_data_for_update.assert_called_once_with(
        username="alice", project_id="proj-1", chip_id="chip-1", qid="0-1"
    )


def test_resolve_publish_targets_defaults_to_output_name() -> None:
    class FrequencyTask:
        output_spec = {
            "fh_frequency": OutputParameterSpec(
                unit="GHz", publish_targets=("fh_frequency", "control_frequency_fh")
            ),
            "r2": OutputParameterSpec(),
        }

    targets = resolve_publish_targets(
        cast("TaskProtocol", FrequencyTask()),
        {"fh_frequency": ParameterModel(value=4.2), "r2": ParameterModel(value=0.9)},
    )

    assert targets == {
        "fh_frequency": ("fh_frequency", "control_frequency_fh"),
        "r2": ("r2",),
    }


def test_save_calibration_publishes_measurement_and_operational_frequency() -> None:
    class FrequencyTask:
        backend = "qubex"
        output_spec = {
            "qubit_frequency": OutputParameterSpec(
                unit="GHz",
                publish_targets=(
                    "qubit_frequency",
                    "control_frequency",
                ),
            )
        }

        @staticmethod
        def get_name() -> str:
            return "CheckChevron"

        @staticmethod
        def get_task_type() -> str:
            return "qubit"

        @staticmethod
        def is_qubit_task() -> bool:
            return True

        @staticmethod
        def is_coupling_task() -> bool:
            return False

    output_parameters = {
        "qubit_frequency": ParameterModel(value=5.2, unit="GHz"),
    }
    task_model = SimpleNamespace(output_parameters=output_parameters)
    state_manager = MagicMock()
    state_manager.get_task.return_value = task_model
    execution_service = cast(
        "ExecutionService",
        SimpleNamespace(execution_id="exec-1", chip_id="chip-1", project_id="proj-1"),
    )
    backend = MagicMock()
    backend.persistence_policy = PersistencePolicy.QUBEX_COMPATIBLE
    backend.name = "qubex"
    updater = MagicMock()
    saver = BackendSaver(state_manager, "alice", "/tmp/calib", "tm-1")

    with (
        patch("qdash.repository.MongoQubitCalibrationRepository") as qubit_repo_cls,
        patch("qdash.repository.MongoCouplingCalibrationRepository"),
        patch(
            "qdash.workflow.engine.task.backend_saver.get_params_updater",
            return_value=updater,
        ),
    ):
        qubit_repo_cls.return_value.get_calibration_data_for_update.return_value = {
            "qubit_frequency": {"value": 5.1},
            "control_frequency": {"value": 5.0},
        }
        saver.save(
            cast("TaskProtocol", FrequencyTask()),
            execution_service,
            "1",
            backend,
            success=True,
        )

    persisted = qubit_repo_cls.return_value.update_calib_data.call_args.kwargs["output_parameters"]
    assert set(persisted) == {"qubit_frequency", "control_frequency"}
    assert persisted["qubit_frequency"]["value"] == 5.2
    assert persisted["control_frequency"]["value"] == 5.2
    updater.update.assert_called_once_with("1", persisted)

    updates = task_model.output_parameters["qubit_frequency"]["database_updates"]
    assert updates == [
        {
            "parameter_name": "qubit_frequency",
            "previous_value": 5.1,
            "updated_value": 5.2,
            "updated": True,
        },
        {
            "parameter_name": "control_frequency",
            "previous_value": 5.0,
            "updated_value": 5.2,
            "updated": True,
        },
    ]


def test_save_persists_fake_task_outputs_like_qubex() -> None:
    """A fake-backend task's outputs reach the calibration database, so the qubex tasks
    that run after it on the fake backend can resolve their inputs."""
    output_parameters = {
        "qubit_frequency": ParameterModel(value=7.15, unit="GHz"),
    }
    state_manager = MagicMock()
    task_model = SimpleNamespace(output_parameters=output_parameters)
    state_manager.get_task.return_value = task_model
    execution_service = cast(
        "ExecutionService",
        SimpleNamespace(execution_id="exec-1", chip_id="chip-1", project_id="proj-1"),
    )
    task = MagicMock()
    task.backend = "fake"
    task.get_name.return_value = "FakeBringUp"
    task.get_task_type.return_value = "qubit"
    task.is_qubit_task.return_value = True
    task.is_coupling_task.return_value = False
    task.__class__.output_spec = {}
    backend = FakeBackend({})
    updater = MagicMock()

    saver = BackendSaver(
        state_manager=state_manager,
        username="alice",
        calib_dir="/tmp/calib",
        task_manager_id="tm-1",
    )

    with (
        patch("qdash.repository.MongoQubitCalibrationRepository") as qubit_repo_cls,
        patch("qdash.repository.MongoCouplingCalibrationRepository"),
        patch(
            "qdash.workflow.engine.task.backend_saver.get_params_updater",
            return_value=updater,
        ),
    ):
        qubit_repo_cls.return_value.get_qubit_data.return_value = {}
        saver.save(task, execution_service, "1", backend, success=True)

    qubit_repo_cls.return_value.update_calib_data.assert_called_once()
    persisted = qubit_repo_cls.return_value.update_calib_data.call_args.kwargs["output_parameters"]
    assert "qubit_frequency" in persisted
    updater.update.assert_called_once()


@pytest.mark.parametrize("success", [False, True])
@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("update", [False, True])
def test_compatible_policy_preserves_note_database_native_order(success, force, update):
    """DB adoption and native validation gates intentionally differ for this policy."""
    task = MagicMock()
    task.backend = "qubex"
    task.get_name.return_value = "CheckRabi"
    task.is_qubit_task.return_value = True
    task.is_coupling_task.return_value = False
    model = SimpleNamespace(output_parameters={"control_amplitude": ParameterModel(value=0.2)})
    state = MagicMock()
    state.get_task.return_value = model
    backend = MagicMock()
    backend.persistence_policy = PersistencePolicy.QUBEX_COMPATIBLE
    events = []
    backend.update_note.side_effect = lambda **_: events.append("note")
    updater = MagicMock()
    updater.update.side_effect = lambda *_: events.append("native")
    execution = cast(
        "ExecutionService",
        SimpleNamespace(chip_id="chip", project_id="project", execution_id="exec"),
    )
    saver = BackendSaver(state, "alice", "/tmp/calib", "tm", force, update)
    with (
        patch("qdash.repository.MongoQubitCalibrationRepository") as repo,
        patch("qdash.repository.MongoCouplingCalibrationRepository"),
        patch("qdash.workflow.engine.task.backend_saver.get_params_updater", return_value=updater),
    ):
        repo.return_value.get_calibration_data_for_update.return_value = {}
        repo.return_value.update_calib_data.side_effect = lambda **_: events.append("database")
        saver.save(task, execution, "0", backend, success)
    expected = ["note"]
    if update:
        expected.append("database")
        if success or force:
            expected.append("native")
    assert events == expected
    assert model.output_parameters["control_amplitude"]["database_updated"] is update


@pytest.mark.parametrize("mux", [False, True])
@pytest.mark.parametrize("policy", [None, "qubex-compatible", MagicMock()])
def test_unknown_policy_fails_before_side_effects(mux, policy):
    backend = MagicMock()
    backend.name = "unknown"
    backend.persistence_policy = policy
    state = MagicMock()
    task = MagicMock()
    task.backend = "qubex"
    saver = BackendSaver(state, "alice", "/tmp/calib", "tm")
    with pytest.raises(ValueError, match="persistence policy"):
        if mux:
            saver.save_mux_qid(task, MagicMock(), "0", backend)
        else:
            saver.save(task, MagicMock(), "0", backend, True)
    state.get_task.assert_not_called()
    backend.update_note.assert_not_called()


def test_mux_requires_backend_for_adoption():
    task = MagicMock()
    task.backend = "qubex"
    state = MagicMock()
    with pytest.raises(ValueError, match="policy is required"):
        BackendSaver(state, "alice", "/tmp/calib", "tm").save_mux_qid(task, MagicMock(), "0")
    state.get_task.assert_not_called()
