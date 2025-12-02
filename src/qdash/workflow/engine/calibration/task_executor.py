"""TaskExecutor for executing calibration tasks.

This module provides the TaskExecutor class that handles the execution
of calibration tasks including preprocessing, running, and postprocessing.
"""

import logging
from typing import Any, Protocol, runtime_checkable

from qdash.datamodel.task import OutputParameterModel
from qdash.workflow.engine.calibration.repository import FilesystemCalibDataSaver
from qdash.workflow.engine.calibration.task_result_processor import (
    FidelityValidationError,
    R2ValidationError,
    TaskResultProcessor,
)
from qdash.workflow.engine.calibration.task_state_manager import TaskStateManager
from qdash.workflow.tasks.base import PostProcessResult, PreProcessResult, RunResult

logger = logging.getLogger(__name__)


@runtime_checkable
class TaskProtocol(Protocol):
    """Protocol for task objects."""

    name: str
    r2_threshold: float

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

    def preprocess(self, session: Any, qid: str) -> PreProcessResult | None:
        """Run preprocessing."""
        ...

    def run(self, session: Any, qid: str) -> RunResult | None:
        """Run the task."""
        ...

    def postprocess(
        self, session: Any, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Run postprocessing."""
        ...

    def attach_task_id(self, task_id: str) -> dict[str, OutputParameterModel]:
        """Attach task ID to output parameters."""
        ...


@runtime_checkable
class SessionProtocol(Protocol):
    """Protocol for session objects."""

    name: str


class TaskExecutionError(Exception):
    """Exception raised when task execution fails."""

    pass


class TaskExecutor:
    """Executor for calibration tasks.

    This class handles:
    - Task lifecycle (start, preprocess, run, postprocess, end)
    - Figure and raw data saving
    - R² and fidelity validation
    - State updates via TaskStateManager

    Attributes
    ----------
    state_manager : TaskStateManager
        Manager for task state
    result_processor : TaskResultProcessor
        Processor for result validation
    data_saver : FilesystemCalibDataSaver
        Saver for figures and raw data
    execution_id : str
        Current execution ID

    """

    def __init__(
        self,
        state_manager: TaskStateManager,
        calib_dir: str,
        execution_id: str,
        result_processor: TaskResultProcessor | None = None,
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
        result_processor : TaskResultProcessor | None
            Processor for result validation
        data_saver : FilesystemCalibDataSaver | None
            Saver for figures and raw data

        """
        self.state_manager = state_manager
        self.execution_id = execution_id
        self.result_processor = result_processor or TaskResultProcessor()
        self.data_saver = data_saver or FilesystemCalibDataSaver(calib_dir)

    def execute_task(
        self,
        task: TaskProtocol,
        session: SessionProtocol,
        qid: str,
    ) -> dict[str, Any]:
        """Execute a task and return results.

        Parameters
        ----------
        task : TaskProtocol
            The task to execute
        session : SessionProtocol
            The session to use
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
            preprocess_result = self._run_preprocess(task, session, qid)
            if preprocess_result:
                self.state_manager.put_input_parameters(
                    task_name, preprocess_result.input_parameters, task_type, qid
                )

            # Run
            run_result = self._run_task(task, session, qid)
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
            postprocess_result = self._run_postprocess(
                task, session, run_result, qid
            )

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
        session: SessionProtocol,
        qid: str,
    ) -> PreProcessResult | None:
        """Run task preprocessing.

        Parameters
        ----------
        task : TaskProtocol
            The task
        session : SessionProtocol
            The session
        qid : str
            The qubit ID

        Returns
        -------
        PreProcessResult | None
            The preprocess result or None

        """
        try:
            return task.preprocess(session, qid)
        except Exception as e:
            logger.warning(f"Preprocess failed for {task.get_name()}: {e}")
            return None

    def _run_task(
        self,
        task: TaskProtocol,
        session: SessionProtocol,
        qid: str,
    ) -> RunResult | None:
        """Run the task.

        Parameters
        ----------
        task : TaskProtocol
            The task
        session : SessionProtocol
            The session
        qid : str
            The qubit ID

        Returns
        -------
        RunResult | None
            The run result or None

        """
        return task.run(session, qid)

    def _run_postprocess(
        self,
        task: TaskProtocol,
        session: SessionProtocol,
        run_result: RunResult,
        qid: str,
    ) -> PostProcessResult:
        """Run task postprocessing.

        Parameters
        ----------
        task : TaskProtocol
            The task
        session : SessionProtocol
            The session
        run_result : RunResult
            The run result
        qid : str
            The qubit ID

        Returns
        -------
        PostProcessResult
            The postprocess result

        """
        return task.postprocess(session, self.execution_id, run_result, qid)

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
        self.state_manager.put_output_parameters(
            task_name, processed_params, task_type, qid
        )

        return processed_params

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
            self.state_manager.set_figure_paths(
                task_name, task_type, qid, png_paths, json_paths
            )

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
        self.state_manager.update_task_status_to_completed(
            task_name, message, task_type, qid
        )

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
        self.state_manager.update_task_status_to_failed(
            task_name, message, task_type, qid
        )
