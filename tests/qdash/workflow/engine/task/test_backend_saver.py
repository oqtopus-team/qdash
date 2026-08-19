from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock, patch

from qdash.datamodel.task import ParameterModel
from qdash.workflow.engine.task.backend_saver import BackendSaver

if TYPE_CHECKING:
    from qdash.workflow.engine.execution.service import ExecutionService


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
    task.get_name.return_value = "CheckResonatorSpectroscopy"
    task.get_task_type.return_value = "qubit"
    backend = MagicMock()
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


def test_save_qubex_stages_outputs_when_persistence_is_disabled() -> None:
    output_parameters = {
        "drive_amplitude": ParameterModel(value=0.12, unit="a.u."),
    }
    state_manager = MagicMock()
    state_manager.get_task.return_value = SimpleNamespace(output_parameters=output_parameters)
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
    backend.name = "qubex"
    updater = MagicMock()

    saver = BackendSaver(
        state_manager=state_manager,
        username="alice",
        calib_dir="/tmp/calib",
        task_manager_id="tm-1",
        persist_output_parameters=False,
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


def test_save_qubex_records_previous_database_value_for_persisted_output() -> None:
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


def test_save_qubex_records_previous_database_value_for_coupling() -> None:
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
