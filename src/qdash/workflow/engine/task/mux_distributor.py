"""MUX result distribution logic for calibration tasks.

This module provides the MuxDistributor class that fans out results from a
representative qubit to all other qubits in the same MUX group.

For MUX-level tasks (e.g. CheckResonatorSpectroscopy), the task runs once for
the representative qubit but produces results for all qubits in the MUX.
MuxDistributor handles postprocessing, saving, and recording for each
non-representative qubit.

Extracted from TaskExecutor to isolate MUX distribution concerns.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qdash.repository import FilesystemCalibDataSaver
    from qdash.workflow.calibtasks.results import RunResult
    from qdash.workflow.engine.backend.base import BaseBackend
    from qdash.workflow.engine.execution.service import ExecutionService
    from qdash.workflow.engine.task.backend_saver import BackendSaver
    from qdash.workflow.engine.task.executor import TaskProtocol
    from qdash.workflow.engine.task.history_recorder import TaskHistoryRecorder
    from qdash.workflow.engine.task.result_processor import TaskResultProcessor
    from qdash.workflow.engine.task.state_manager import TaskStateManager

logger = logging.getLogger(__name__)


class MuxDistributor:
    """Distributes MUX task results from a representative qubit to other qubits.

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
    history_recorder : TaskHistoryRecorder
        Recorder for task history
    backend_saver : BackendSaver
        Backend-specific persistence handler
    """

    def __init__(
        self,
        state_manager: "TaskStateManager",
        execution_id: str,
        result_processor: "TaskResultProcessor",
        data_saver: "FilesystemCalibDataSaver",
        history_recorder: "TaskHistoryRecorder",
        backend_saver: "BackendSaver",
    ) -> None:
        self._state_manager = state_manager
        self._execution_id = execution_id
        self._result_processor = result_processor
        self._data_saver = data_saver
        self._history_recorder = history_recorder
        self._backend_saver = backend_saver

    def distribute(
        self,
        task: "TaskProtocol",
        backend: "BaseBackend",
        execution_service: "ExecutionService",
        run_result: "RunResult",
        representative_qid: str,
    ) -> None:
        """Distribute MUX task results to other qubits in the MUX.

        For MUX-level tasks, the task runs once for the representative qubit
        but produces results for all qubits in the MUX. This method calls
        postprocess for each other qubit to save their figures and output
        parameters.

        Parameters
        ----------
        task : TaskProtocol
            The task instance
        backend : BaseBackend
            The backend
        execution_service : ExecutionService
            The execution service
        run_result : RunResult
            The run result from the representative qubit's execution
        representative_qid : str
            The representative qubit ID (the one that executed the task)
        """
        # Calculate other qids in the MUX (assuming 4 qubits per MUX)
        try:
            mux_base_qid = (int(representative_qid) // 4) * 4
        except ValueError:
            logger.warning(
                "Could not parse representative_qid=%s as integer, skipping MUX distribution",
                representative_qid,
            )
            return

        for pos_in_mux in range(4):
            target_qid = str(mux_base_qid + pos_in_mux)
            if target_qid == representative_qid:
                continue
            self._distribute_to_qid(task, backend, execution_service, run_result, target_qid)

    def _distribute_to_qid(
        self,
        task: "TaskProtocol",
        backend: "BaseBackend",
        execution_service: "ExecutionService",
        run_result: "RunResult",
        target_qid: str,
    ) -> None:
        """Postprocess, save, and record a MUX task result for a single qubit.

        Parameters
        ----------
        task : TaskProtocol
            The task instance
        backend : BaseBackend
            The backend
        execution_service : ExecutionService
            The execution service
        run_result : RunResult
            The run result from the representative qubit's execution
        target_qid : str
            The qubit ID to distribute results to
        """
        task_name = task.get_name()
        task_type = task.get_task_type()
        logger.debug("Processing MUX result for qid=%s (task=%s)", target_qid, task_name)

        try:
            self._state_manager.ensure_task_exists(task_name, task_type, target_qid)
            self._state_manager.start_task(task_name, task_type, target_qid)

            postprocess_result = task.postprocess(
                backend, self._execution_id, run_result, target_qid
            )

            if postprocess_result:
                if postprocess_result.output_parameters:
                    task_model = self._state_manager.get_task(task_name, task_type, target_qid)
                    task.attach_task_id(task_model.task_id)
                    processed_params = self._result_processor.process_output_parameters(
                        postprocess_result.output_parameters,
                        task_name,
                        self._execution_id,
                        task_model.task_id,
                    )
                    self._state_manager.put_output_parameters(
                        task_name, processed_params, task_type, target_qid
                    )

                if postprocess_result.figures:
                    png_paths, json_paths = self._data_saver.save_figures(
                        postprocess_result.figures, task_name, task_type, target_qid
                    )
                    self._state_manager.set_figure_paths(
                        task_name, task_type, target_qid, png_paths, json_paths
                    )

                self._backend_saver.save_mux_qid(task, execution_service, target_qid)

            self._state_manager.update_task_status_to_completed(
                task_name, f"{task_name} completed (MUX distribution)", task_type, target_qid
            )

        except Exception as e:
            logger.warning(
                "Failed to process MUX result for qid=%s: %s",
                target_qid,
                e,
                exc_info=True,
            )
            self._state_manager.update_task_status_to_failed(
                task_name, str(e), task_type, target_qid
            )

        finally:
            self._state_manager.end_task(task_name, task_type, target_qid)
            executed_task = self._state_manager.get_task(task_name, task_type, target_qid)
            self._history_recorder.record_task_result(
                executed_task, execution_service.to_datamodel()
            )
