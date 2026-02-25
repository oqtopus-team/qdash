"""TaskContext - Lightweight task context without facade bloat.

This module provides the TaskContext class that directly holds TaskStateManager
and TaskExecutor without the sync overhead of the old TaskManager facade.

The key difference from TaskManager:
- No bidirectional sync (_sync_to/_sync_from) on every method call
- Direct property access to state (no copying)
- Cleaner, more traceable code path
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from qdash.datamodel.task import (
    CalibDataModel,
    TaskResultModel,
    TaskTypes,
)
from qdash.repository import FilesystemCalibDataSaver
from qdash.workflow.engine.task.executor import TaskExecutor
from qdash.workflow.engine.task.history_recorder import TaskHistoryRecorder
from qdash.workflow.engine.task.result_processor import TaskResultProcessor
from qdash.workflow.engine.task.snapshot_loader import SnapshotParameterLoader
from qdash.workflow.engine.task.state_manager import TaskStateManager

logger = logging.getLogger(__name__)


class TaskContext:
    """Lightweight task context without facade bloat.

    This class directly holds TaskStateManager and TaskExecutor,
    eliminating the sync overhead of the old TaskManager.

    Attributes
    ----------
    id : str
        Unique session identifier
    username : str
        Username for this session
    execution_id : str
        Execution identifier
    calib_dir : str
        Calibration data directory
    state : TaskStateManager
        Direct access to task state (no sync needed)
    executor : TaskExecutor
        Task executor for running calibration tasks
    Example
    -------
    Production usage::

        session = TaskContext(
            username="alice",
            execution_id="20240101-001",
            qids=["0", "1"],
            calib_dir="/app/calib_data/alice/20240101/001",
        )

        # Direct access to state - preferred pattern
        session.state.start_task("CheckFreq", TaskTypes.QUBIT, "0")

    Testing with dependency injection::

        mock_state = MagicMock(spec=TaskStateManager)
        mock_executor = MagicMock(spec=TaskExecutor)
        session = TaskContext(
            username="test",
            execution_id="test-001",
            qids=["0"],
            calib_dir="/tmp/test",
            state_manager=mock_state,
            executor=mock_executor,
        )
    """

    def __init__(
        self,
        username: str,
        execution_id: str,
        qids: list[str],
        calib_dir: str,
        *,
        state_manager: TaskStateManager | None = None,
        data_saver: FilesystemCalibDataSaver | None = None,
        executor: TaskExecutor | None = None,
        result_processor: TaskResultProcessor | None = None,
        history_recorder: TaskHistoryRecorder | None = None,
        context_id: str | None = None,
        snapshot_loader: SnapshotParameterLoader | None = None,
        source_task_id: str | None = None,
    ) -> None:
        self.id = context_id or str(uuid.uuid4())
        self.username = username
        self.execution_id = execution_id
        self.calib_dir = calib_dir
        # Initialize state manager (the source of truth)
        # Use injected or create default
        self.state: TaskStateManager = state_manager or TaskStateManager(qids=qids)

        # Initialize data saver
        self.data_saver = data_saver or FilesystemCalibDataSaver(calib_dir)

        # Initialize executor with state manager
        # Use injected or create default
        self.executor = executor or TaskExecutor(
            state_manager=self.state,
            calib_dir=calib_dir,
            execution_id=execution_id,
            task_manager_id=self.id,
            username=username,
            result_processor=result_processor or TaskResultProcessor(),
            history_recorder=history_recorder or TaskHistoryRecorder(),
            data_saver=self.data_saver,
            snapshot_loader=snapshot_loader,
            source_task_id=source_task_id,
        )

        # Initialize containers for coupling qids (only if state_manager was not injected)
        if state_manager is None:
            for qid in qids:
                if self._is_coupling_format(qid):
                    self.state.calib_data.coupling[qid] = {}

    # === Direct Properties (no sync needed) ===

    @property
    def task_result(self) -> TaskResultModel:
        """Get task result directly from state manager."""
        return self.state.task_result

    @property
    def calib_data(self) -> CalibDataModel:
        """Get calibration data directly from state manager."""
        return self.state.calib_data

    # === Format Checking ===

    def _is_qubit_format(self, qid: str) -> bool:
        """Check if qid is in qubit format (no hyphen)."""
        return "-" not in qid

    def _is_coupling_format(self, qid: str) -> bool:
        """Check if qid is in coupling format (has hyphen)."""
        return "-" in qid

    # === Upstream Task ID ===

    def set_upstream_task_id(self, task_id: str) -> None:
        """Set upstream task ID for dependency tracking."""
        self.state.set_upstream_task_id(task_id)

    # === Figure/Data Saving ===

    def save_figures(
        self,
        figures: list[Any],
        task_name: str,
        task_type: str = TaskTypes.GLOBAL,
        savedir: str = "",
        qid: str = "",
    ) -> None:
        """Save figures for a task."""
        override_dir = savedir or None
        png_paths, json_paths = self.data_saver.save_figures(
            figures,
            task_name,
            task_type,
            qid,
            output_dir=override_dir,
        )
        self.state.set_figure_paths(task_name, task_type, qid, png_paths, json_paths)

    def save_figure(
        self,
        figure: Any,
        task_name: str,
        task_type: str = TaskTypes.GLOBAL,
        savedir: str = "",
        qid: str = "",
    ) -> None:
        """Save a single figure."""
        self.save_figures([figure], task_name, task_type, savedir, qid)

    def save_raw_data(
        self,
        raw_data: list[Any],
        task_name: str,
        task_type: str = TaskTypes.GLOBAL,
        qid: str = "",
    ) -> None:
        """Save raw data for a task."""
        paths = self.data_saver.save_raw_data(
            raw_data,
            task_name,
            task_type,
            qid,
            output_dir=None,
        )
        self.state.set_raw_data_paths(task_name, task_type, qid, paths)

    # === Persistence ===

    def save(self, calib_dir: str = "") -> None:
        """Save task session state to JSON file."""
        if calib_dir == "":
            calib_dir = f"{self.calib_dir}/task"

        Path(calib_dir).mkdir(parents=True, exist_ok=True)

        data = {
            "id": self.id,
            "username": self.username,
            "execution_id": self.execution_id,
            "calib_dir": self.calib_dir,
            "task_result": self.task_result.model_dump(mode="json"),
            "calib_data": self.calib_data.model_dump(mode="json"),
        }

        with Path(f"{calib_dir}/{self.id}.json").open("w") as f:
            json.dump(data, f, indent=2)

    # =========================================================================
    # Core Task Operations
    # =========================================================================
    # These methods are frequently used and provide convenient shortcuts.

    def get_task(self, task_name: str, task_type: str = TaskTypes.GLOBAL, qid: str = "") -> Any:
        """Get a task by name.

        This is a core operation used frequently in calibration flows.
        """
        return self.state.get_task(task_name, task_type, qid)

    def start_task(self, task_name: str, task_type: str = TaskTypes.GLOBAL, qid: str = "") -> None:
        """Start a task (set status to RUNNING and record start time).

        This is a core operation used frequently in calibration flows.
        """
        self.state.start_task(task_name, task_type, qid)

    def end_task(self, task_name: str, task_type: str = TaskTypes.GLOBAL, qid: str = "") -> None:
        """End a task (record end time and calculate elapsed time).

        This is a core operation used frequently in calibration flows.
        """
        self.state.end_task(task_name, task_type, qid)
