"""Backend-specific persistence logic for calibration tasks.

This module provides the BackendSaver class that handles saving task results
to MongoDB and updating backend parameters (e.g. Qubex YAML files).

Extracted from TaskExecutor to isolate backend-specific persistence concerns.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import TYPE_CHECKING, Any, cast

from qdash.workflow.engine.params_updater import get_params_updater

if TYPE_CHECKING:
    from qdash.datamodel.task import TaskResultOutputParameter
    from qdash.workflow.engine.backend.base import BaseBackend
    from qdash.workflow.engine.execution.service import ExecutionService
    from qdash.workflow.engine.task.state_manager import TaskStateManager
    from qdash.workflow.engine.task.types import TaskProtocol

logger = logging.getLogger(__name__)


class BackendSaver:
    """Handles backend-specific persistence for calibration task results.

    Responsibilities:
    - Dispatching to the correct backend saver (qubex, fake, etc.)
    - Saving calibration data to MongoDB (qubit and coupling repositories)
    - Updating calibration notes on the backend
    - Updating backend parameter files (e.g. Qubex YAML)
    - Saving MUX qubit results to the database

    Parameters
    ----------
    state_manager : TaskStateManager
        Manager for task state (used to retrieve output parameters)
    username : str
        Current username
    calib_dir : str
        Calibration data directory
    task_manager_id : str
        The unique TaskManager ID (used for note files)
    force_update_params : bool, default=False
        Whether to update backend parameters when R² validation fails
    persist_output_parameters : bool, default=True
        Whether to persist output parameters to the database and backend
    """

    def __init__(
        self,
        state_manager: TaskStateManager,
        username: str,
        calib_dir: str,
        task_manager_id: str,
        force_update_params: bool = False,
        persist_output_parameters: bool = True,
    ) -> None:
        self._state_manager = state_manager
        self._username = username
        self._calib_dir = calib_dir
        self._task_manager_id = task_manager_id
        self._force_update_params = force_update_params
        self._persist_output_parameters = persist_output_parameters

    def save(
        self,
        task: TaskProtocol,
        execution_service: ExecutionService,
        qid: str,
        backend: BaseBackend,
        success: bool,
    ) -> None:
        """Dispatch to the correct backend-specific saver.

        Parameters
        ----------
        task : TaskProtocol
            The task
        execution_service : ExecutionService
            The execution service
        qid : str
            The qubit ID
        backend : BaseBackend
            The backend
        success : bool
            Whether backend updates should be applied
        """
        if task.backend == "qubex":
            self._save_qubex(task, execution_service, qid, backend, success)
        elif task.backend == "fake":
            # Simulation metadata save (implement as needed)
            pass

    def save_mux_qid(
        self,
        task: TaskProtocol,
        execution_service: ExecutionService,
        qid: str,
        backend: BaseBackend | None = None,
    ) -> None:
        """Save MUX task results for a single qid to database.

        Parameters
        ----------
        task : TaskProtocol
            The task instance
        execution_service : ExecutionService
            The execution service
        qid : str
            The qubit ID
        backend : BaseBackend | None
            Backend used to sync parameter files for immediate downstream tasks.
        """
        task_name = task.get_name()
        task_type = task.get_task_type()

        # Get output parameters from state_manager (already processed and stored)
        task_model = self._state_manager.get_task(task_name, task_type, qid)
        output_parameters = dict(task_model.output_parameters)

        if not output_parameters or not self._persist_output_parameters:
            return

        from qdash.repository import MongoQubitCalibrationRepository

        qubit_repo = MongoQubitCalibrationRepository()
        previous_data = self._get_previous_calibration_data(qubit_repo, execution_service, qid)
        qubit_repo.update_calib_data(
            username=self._username,
            qid=qid,
            chip_id=execution_service.chip_id,
            output_parameters=output_parameters,
            project_id=execution_service.project_id,
        )
        # Note: calib_data is already updated by put_output_parameters
        if backend is not None:
            self._update_backend_params(backend, execution_service, qid, output_parameters)
        self._attach_previous_database_values(task_model, output_parameters, previous_data)

    def _save_qubex(
        self,
        task: TaskProtocol,
        execution_service: ExecutionService,
        qid: str,
        backend: BaseBackend,
        success: bool,
    ) -> None:
        """Qubex-specific save processing.

        Parameters
        ----------
        task : TaskProtocol
            The task
        execution_service : ExecutionService
            The execution service
        qid : str
            The qubit ID
        backend : BaseBackend
            The backend
        success : bool
            Whether backend updates should be applied
        """
        from qdash.repository import (
            MongoCouplingCalibrationRepository,
            MongoQubitCalibrationRepository,
        )

        task_name = task.get_name()
        task_type = task.get_task_type()

        # Get output parameters
        task_model = self._state_manager.get_task(task_name, task_type, qid)
        output_parameters = dict(task_model.output_parameters)

        # Get repositories
        qubit_repo = MongoQubitCalibrationRepository()
        coupling_repo = MongoCouplingCalibrationRepository()

        # Always update calibration note regardless of success/failure
        if backend.name == "qubex":
            note_qid = qid if task.is_qubit_task() or task.is_coupling_task() else None
            backend.update_note(
                username=self._username,
                chip_id=execution_service.chip_id,
                calib_dir=self._calib_dir,
                execution_id=execution_service.execution_id,
                task_manager_id=self._task_manager_id,
                project_id=execution_service.project_id,
                qid=note_qid,
            )

        if not self._persist_output_parameters:
            logger.info(
                "Staging output parameters for %s without calibration/backend write-back",
                task_name,
            )
            return

        # Save to the authoritative calibration database only when persistence is enabled.
        if output_parameters:
            if task.is_qubit_task():
                previous_data = self._get_previous_calibration_data(
                    qubit_repo, execution_service, qid
                )
                qubit_repo.update_calib_data(
                    username=self._username,
                    qid=qid,
                    chip_id=execution_service.chip_id,
                    output_parameters=output_parameters,
                    project_id=execution_service.project_id,
                )
                self._attach_previous_database_values(task_model, output_parameters, previous_data)
            elif task.is_coupling_task():
                previous_data = self._get_previous_calibration_data(
                    coupling_repo, execution_service, qid
                )
                coupling_repo.update_calib_data(
                    username=self._username,
                    qid=qid,
                    chip_id=execution_service.chip_id,
                    output_parameters=output_parameters,
                    project_id=execution_service.project_id,
                )
                self._attach_previous_database_values(task_model, output_parameters, previous_data)

        # Update backend params on success, or when force_update_params is enabled
        if not success and not self._force_update_params:
            logger.info(
                "Skipping backend parameter updates for %s due to failed R² validation",
                task_name,
            )
            return

        if output_parameters and task.is_qubit_task():
            if not success and self._force_update_params:
                logger.info(
                    "Force-updating backend params for %s despite failed R² validation",
                    task_name,
                )
            self._update_backend_params(backend, execution_service, qid, output_parameters)

    def _update_backend_params(
        self,
        backend: BaseBackend,
        execution_service: ExecutionService,
        qid: str,
        output_parameters: dict[str, Any],
    ) -> None:
        """Update backend parameters using the params updater.

        Parameters
        ----------
        backend : BaseBackend
            The backend
        execution_service : ExecutionService
            The execution service
        qid : str
            The qubit ID
        output_parameters : dict[str, Any]
            Output parameters to update
        """
        updater = get_params_updater(backend, execution_service.chip_id)
        if updater is None:
            return
        try:
            updater.update(qid, output_parameters)
        except Exception as exc:
            logger.warning("Failed to update backend params for qid=%s: %s", qid, exc)

    @staticmethod
    def _attach_previous_database_values(
        task_model: Any,
        output_parameters: dict[str, Any],
        previous_data: dict[str, Any],
    ) -> None:
        """Add pre-update database values to the history-facing task result."""
        compared_parameters: dict[str, TaskResultOutputParameter] = {}
        for name, parameter in output_parameters.items():
            if hasattr(parameter, "model_dump"):
                current = parameter.model_dump()
            elif isinstance(parameter, dict):
                current = deepcopy(parameter)
            else:
                current = {"value": deepcopy(parameter)}

            previous = previous_data.get(name)
            previous_value = previous.get("value") if isinstance(previous, dict) else previous
            current["previous_database_value"] = deepcopy(previous_value)
            current["database_updated"] = True
            compared_parameters[name] = current

        task_model.output_parameters = compared_parameters

    def _get_previous_calibration_data(
        self,
        repository: Any,
        execution_service: ExecutionService,
        qid: str,
    ) -> dict[str, Any]:
        """Load pre-update calibration data for project-scoped and legacy executions."""
        return cast(
            "dict[str, Any]",
            repository.get_calibration_data_for_update(
                username=self._username,
                project_id=execution_service.project_id,
                chip_id=execution_service.chip_id,
                qid=qid,
            ),
        )
