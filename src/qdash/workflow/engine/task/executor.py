"""TaskExecutor for executing calibration tasks.

This module provides the TaskExecutor class that handles the execution
of calibration tasks including preprocessing, running, and postprocessing.

The TaskExecutor is responsible for the complete task execution lifecycle:
- Task state management via TaskStateManager
- Result validation via TaskResultProcessor
- History recording via TaskHistoryRecorder
- Backend-specific save processing
"""

import logging
from typing import TYPE_CHECKING, Any

from qdash.repository import FilesystemCalibDataSaver
from qdash.workflow.calibtasks.results import PostProcessResult, PreProcessResult, RunResult
from qdash.workflow.engine.task.backend_saver import BackendSaver
from qdash.workflow.engine.task.history_recorder import TaskHistoryRecorder
from qdash.workflow.engine.task.mux_distributor import MuxDistributor
from qdash.workflow.engine.task.result_processor import (
    FidelityValidationError,
    R2ValidationError,
    TaskResultProcessor,
)
from qdash.workflow.engine.task.state_manager import TaskStateManager
from qdash.workflow.engine.task.types import (
    BackendProtocol,
    TaskExecutionError,
    TaskExecutionResult,
    TaskProtocol,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.base import BaseBackend
    from qdash.workflow.engine.execution.service import ExecutionService


class TaskExecutor:
    """Executor for calibration tasks.

    This class handles the complete task execution lifecycle:
    - Task lifecycle (start, preprocess, run, postprocess, end)
    - Figure and raw data saving
    - R² and fidelity validation
    - State updates via TaskStateManager
    - History recording via TaskHistoryRecorder
    - Backend-specific save processing

    Attributes
    ----------
    state_manager : TaskStateManager
        Manager for task state
    result_processor : TaskResultProcessor
        Processor for result validation
    history_recorder : TaskHistoryRecorder
        Recorder for task history
    data_saver : FilesystemCalibDataSaver
        Saver for figures and raw data
    execution_id : str
        Current execution ID
    username : str
        Current username
    calib_dir : str
        Calibration data directory

    """

    def __init__(
        self,
        state_manager: TaskStateManager,
        calib_dir: str,
        execution_id: str,
        task_manager_id: str,
        username: str = "admin",
        result_processor: TaskResultProcessor | None = None,
        history_recorder: TaskHistoryRecorder | None = None,
        data_saver: FilesystemCalibDataSaver | None = None,
    ) -> None:
        self.state_manager = state_manager
        self.execution_id = execution_id
        self.task_manager_id = task_manager_id
        self.username = username
        self.calib_dir = calib_dir
        self.result_processor = result_processor or TaskResultProcessor()
        self.history_recorder = history_recorder or TaskHistoryRecorder()
        self.data_saver = data_saver or FilesystemCalibDataSaver(calib_dir)
        self._backend_saver = BackendSaver(
            state_manager=state_manager,
            username=username,
            calib_dir=calib_dir,
            task_manager_id=task_manager_id,
        )
        self._mux_distributor = MuxDistributor(
            state_manager=state_manager,
            execution_id=execution_id,
            result_processor=self.result_processor,
            data_saver=self.data_saver,
            history_recorder=self.history_recorder,
            backend_saver=self._backend_saver,
        )

    def execute_task(
        self,
        task: TaskProtocol,
        backend: "BaseBackend",
        qid: str,
    ) -> dict[str, Any]:
        """Execute a task without ExecutionService (for testing)."""
        _, result = self.execute(task=task, backend=backend, qid=qid)
        return {
            "task_name": result.task_name,
            "task_type": result.task_type,
            "qid": result.qid,
            "success": result.success,
            "message": result.message,
            "output_parameters": result.output_parameters,
            "r2": result.r2,
        }

    def _run_preprocess(
        self,
        task: TaskProtocol,
        backend: BackendProtocol,
        qid: str,
    ) -> PreProcessResult | None:
        """Run task preprocessing, returning None on failure."""
        try:
            return task.preprocess(backend, qid)
        except Exception as e:
            logger.warning(f"Preprocess failed for {task.get_name()}: {e}")
            return None

    def _run_task(
        self,
        task: TaskProtocol,
        backend: BackendProtocol,
        qid: str,
    ) -> RunResult | None:
        """Run the main task logic."""
        return task.run(backend, qid)

    def _run_postprocess(
        self,
        task: TaskProtocol,
        backend: BackendProtocol,
        run_result: RunResult,
        qid: str,
    ) -> PostProcessResult:
        """Run task postprocessing."""
        return task.postprocess(backend, self.execution_id, run_result, qid)

    def _save_artifacts(
        self,
        postprocess_result: PostProcessResult,
        task_name: str,
        task_type: str,
        qid: str,
    ) -> None:
        """Save figures and raw data from postprocess result."""
        # Save figures
        if postprocess_result.figures:
            png_paths, json_paths = self.data_saver.save_figures(
                postprocess_result.figures, task_name, task_type, qid
            )
            self.state_manager.set_figure_paths(task_name, task_type, qid, png_paths, json_paths)

        # Save raw data
        if postprocess_result.raw_data:
            raw_paths = self.data_saver.save_raw_data(
                postprocess_result.raw_data, task_name, task_type, qid
            )
            self.state_manager.set_raw_data_paths(task_name, task_type, qid, raw_paths)

    def _complete_task(
        self,
        task_name: str,
        task_type: str,
        qid: str,
        message: str,
    ) -> None:
        """Mark task as completed."""
        self.state_manager.update_task_status_to_completed(task_name, message, task_type, qid)

    def _fail_task(
        self,
        task_name: str,
        task_type: str,
        qid: str,
        message: str,
    ) -> None:
        """Mark task as failed."""
        self.state_manager.update_task_status_to_failed(task_name, message, task_type, qid)

    def execute(
        self,
        task: TaskProtocol,
        backend: "BaseBackend",
        qid: str,
        execution_service: "ExecutionService | None" = None,
    ) -> tuple["ExecutionService | None", TaskExecutionResult]:
        """Execute a task with full lifecycle management.

        This is the single entry point for task execution. When execution_service
        is None, history recording, execution updates, backend saves, and MUX
        distribution are skipped (useful for testing).

        Parameters
        ----------
        task : TaskProtocol
            The task to execute
        backend : BaseBackend
            The backend to use
        qid : str
            The qubit ID
        execution_service : ExecutionService | None
            The execution service (None for test-only mode)

        Returns
        -------
        tuple[ExecutionService | None, TaskExecutionResult]
            Updated execution service and task execution result
        """
        task_name = task.get_name()
        task_type = task.get_task_type()

        result = TaskExecutionResult(
            task_name=task_name,
            task_type=task_type,
            qid=qid,
        )

        try:
            # 0. Ensure task exists
            self.state_manager.ensure_task_exists(task_name, task_type, qid)

            # 1. Start task
            self.state_manager.start_task(task_name, task_type, qid)

            # Record run_parameters (experiment configuration used)
            run_params = {k: v.model_dump() for k, v in task.run_parameters.items()}
            if run_params:
                self.state_manager.put_run_parameters(task_name, run_params, task_type, qid)

            # Record task start to history (production only)
            if execution_service is not None:
                executed_task = self.state_manager.get_task(task_name, task_type, qid)
                self.history_recorder.record_task_result(
                    executed_task, execution_service.to_datamodel()
                )
                execution_service = self._update_execution(execution_service)

            # 2. Preprocess
            preprocess_result = self._run_preprocess(task, backend, qid)
            if preprocess_result:
                self.state_manager.put_input_parameters(
                    task_name, preprocess_result.input_parameters, task_type, qid
                )
                if execution_service is not None:
                    execution_service = self._update_execution(execution_service)

            # 3. Run
            run_result = self._run_task(task, backend, qid)
            result.r2 = run_result.r2 if run_result else None

            if run_result is None:
                self._complete_task(task_name, task_type, qid, "No run result")
                result.success = True
                result.message = "Completed without run result"
                return execution_service, result

            # 4. Postprocess
            postprocess_result = self._run_postprocess(task, backend, run_result, qid)

            if postprocess_result:
                # 5a. Validate fidelity
                if postprocess_result.output_parameters:
                    try:
                        self.result_processor.validate_fidelity(
                            postprocess_result.output_parameters, task_name
                        )
                    except FidelityValidationError as e:
                        raise ValueError(str(e)) from e

                # 5b. Process output parameters
                if postprocess_result.output_parameters:
                    task_model = self.state_manager.get_task(task_name, task_type, qid)
                    task.attach_task_id(task_model.task_id)
                    processed_params = self.result_processor.process_output_parameters(
                        postprocess_result.output_parameters,
                        task_name,
                        self.execution_id,
                        task_model.task_id,
                    )
                    self.state_manager.put_output_parameters(
                        task_name, processed_params, task_type, qid
                    )

                # 5c. Save figures and raw data
                self._save_artifacts(postprocess_result, task_name, task_type, qid)

                # 5d. Validate R² (rollback output params on failure)
                backend_success = True
                r2_error_msg: str | None = None
                if run_result.has_r2() and run_result.r2 is not None:
                    r2_value = run_result.r2.get(qid)
                    if r2_value is None:
                        backend_success = False
                    else:
                        try:
                            self.result_processor.validate_r2(run_result.r2, qid, task.r2_threshold)
                        except R2ValidationError:
                            if postprocess_result.output_parameters:
                                self.state_manager.clear_output_parameters(
                                    task_name, task_type, qid
                                )
                            backend_success = False
                            r2_error_msg = f"{task_name} R² value too low: {r2_value:.4f}"

                    if not backend_success and postprocess_result.output_parameters:
                        self.state_manager.clear_output_parameters(task_name, task_type, qid)

                # 5e. Backend save (production only, always runs even on R² failure)
                if execution_service is not None:
                    self._backend_saver.save(task, execution_service, qid, backend, backend_success)

                # Raise after save so calibration note is updated
                if r2_error_msg is not None:
                    raise ValueError(r2_error_msg)

                result.output_parameters = dict(
                    self.state_manager.get_task(task_name, task_type, qid).output_parameters
                )

                # 5.5 MUX distribution (production only)
                if execution_service is not None:
                    is_mux = getattr(task, "is_mux_level", False)
                    logger.debug(
                        "Checking MUX distribution: task=%s, is_mux_level=%s, qid=%s",
                        task_name,
                        is_mux,
                        qid,
                    )
                    if is_mux:
                        logger.debug(
                            "Starting MUX distribution for task=%s, qid=%s", task_name, qid
                        )
                        self._mux_distributor.distribute(
                            task, backend, execution_service, run_result, qid
                        )
                        logger.debug(
                            "Finished MUX distribution for task=%s, qid=%s", task_name, qid
                        )

            # 6. Complete task
            self._complete_task(task_name, task_type, qid, f"{task_name} is completed")

            if execution_service is not None:
                execution_service = self._update_execution(execution_service)
            result.success = True
            result.message = "Completed"

        except (R2ValidationError, FidelityValidationError, ValueError) as e:
            self._fail_task(task_name, task_type, qid, str(e))
            result.message = str(e)
            raise

        except Exception as e:
            self._fail_task(task_name, task_type, qid, str(e))
            result.message = str(e)
            raise TaskExecutionError(f"Task {task_name} failed: {e}") from e

        finally:
            self.state_manager.end_task(task_name, task_type, qid)

            if execution_service is not None:
                executed_task = self.state_manager.get_task(task_name, task_type, qid)
                self.history_recorder.record_task_result(
                    executed_task, execution_service.to_datamodel()
                )
                self.history_recorder.create_chip_history_snapshot(self.username)
                execution_service = self._update_execution(execution_service)

        result.calib_data_delta = self.state_manager.calib_data

        return execution_service, result

    def _update_execution(self, execution_service: "ExecutionService") -> "ExecutionService":
        """Update execution service with current calibration data."""
        return execution_service.merge_calib_data(
            calib_data=self.state_manager.calib_data,
        )
