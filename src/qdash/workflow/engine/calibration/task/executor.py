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
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field
from qdash.datamodel.task import CalibDataModel, OutputParameterModel
from qdash.workflow.calibtasks.results import PostProcessResult, PreProcessResult, RunResult
from qdash.workflow.engine.calibration.params_updater import get_params_updater
from qdash.workflow.engine.calibration.repository import FilesystemCalibDataSaver
from qdash.workflow.engine.calibration.task.history_recorder import TaskHistoryRecorder
from qdash.workflow.engine.calibration.task.result_processor import (
    FidelityValidationError,
    R2ValidationError,
    TaskResultProcessor,
)
from qdash.workflow.engine.calibration.task.state_manager import TaskStateManager

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from qdash.workflow.engine.calibration.execution.service import ExecutionService


@runtime_checkable
class TaskProtocol(Protocol):
    """Protocol for task objects."""

    name: str
    r2_threshold: float
    backend: str

    def get_name(self) -> str:
        """Get task name."""
        ...

    def get_task_type(self) -> str:
        """Get task type."""
        ...

    def is_qubit_task(self) -> bool:
        """Check if qubit task."""
        ...

    def is_coupling_task(self) -> bool:
        """Check if coupling task."""
        ...

    def preprocess(self, backend: Any, qid: str) -> PreProcessResult | None:
        """Run preprocessing."""
        ...

    def run(self, backend: Any, qid: str) -> RunResult | None:
        """Run the task."""
        ...

    def postprocess(
        self, backend: Any, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Run postprocessing."""
        ...

    def attach_task_id(self, task_id: str) -> dict[str, OutputParameterModel]:
        """Attach task ID to output parameters."""
        ...


@runtime_checkable
class BackendProtocol(Protocol):
    """Protocol for backend objects."""

    name: str

    def update_note(
        self,
        username: str,
        chip_id: str,
        calib_dir: str,
        execution_id: str,
        task_manager_id: str,
        project_id: str | None = None,
    ) -> None:
        """Update calibration note."""
        ...


class TaskExecutionError(Exception):
    """Exception raised when task execution fails."""

    pass


class TaskExecutionResult(BaseModel):
    """Result of task execution.

    This class encapsulates the complete result of a task execution,
    including output parameters, calibration data changes, and metadata.
    """

    task_name: str
    task_type: str
    qid: str
    success: bool = False
    message: str = ""
    output_parameters: dict[str, Any] = Field(default_factory=dict)
    r2: dict[str, float] | None = None
    calib_data_delta: CalibDataModel = Field(
        default_factory=lambda: CalibDataModel(qubit={}, coupling={})
    )
    controller_info: dict[str, dict[str, Any]] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


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
        """Initialize TaskExecutor.

        Parameters
        ----------
        state_manager : TaskStateManager
            Manager for task state
        calib_dir : str
            Directory for calibration data
        execution_id : str
            Current execution ID
        task_manager_id : str
            The unique TaskManager ID (used for result keys and note files)
        username : str
            Current username
        result_processor : TaskResultProcessor | None
            Processor for result validation
        history_recorder : TaskHistoryRecorder | None
            Recorder for task history
        data_saver : FilesystemCalibDataSaver | None
            Saver for figures and raw data

        """
        self.state_manager = state_manager
        self.execution_id = execution_id
        self.task_manager_id = task_manager_id
        self.username = username
        self.calib_dir = calib_dir
        self.result_processor = result_processor or TaskResultProcessor()
        self.history_recorder = history_recorder or TaskHistoryRecorder()
        self.data_saver = data_saver or FilesystemCalibDataSaver(calib_dir)
        self._controller_info: dict[str, dict[str, Any]] = {}

    def set_controller_info(self, controller_info: dict[str, dict[str, Any]]) -> None:
        """Set controller information for hardware tracking.

        Parameters
        ----------
        controller_info : dict[str, dict]
            Controller/hardware information to track

        """
        self._controller_info = controller_info

    def execute_task(
        self,
        task: TaskProtocol,
        backend: BackendProtocol,
        qid: str,
    ) -> dict[str, Any]:
        """Execute a task and return results (simplified version).

        This method provides a simpler interface for tests and cases
        where ExecutionManager integration is not needed.

        Parameters
        ----------
        task : TaskProtocol
            The task to execute
        backend : BackendProtocol
            The backend to use
        qid : str
            The qubit ID

        Returns
        -------
        dict[str, Any]
            Dictionary containing execution results

        Raises
        ------
        TaskExecutionError
            If task execution fails

        """
        task_name = task.get_name()
        task_type = task.get_task_type()

        result = {
            "task_name": task_name,
            "task_type": task_type,
            "qid": qid,
            "success": False,
            "message": "",
            "output_parameters": {},
            "r2": None,
        }

        try:
            # Start task
            self.state_manager.start_task(task_name, task_type, qid)

            # Preprocess
            preprocess_result = self._run_preprocess(task, backend, qid)
            if preprocess_result:
                self.state_manager.put_input_parameters(
                    task_name, preprocess_result.input_parameters, task_type, qid
                )

            # Run
            run_result = self._run_task(task, backend, qid)
            if run_result is None:
                # Task didn't produce results, mark as completed
                self._complete_task(task_name, task_type, qid, "No run result")
                result["success"] = True
                result["message"] = "Completed without run result"
                return result

            result["r2"] = run_result.r2

            # Validate R² if present
            if run_result.r2 is not None:
                self._validate_r2(run_result.r2, qid, task)

            # Postprocess
            postprocess_result = self._run_postprocess(task, backend, run_result, qid)

            # Process output parameters
            output_params = self._process_output_parameters(
                postprocess_result, task_name, qid, task_type
            )
            result["output_parameters"] = output_params

            # Save figures and raw data
            self._save_artifacts(postprocess_result, task_name, task_type, qid)

            # Complete task
            self._complete_task(task_name, task_type, qid, "Task completed successfully")
            result["success"] = True
            result["message"] = "Completed"

        except R2ValidationError as e:
            self._fail_task(task_name, task_type, qid, str(e))
            result["message"] = str(e)
            raise ValueError(str(e)) from e

        except FidelityValidationError as e:
            self._fail_task(task_name, task_type, qid, str(e))
            result["message"] = str(e)
            raise ValueError(str(e)) from e

        except Exception as e:
            self._fail_task(task_name, task_type, qid, str(e))
            result["message"] = str(e)
            raise TaskExecutionError(f"Task {task_name} failed: {e}") from e

        finally:
            # End task (record end time)
            self.state_manager.end_task(task_name, task_type, qid)

        return result

    def _run_preprocess(
        self,
        task: TaskProtocol,
        backend: BackendProtocol,
        qid: str,
    ) -> PreProcessResult | None:
        """Run task preprocessing.

        Parameters
        ----------
        task : TaskProtocol
            The task
        backend : BackendProtocol
            The backend
        qid : str
            The qubit ID

        Returns
        -------
        PreProcessResult | None
            The preprocess result or None

        """
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
        """Run the task.

        Parameters
        ----------
        task : TaskProtocol
            The task
        backend : BackendProtocol
            The backend
        qid : str
            The qubit ID

        Returns
        -------
        RunResult | None
            The run result or None

        """
        return task.run(backend, qid)

    def _run_postprocess(
        self,
        task: TaskProtocol,
        backend: BackendProtocol,
        run_result: RunResult,
        qid: str,
    ) -> PostProcessResult:
        """Run task postprocessing.

        Parameters
        ----------
        task : TaskProtocol
            The task
        backend : BackendProtocol
            The backend
        run_result : RunResult
            The run result
        qid : str
            The qubit ID

        Returns
        -------
        PostProcessResult
            The postprocess result

        """
        return task.postprocess(backend, self.execution_id, run_result, qid)

    def _validate_r2(
        self,
        r2: dict[str, float],
        qid: str,
        task: TaskProtocol,
    ) -> None:
        """Validate R² value.

        Parameters
        ----------
        r2 : dict[str, float]
            R² values per qid
        qid : str
            The qubit ID
        task : TaskProtocol
            The task (for threshold)

        Raises
        ------
        R2ValidationError
            If R² is below threshold

        """
        self.result_processor.validate_r2(r2, qid, task.r2_threshold)

    def _process_output_parameters(
        self,
        postprocess_result: PostProcessResult,
        task_name: str,
        qid: str,
        task_type: str,
    ) -> dict[str, OutputParameterModel]:
        """Process output parameters.

        Parameters
        ----------
        postprocess_result : PostProcessResult
            The postprocess result
        task_name : str
            The task name
        qid : str
            The qubit ID
        task_type : str
            The task type

        Returns
        -------
        dict[str, OutputParameterModel]
            The processed output parameters

        """
        output_params = postprocess_result.output_parameters

        # Get task_id
        task = self.state_manager.get_task(task_name, task_type, qid)
        task_id = task.task_id

        # Process and validate output parameters
        processed_params = self.result_processor.process_output_parameters(
            output_params, task_name, self.execution_id, task_id
        )

        # Store in state manager
        self.state_manager.put_output_parameters(task_name, processed_params, task_type, qid)

        return dict(processed_params)

    def _save_artifacts(
        self,
        postprocess_result: PostProcessResult,
        task_name: str,
        task_type: str,
        qid: str,
    ) -> None:
        """Save figures and raw data.

        Parameters
        ----------
        postprocess_result : PostProcessResult
            The postprocess result
        task_name : str
            The task name
        task_type : str
            The task type
        qid : str
            The qubit ID

        """
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
        """Mark task as completed.

        Parameters
        ----------
        task_name : str
            The task name
        task_type : str
            The task type
        qid : str
            The qubit ID
        message : str
            Completion message

        """
        self.state_manager.update_task_status_to_completed(task_name, message, task_type, qid)

    def _fail_task(
        self,
        task_name: str,
        task_type: str,
        qid: str,
        message: str,
    ) -> None:
        """Mark task as failed.

        Parameters
        ----------
        task_name : str
            The task name
        task_type : str
            The task type
        qid : str
            The qubit ID
        message : str
            Failure message

        """
        self.state_manager.update_task_status_to_failed(task_name, message, task_type, qid)

    def execute(
        self,
        task: TaskProtocol,
        backend: BackendProtocol,
        execution_service: "ExecutionService",
        qid: str,
    ) -> tuple["ExecutionService", TaskExecutionResult]:
        """Execute a task with full lifecycle management.

        This is the main entry point for task execution.

        Parameters
        ----------
        task : TaskProtocol
            The task to execute
        backend : BackendProtocol
            The backend to use
        execution_service : ExecutionService
            The execution service
        qid : str
            The qubit ID

        Returns
        -------
        tuple[ExecutionService, TaskExecutionResult]
            Updated execution service and task execution result

        Raises
        ------
        TaskExecutionError
            If task execution fails
        ValueError
            If R² or fidelity validation fails
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

            # Record task start to history
            executed_task = self.state_manager.get_task(task_name, task_type, qid)
            self.history_recorder.record_task_result(
                executed_task, execution_service.to_datamodel()
            )

            # Update execution service
            execution_service = self._update_execution(execution_service)

            # 2. Preprocess
            preprocess_result = self._run_preprocess(task, backend, qid)
            if preprocess_result:
                self.state_manager.put_input_parameters(
                    task_name, preprocess_result.input_parameters, task_type, qid
                )
                execution_service = self._update_execution(execution_service)

            # 3. Run
            run_result = self._run_task(task, backend, qid)
            result.r2 = run_result.r2 if run_result else None

            if run_result is None:
                # Task didn't produce results, mark as completed
                self._complete_task(task_name, task_type, qid, "No run result")
                result.success = True
                result.message = "Completed without run result"
                return execution_service, result

            # 4. Postprocess
            postprocess_result = self._run_postprocess(task, backend, run_result, qid)

            if postprocess_result:
                # 5. Process and validate results
                self._process_results(
                    task, execution_service, postprocess_result, qid, run_result, backend
                )

                result.output_parameters = dict(
                    self.state_manager.get_task(task_name, task_type, qid).output_parameters
                )

            # 6. Complete task
            self._complete_task(task_name, task_type, qid, f"{task_name} is completed")

            # Record completion to history
            executed_task = self.state_manager.get_task(task_name, task_type, qid)
            self.history_recorder.record_task_result(
                executed_task, execution_service.to_datamodel()
            )

            execution_service = self._update_execution(execution_service)
            result.success = True
            result.message = "Completed"

        except (R2ValidationError, FidelityValidationError, ValueError) as e:
            self._fail_task(task_name, task_type, qid, str(e))
            executed_task = self.state_manager.get_task(task_name, task_type, qid)
            self.history_recorder.record_task_result(
                executed_task, execution_service.to_datamodel()
            )
            result.message = str(e)
            raise

        except Exception as e:
            self._fail_task(task_name, task_type, qid, str(e))
            executed_task = self.state_manager.get_task(task_name, task_type, qid)
            self.history_recorder.record_task_result(
                executed_task, execution_service.to_datamodel()
            )
            result.message = str(e)
            raise TaskExecutionError(f"Task {task_name} failed: {e}") from e

        finally:
            # End task (record end time)
            self.state_manager.end_task(task_name, task_type, qid)

            # Final history record
            executed_task = self.state_manager.get_task(task_name, task_type, qid)
            self.history_recorder.record_task_result(
                executed_task, execution_service.to_datamodel()
            )

            # Create chip history snapshot
            self.history_recorder.create_chip_history_snapshot(self.username)

            execution_service = self._update_execution(execution_service)

        # Build calib_data_delta from state manager
        result.calib_data_delta = self.state_manager.calib_data
        result.controller_info = self._controller_info

        return execution_service, result

    def _update_execution(
        self, execution_service: "ExecutionService"
    ) -> "ExecutionService":
        """Update execution service with current state.

        Parameters
        ----------
        execution_service : ExecutionService
            The execution service to update

        Returns
        -------
        ExecutionService
            Updated execution service
        """
        return execution_service.update_with_task_result(
            task_manager_id=self.task_manager_id,
            task_result=self.state_manager.task_result,
            calib_data=self.state_manager.calib_data,
            controller_info=self._controller_info,
        )

    def _process_results(
        self,
        task: TaskProtocol,
        execution_service: "ExecutionService",
        postprocess_result: PostProcessResult,
        qid: str,
        run_result: RunResult,
        backend: BackendProtocol,
    ) -> bool:
        """Process task results using ExecutionService.

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
        backend : BackendProtocol
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
                self.result_processor.validate_fidelity(
                    postprocess_result.output_parameters, task_name
                )
            except FidelityValidationError as e:
                raise ValueError(str(e)) from e

        # 2. Process output parameters
        if postprocess_result.output_parameters:
            task_model = self.state_manager.get_task(task_name, task_type, qid)
            task.attach_task_id(task_model.task_id)

            processed_params = self.result_processor.process_output_parameters(
                postprocess_result.output_parameters,
                task_name,
                self.execution_id,
                task_model.task_id,
            )
            self.state_manager.put_output_parameters(task_name, processed_params, task_type, qid)

        # 3. Save figures
        if postprocess_result.figures:
            png_paths, json_paths = self.data_saver.save_figures(
                postprocess_result.figures, task_name, task_type, qid
            )
            self.state_manager.set_figure_paths(task_name, task_type, qid, png_paths, json_paths)

        # 4. Save raw data
        if postprocess_result.raw_data:
            raw_paths = self.data_saver.save_raw_data(
                postprocess_result.raw_data, task_name, task_type, qid
            )
            self.state_manager.set_raw_data_paths(task_name, task_type, qid, raw_paths)

        # 5. Validate R²
        backend_success = True
        if run_result.has_r2():
            r2_value = run_result.r2.get(qid)
            if r2_value is None:
                backend_success = False
            else:
                try:
                    self.result_processor.validate_r2(run_result.r2, qid, task.r2_threshold)
                except R2ValidationError:
                    # Clear output parameters on R² failure
                    if postprocess_result.output_parameters:
                        self.state_manager.clear_output_parameters(task_name, task_type, qid)
                    raise ValueError(f"{task_name} R² value too low: {r2_value:.4f}")

            if not backend_success and postprocess_result.output_parameters:
                self.state_manager.clear_output_parameters(task_name, task_type, qid)

        # 6. Backend-specific save processing
        self._save_backend_specific(task, execution_service, qid, backend, backend_success)

        return backend_success

    def _save_backend_specific(
        self,
        task: TaskProtocol,
        execution_service: "ExecutionService",
        qid: str,
        backend: BackendProtocol,
        success: bool,
    ) -> None:
        """Backend-specific save processing using ExecutionService.

        Parameters
        ----------
        task : TaskProtocol
            The task
        execution_service : ExecutionService
            The execution service
        qid : str
            The qubit ID
        backend : BackendProtocol
            The backend
        success : bool
            Whether backend updates should be applied
        """
        if task.backend == "qubex":
            self._save_qubex_specific(task, execution_service, qid, backend, success)
        elif task.backend == "fake":
            # Simulation metadata save (implement as needed)
            pass

    def _save_qubex_specific(
        self,
        task: TaskProtocol,
        execution_service: "ExecutionService",
        qid: str,
        backend: BackendProtocol,
        success: bool,
    ) -> None:
        """Qubex-specific save processing using ExecutionService.

        Parameters
        ----------
        task : TaskProtocol
            The task
        execution_service : ExecutionService
            The execution service
        qid : str
            The qubit ID
        backend : BackendProtocol
            The backend
        success : bool
            Whether backend updates should be applied
        """
        from qdash.dbmodel.coupling import CouplingDocument
        from qdash.dbmodel.qubit import QubitDocument

        task_name = task.get_name()
        task_type = task.get_task_type()

        # Get output parameters
        task_model = self.state_manager.get_task(task_name, task_type, qid)
        output_parameters = dict(task_model.output_parameters)

        if not success:
            logger.info(
                "Skipping backend parameter updates for %s due to failed R² validation",
                task_name,
            )
            # Still save to database even if R² failed
            if output_parameters:
                if task.is_qubit_task():
                    QubitDocument.update_calib_data(
                        username=self.username,
                        qid=qid,
                        chip_id=execution_service.chip_id,
                        output_parameters=output_parameters,
                        project_id=execution_service.project_id,
                    )
                elif task.is_coupling_task():
                    CouplingDocument.update_calib_data(
                        username=self.username,
                        qid=qid,
                        chip_id=execution_service.chip_id,
                        output_parameters=output_parameters,
                        project_id=execution_service.project_id,
                    )
            return

        # Save calibration note
        if backend.name == "qubex":
            backend.update_note(
                username=self.username,
                chip_id=execution_service.chip_id,
                calib_dir=self.calib_dir,
                execution_id=execution_service.execution_id,
                task_manager_id=self.task_manager_id,
                project_id=execution_service.project_id,
            )

        # Update database
        if output_parameters:
            if task.is_qubit_task():
                QubitDocument.update_calib_data(
                    username=self.username,
                    qid=qid,
                    chip_id=execution_service.chip_id,
                    output_parameters=output_parameters,
                    project_id=execution_service.project_id,
                )
                self._update_backend_params(
                    backend, execution_service, qid, output_parameters
                )
            elif task.is_coupling_task():
                CouplingDocument.update_calib_data(
                    username=self.username,
                    qid=qid,
                    chip_id=execution_service.chip_id,
                    output_parameters=output_parameters,
                    project_id=execution_service.project_id,
                )

    def _update_backend_params(
        self,
        backend: BackendProtocol,
        execution_service: "ExecutionService",
        qid: str,
        output_parameters: dict[str, Any],
    ) -> None:
        """Update backend parameters using ExecutionService.

        Parameters
        ----------
        backend : BackendProtocol
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
