"""Result processing pipeline for calibration tasks.

This module provides the ResultPipeline class that handles the multi-step
result processing after a task's postprocess phase:

1. Fidelity validation
2. Output parameter processing and storage
3. Figure and raw-data saving
4. R-squared validation (with output parameter rollback on failure)
5. Backend-specific persistence

Extracted from TaskExecutor._process_results to isolate result-processing
concerns from the task execution lifecycle.
"""

import logging
from typing import TYPE_CHECKING

from qdash.workflow.engine.task.result_processor import (
    FidelityValidationError,
    R2ValidationError,
)

if TYPE_CHECKING:
    from qdash.repository import FilesystemCalibDataSaver
    from qdash.workflow.calibtasks.results import PostProcessResult, RunResult
    from qdash.workflow.engine.backend.base import BaseBackend
    from qdash.workflow.engine.execution.service import ExecutionService
    from qdash.workflow.engine.task.backend_saver import BackendSaver
    from qdash.workflow.engine.task.result_processor import TaskResultProcessor
    from qdash.workflow.engine.task.state_manager import TaskStateManager
    from qdash.workflow.engine.task.types import TaskProtocol

logger = logging.getLogger(__name__)


class ResultPipeline:
    """Multi-step result processor for calibration task outputs.

    Parameters
    ----------
    state_manager : TaskStateManager
        Manager for task state
    execution_id : str
        Current execution ID
    result_processor : TaskResultProcessor
        Processor for result validation
    data_saver : FilesystemCalibDataSaver
        Saver for figures and raw data
    backend_saver : BackendSaver
        Backend-specific persistence handler
    """

    def __init__(
        self,
        state_manager: "TaskStateManager",
        execution_id: str,
        result_processor: "TaskResultProcessor",
        data_saver: "FilesystemCalibDataSaver",
        backend_saver: "BackendSaver",
    ) -> None:
        self._state_manager = state_manager
        self._execution_id = execution_id
        self._result_processor = result_processor
        self._data_saver = data_saver
        self._backend_saver = backend_saver

    def process(
        self,
        task: "TaskProtocol",
        execution_service: "ExecutionService",
        postprocess_result: "PostProcessResult",
        qid: str,
        run_result: "RunResult",
        backend: "BaseBackend",
    ) -> bool:
        """Process task results.

        Parameters
        ----------
        task : TaskProtocol
            The task
        execution_service : ExecutionService
            The execution service
        postprocess_result : PostProcessResult
            The postprocess result
        qid : str
            The qubit ID
        run_result : RunResult
            The run result
        backend : BaseBackend
            The backend

        Returns
        -------
        bool
            True if backend updates should be applied
        """
        task_name = task.get_name()
        task_type = task.get_task_type()

        # 1. Validate fidelity
        if postprocess_result.output_parameters:
            try:
                self._result_processor.validate_fidelity(
                    postprocess_result.output_parameters, task_name
                )
            except FidelityValidationError as e:
                raise ValueError(str(e)) from e

        # 2. Process output parameters
        if postprocess_result.output_parameters:
            task_model = self._state_manager.get_task(task_name, task_type, qid)
            task.attach_task_id(task_model.task_id)

            processed_params = self._result_processor.process_output_parameters(
                postprocess_result.output_parameters,
                task_name,
                self._execution_id,
                task_model.task_id,
            )
            self._state_manager.put_output_parameters(task_name, processed_params, task_type, qid)

        # 3. Save figures
        if postprocess_result.figures:
            png_paths, json_paths = self._data_saver.save_figures(
                postprocess_result.figures, task_name, task_type, qid
            )
            self._state_manager.set_figure_paths(task_name, task_type, qid, png_paths, json_paths)

        # 4. Save raw data
        if postprocess_result.raw_data:
            raw_paths = self._data_saver.save_raw_data(
                postprocess_result.raw_data, task_name, task_type, qid
            )
            self._state_manager.set_raw_data_paths(task_name, task_type, qid, raw_paths)

        # 5. Validate R²
        backend_success = True
        r2_error_msg: str | None = None
        if run_result.has_r2() and run_result.r2 is not None:
            r2_value = run_result.r2.get(qid)
            if r2_value is None:
                backend_success = False
            else:
                try:
                    self._result_processor.validate_r2(run_result.r2, qid, task.r2_threshold)
                except R2ValidationError:
                    # Clear output parameters on R² failure
                    if postprocess_result.output_parameters:
                        self._state_manager.clear_output_parameters(task_name, task_type, qid)
                    backend_success = False
                    r2_error_msg = f"{task_name} R² value too low: {r2_value:.4f}"

            if not backend_success and postprocess_result.output_parameters:
                self._state_manager.clear_output_parameters(task_name, task_type, qid)

        # 6. Backend-specific save processing (always runs, even on R² failure)
        self._backend_saver.save(task, execution_service, qid, backend, backend_success)

        # Raise after save so calibration note is updated
        if r2_error_msg is not None:
            raise ValueError(r2_error_msg)

        return backend_success
