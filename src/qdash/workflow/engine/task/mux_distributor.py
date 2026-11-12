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

from qdash.common.mux_mapping import resolve_chip_mux_mapping
from qdash.workflow.engine.task.backend_saver import resolve_publish_targets

if TYPE_CHECKING:
    from qdash.common.mux_mapping import MuxMapping
    from qdash.datamodel.task_invocation import TaskInvocation
    from qdash.repository import FilesystemCalibDataSaver
    from qdash.workflow.calibtasks.results import RunResult
    from qdash.workflow.engine.backend.base import BaseBackend
    from qdash.workflow.engine.execution.service import ExecutionService
    from qdash.workflow.engine.task.backend_saver import BackendSaver
    from qdash.workflow.engine.task.history_recorder import TaskHistoryRecorder
    from qdash.workflow.engine.task.result_processor import TaskResultProcessor
    from qdash.workflow.engine.task.state_manager import TaskStateManager
    from qdash.workflow.engine.task.types import TaskProtocol

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
    mux_mapping : MuxMapping | None
        MUX membership; resolved from the execution's chip topology if None
    """

    def __init__(
        self,
        state_manager: "TaskStateManager",
        execution_id: str,
        result_processor: "TaskResultProcessor",
        data_saver: "FilesystemCalibDataSaver",
        history_recorder: "TaskHistoryRecorder",
        backend_saver: "BackendSaver",
        mux_mapping: "MuxMapping | None" = None,
    ) -> None:
        self._state_manager = state_manager
        self._execution_id = execution_id
        self._result_processor = result_processor
        self._data_saver = data_saver
        self._history_recorder = history_recorder
        self._backend_saver = backend_saver
        self._mux_mapping = mux_mapping

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
        # Members come from the chip topology; an explicit mapping that does not
        # know the representative raises instead of fanning out to guessed qids.
        mapping = self._mux_mapping
        if mapping is None:
            mapping = resolve_chip_mux_mapping(
                execution_service.project_id, execution_service.chip_id
            )
            self._mux_mapping = mapping
        if mapping.unbounded and mapping.find_mux(representative_qid) is None:
            logger.warning(
                "Could not parse representative_qid=%s as integer, skipping MUX distribution",
                representative_qid,
            )
            return
        mux_id = mapping.mux_of(representative_qid)

        # Distributed results belong to the same planned call as the representative.
        representative = self._state_manager.get_task(
            task.get_name(), task.get_task_type(), representative_qid
        )
        for target_qid in mapping.qids_of(mux_id):
            if target_qid == representative_qid:
                continue
            self._distribute_to_qid(
                task,
                backend,
                execution_service,
                run_result,
                target_qid,
                invocation=representative.invocation,
            )

    def _distribute_to_qid(
        self,
        task: "TaskProtocol",
        backend: "BaseBackend",
        execution_service: "ExecutionService",
        run_result: "RunResult",
        target_qid: str,
        invocation: "TaskInvocation | None" = None,
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
            distributed = self._state_manager.ensure_task_exists(task_name, task_type, target_qid)
            distributed.invocation = invocation
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
                        task_name,
                        processed_params,
                        task_type,
                        target_qid,
                        publish_targets=resolve_publish_targets(task, processed_params),
                    )

                if postprocess_result.figures:
                    png_paths, json_paths = self._data_saver.save_figures(
                        postprocess_result.figures, task_name, task_type, target_qid
                    )
                    self._state_manager.set_figure_paths(
                        task_name, task_type, target_qid, png_paths, json_paths
                    )

                self._backend_saver.save_mux_qid(task, execution_service, target_qid, backend)

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
