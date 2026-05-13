from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

from qdash.datamodel.task import ParameterModel
from qdash.workflow.engine.execution.service import ExecutionService
from qdash.workflow.engine.task.backend_saver import BackendSaver


def test_save_mux_qid_syncs_backend_params_for_distributed_outputs() -> None:
    output_parameters = {
        "readout_frequency": ParameterModel(value=6.123, unit="GHz"),
        "readout_amplitude": ParameterModel(value=0.017, unit="a.u."),
    }
    state_manager = MagicMock()
    state_manager.get_task.return_value = SimpleNamespace(output_parameters=output_parameters)
    execution_service = cast(
        ExecutionService,
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
        saver.save_mux_qid(task, execution_service, "1", backend)

    repo_cls.return_value.update_calib_data.assert_called_once_with(
        username="alice",
        qid="1",
        chip_id="chip-1",
        output_parameters=output_parameters,
        project_id="proj-1",
    )
    updater.update.assert_called_once_with("1", output_parameters)
