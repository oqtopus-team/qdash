"""Python Flow Editor - Session management and helper functions for custom calibration flows.

This module provides a high-level API for creating custom calibration workflows
using Python code. It leverages the refactored TaskManager architecture with
integrated save processing.

Example:
    Basic calibration flow:

    ```python
    from prefect import flow
    from qdash.workflow.helpers import init_calibration, calibrate_qubits_parallel, finish_calibration

    @flow
    def simple_calibration(username, execution_id, chip_id, qids):
        session = init_calibration(username, execution_id, chip_id)
        results = calibrate_qubits_parallel(
            qids=qids,
            tasks=["CheckFreq", "CheckRabi", "CheckT1"]
        )
        finish_calibration()
        return results
    ```
"""

from pathlib import Path
from typing import Any

import pendulum
from prefect import get_run_logger
from qdash.datamodel.menu import BatchNode, ParallelNode, ScheduleNode, SerialNode
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_history import ChipHistoryDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.workflow.core.calibration.execution_manager import ExecutionManager
from qdash.workflow.core.calibration.task import execute_dynamic_task_by_qid
from qdash.workflow.core.calibration.task_manager import TaskManager
from qdash.workflow.core.session.factory import create_session
from qdash.workflow.tasks.active_protocols import generate_task_instances


def generate_execution_id(username: str, chip_id: str) -> str:
    """Generate a unique execution ID based on the current date and an execution index.

    This function creates execution IDs in the format YYYYMMDD-NNN, where:
    - YYYYMMDD is the current date in JST timezone
    - NNN is a zero-padded 3-digit counter for that day

    Args:
        username: Username for the execution
        chip_id: Chip ID for the execution

    Returns:
        Generated execution ID (e.g., "20240101-001")

    Example:
        ```python
        exec_id = generate_execution_id("alice", "chip_1")
        print(exec_id)  # "20240123-001"
        ```

    """
    date_str = pendulum.now(tz="Asia/Tokyo").date().strftime("%Y%m%d")
    execution_index = ExecutionCounterDocument.get_next_index(date_str, username, chip_id)
    return f"{date_str}-{execution_index:03d}"


class FlowSession:
    """Session manager for Python Flow calibration workflows.

    This class provides a high-level interface for managing calibration sessions,
    executing tasks, and handling parameters. It uses the refactored TaskManager
    architecture with integrated save processing.

    Attributes:
        username: Username for the calibration session
        execution_id: Unique execution identifier
        chip_id: Target chip ID
        backend: Backend type ('qubex' or 'fake')
        execution_manager: Manages execution state and history
        session: Backend session for device communication

    Example:
        ```python
        session = FlowSession("user", "20240101-001", "chip_1")
        result = session.execute_task("CheckFreq", "0")
        freq = session.get_parameter("0", "qubit_frequency")
        session.finish_calibration()
        ```
    """

    def __init__(
        self,
        username: str,
        chip_id: str,
        qids: list[str],
        execution_id: str | None = None,
        backend: str = "qubex",
        name: str = "Python Flow Execution",
        tags: list[str] | None = None,
        use_lock: bool = True,
        note: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a new calibration flow session.

        Args:
            username: Username for the session
            chip_id: Target chip ID
            qids: List of qubit IDs to calibrate (required for qubex initialization)
            execution_id: Unique execution identifier (e.g., "20240101-001").
                If None, auto-generates using current date and counter.
            backend: Backend type, either 'qubex' or 'fake' (default: 'qubex')
            name: Human-readable name for the execution (default: 'Python Flow Execution')
            tags: List of tags for categorization (default: ['python_flow'])
            use_lock: Whether to use ExecutionLock to prevent concurrent calibrations (default: True)
            note: Additional notes to store with execution (default: {})

        Raises:
            RuntimeError: If use_lock=True and another calibration is already running

        """
        self.username = username
        self.chip_id = chip_id
        self.qids = qids
        self.backend = backend
        self.use_lock = use_lock
        self._lock_acquired = False
        self._last_executed_task_id_by_qid: dict[str, str] = {}  # Track last task_id per qid

        # Auto-generate execution_id if not provided
        if execution_id is None:
            execution_id = generate_execution_id(username, chip_id)

        self.execution_id = execution_id

        # Acquire lock if requested
        if use_lock:
            if ExecutionLockDocument.get_lock_status():
                msg = "Calibration is already running. Cannot start a new session."
                raise RuntimeError(msg)
            ExecutionLockDocument.lock()
            self._lock_acquired = True

        # Set default tags and note
        if tags is None:
            tags = ["python_flow"]
        if note is None:
            note = {}

        # Setup calibration directory
        date_str, index = execution_id.split("-")
        calib_data_path = f"/app/calib_data/{username}/{date_str}/{index}"

        # Create directory structure (matching create_directory_task behavior)
        Path(calib_data_path).mkdir(parents=True, exist_ok=True)
        Path(f"{calib_data_path}/task").mkdir(exist_ok=True)
        Path(f"{calib_data_path}/fig").mkdir(exist_ok=True)
        Path(f"{calib_data_path}/calib").mkdir(exist_ok=True)
        Path(f"{calib_data_path}/calib_note").mkdir(exist_ok=True)

        # Initialize ExecutionManager with integrated save processing
        self.execution_manager = (
            ExecutionManager(
                username=username,
                execution_id=execution_id,
                calib_data_path=calib_data_path,
                chip_id=chip_id,
                name=name,
                tags=tags,
                note=note,
            )
            .save()
            .start_execution()
            .update_execution_status_to_running()
        )

        # Initialize TaskManager for tracking all tasks
        # This will be reused across all execute_task calls
        self.task_manager = TaskManager(
            username=username,
            execution_id=execution_id,
            qids=qids,
            calib_dir=calib_data_path,
        )

        # Initialize backend session
        # Note: For qubex backend, qids must be provided for proper box selection
        note_path = Path(f"{calib_data_path}/calib_note/flow.json")
        self.session = create_session(
            backend=backend,
            config={
                "task_type": "qubit",
                "username": username,
                "qids": qids,
                "note_path": str(note_path),
                "chip_id": chip_id,
            },
        )
        self.session.connect()

    def _ensure_task_in_workflow(self, task_name: str, task_type: str, qid: str) -> None:
        """Ensure task exists in TaskManager's workflow structure.

        Dynamically adds task to the workflow if it doesn't exist yet.
        This allows FlowSession to execute tasks on-demand without pre-building
        the entire workflow.

        Args:
            task_name: Name of the task
            task_type: Type of task ('qubit', 'coupling', 'global', 'system')
            qid: Qubit ID

        """
        from qdash.datamodel.task import (
            CouplingTaskModel,
            GlobalTaskModel,
            QubitTaskModel,
            SystemTaskModel,
        )

        # Check if task already exists
        if task_type == "qubit":
            if qid in self.task_manager.task_result.qubit_tasks:
                existing_tasks = [t.name for t in self.task_manager.task_result.qubit_tasks[qid]]
                if task_name in existing_tasks:
                    return
            # Add new qubit task
            task = QubitTaskModel(name=task_name, upstream_id="", qid=qid)
            self.task_manager.task_result.qubit_tasks.setdefault(qid, []).append(task)
        elif task_type == "coupling":
            if qid in self.task_manager.task_result.coupling_tasks:
                existing_tasks = [t.name for t in self.task_manager.task_result.coupling_tasks[qid]]
                if task_name in existing_tasks:
                    return
            # Add new coupling task
            task = CouplingTaskModel(name=task_name, upstream_id="", qid=qid)
            self.task_manager.task_result.coupling_tasks.setdefault(qid, []).append(task)
        elif task_type == "global":
            existing_tasks = [t.name for t in self.task_manager.task_result.global_tasks]
            if task_name in existing_tasks:
                return
            # Add new global task
            task = GlobalTaskModel(name=task_name, upstream_id="")
            self.task_manager.task_result.global_tasks.append(task)
        elif task_type == "system":
            existing_tasks = [t.name for t in self.task_manager.task_result.system_tasks]
            if task_name in existing_tasks:
                return
            # Add new system task
            task = SystemTaskModel(name=task_name, upstream_id="")
            self.task_manager.task_result.system_tasks.append(task)

        # Save updated workflow
        self.task_manager.save()

    def execute_task(
        self,
        task_name: str,
        qid: str,
        task_details: dict[str, Any] | None = None,
        upstream_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a calibration task with integrated save processing.

        This method leverages the refactored TaskManager.execute_task() which
        automatically handles all save operations including:
        - Output parameters
        - Figures and raw data
        - Task result history
        - Execution history
        - Calibration data updates

        Args:
            task_name: Name of the task to execute (e.g., 'CheckFreq')
            qid: Qubit ID to calibrate
            task_details: Optional task-specific configuration parameters
            upstream_id: Optional explicit upstream task_id for dependency tracking.
                If None, uses the last executed task_id for this qid.

        Returns:
            Dictionary containing the task's output parameters and task_id

        Example:
            ```python
            result = session.execute_task("CheckFreq", "0")
            print(f"Frequency: {result.get('qubit_frequency')}")

            # With explicit upstream_id for group execution
            result1 = session.execute_task("CheckRabi", "33")
            result2 = session.execute_task("CheckRabi", "32", upstream_id=result1["task_id"])
            ```

        """
        if task_details is None:
            task_details = {}

        # Ensure task_details has an entry for this task (can be empty dict)
        if task_name not in task_details:
            task_details[task_name] = {}

        # Generate task instance
        task_instances = generate_task_instances(
            task_names=[task_name],
            task_details=task_details,
            backend=self.backend,
        )

        task_instance = task_instances[task_name]
        task_type = task_instance.get_task_type()

        # Add task to workflow if not already present
        self._ensure_task_in_workflow(task_name, task_type, qid)

        # Reload execution manager to get latest state
        execution_manager = ExecutionManager(
            username=self.username,
            execution_id=self.execution_id,
            calib_data_path=self.execution_manager.calib_data_path,
        ).reload()

        # Create a new TaskManager for this specific execution
        # This ensures each execution has a separate task_result entry
        import uuid
        from copy import deepcopy

        execution_task_manager = TaskManager(
            username=self.username,
            execution_id=self.execution_id,
            qids=[qid],
            calib_dir=self.task_manager.calib_dir,
        )
        execution_task_manager.id = str(uuid.uuid4())

        # Copy current calibration data to the new task manager
        execution_task_manager.calib_data = deepcopy(self.task_manager.calib_data)
        execution_task_manager.controller_info = deepcopy(self.task_manager.controller_info)

        # Set upstream_id for sequential task dependency tracking
        # Priority: explicit upstream_id > last executed task for this qid > empty
        if upstream_id is not None:
            execution_task_manager._upstream_task_id = upstream_id
        else:
            execution_task_manager._upstream_task_id = self._last_executed_task_id_by_qid.get(qid, "")

        # Execute task with the dedicated task manager
        execution_manager, executed_task_manager = execute_dynamic_task_by_qid.with_options(
            timeout_seconds=task_instance.timeout,
            task_run_name=task_instance.name,
            log_prints=True,
        )(
            session=self.session,
            execution_manager=execution_manager,
            task_manager=execution_task_manager,
            task_instance=task_instance,
            qid=qid,
        )

        # Merge results back to main task_manager (for parameter access in future tasks)
        self.task_manager.calib_data.qubit.update(executed_task_manager.calib_data.qubit)
        self.task_manager.calib_data.coupling.update(executed_task_manager.calib_data.coupling)
        self.task_manager.controller_info.update(executed_task_manager.controller_info)

        # Update local execution manager
        self.execution_manager = execution_manager

        # Store the executed task's task_id for upstream tracking in next execution (per qid)
        executed_task = executed_task_manager.get_task(
            task_name=task_name, task_type=task_instance.get_task_type(), qid=qid
        )
        self._last_executed_task_id_by_qid[qid] = executed_task.task_id

        # Return output parameters from the executed task manager
        result = executed_task_manager.get_output_parameter_by_task_name(
            task_name,
            task_type=task_instance.get_task_type(),
            qid=qid,
        )

        # Add task_id to result for upstream tracking in group execution
        result["task_id"] = executed_task.task_id

        return result

    def get_parameter(self, qid: str, param_name: str) -> Any:
        """Get a calibration parameter value for a qubit.

        Args:
            qid: Qubit ID
            param_name: Parameter name (e.g., 'qubit_frequency')

        Returns:
            Parameter value, or None if not found

        Example:
            ```python
            freq = session.get_parameter("0", "qubit_frequency")
            ```

        """
        return self.execution_manager.calib_data.qubit.get(qid, {}).get(param_name)

    def set_parameter(self, qid: str, param_name: str, value: Any) -> None:
        """Set a calibration parameter value for a qubit.

        Args:
            qid: Qubit ID
            param_name: Parameter name
            value: Parameter value

        Example:
            ```python
            session.set_parameter("0", "qubit_frequency", 5.0)
            ```

        """
        if qid not in self.execution_manager.calib_data.qubit:
            self.execution_manager.calib_data.qubit[qid] = {}
        self.execution_manager.calib_data.qubit[qid][param_name] = value

    def finish_calibration(self, update_chip_history: bool = True) -> None:
        """Complete the calibration session and save final state.

        This method performs cleanup and finalization:
        - Marks the execution as complete
        - Updates ChipDocument and ChipHistoryDocument (if requested)
        - Releases the execution lock (if it was acquired)

        Args:
            update_chip_history: Whether to update ChipHistoryDocument (default: True)

        Example:
            ```python
            session.finish_calibration()
            ```

        """
        try:
            # Reload and complete execution
            self.execution_manager = self.execution_manager.reload().complete_execution()

            # Update chip history
            if update_chip_history:
                try:
                    chip_doc = ChipDocument.get_current_chip(username=self.username)
                    ChipHistoryDocument.create_history(chip_doc)
                except Exception:
                    # If chip history update fails, log but don't fail the calibration
                    pass

        finally:
            # Always release lock if we acquired it
            if self.use_lock and self._lock_acquired:
                ExecutionLockDocument.unlock()
                self._lock_acquired = False

    def fail_calibration(self, error_message: str = "") -> None:
        """Mark the calibration as failed and cleanup.

        This should be called in exception handlers to properly mark
        the execution as failed and release resources.

        Args:
            error_message: Description of the failure

        Example:
            ```python
            try:
                session.execute_task("CheckFreq", "0")
            except Exception as e:
                session.fail_calibration(str(e))
                raise
            ```

        """
        try:
            # Reload and mark as failed
            self.execution_manager = self.execution_manager.reload().fail_execution()
        finally:
            # Always release lock if we acquired it
            if self.use_lock and self._lock_acquired:
                ExecutionLockDocument.unlock()
                self._lock_acquired = False


# Global session storage for Prefect context
_current_session: FlowSession | None = None


def init_calibration(
    username: str,
    chip_id: str,
    qids: list[str],
    execution_id: str | None = None,
    backend: str = "qubex",
    name: str | None = None,
    flow_name: str | None = None,
    tags: list[str] | None = None,
    use_lock: bool = True,
    note: dict[str, Any] | None = None,
) -> FlowSession:
    """Initialize a calibration session for use in Prefect flows.

    This function creates and stores a FlowSession in the global context,
    making it accessible via get_session() throughout the flow.

    Args:
        username: Username for the session
        chip_id: Target chip ID
        qids: List of qubit IDs to calibrate (required for qubex initialization)
        execution_id: Unique execution identifier (e.g., "20240101-001").
            If None, auto-generates using current date and counter.
        backend: Backend type ('qubex' or 'fake')
        name: Human-readable name for the execution (deprecated, use flow_name instead).
            If None, auto-detects from Prefect flow name or defaults to "Python Flow Execution".
        flow_name: Flow name (file name without .py extension) for display in execution list.
            This takes precedence over 'name' parameter.
        tags: List of tags for categorization
        use_lock: Whether to use ExecutionLock to prevent concurrent calibrations
        note: Additional notes to store with execution

    Returns:
        Initialized FlowSession instance

    Example:
        ```python
        @flow
        def my_calibration(username, chip_id, qids, flow_name=None):
            # flow_name will be automatically injected by API
            session = init_calibration(username, chip_id, qids, flow_name=flow_name)
            # ... perform calibration tasks
            finish_calibration()
        ```

    """
    global _current_session  # noqa: PLW0603

    # Priority: flow_name > name > auto-detect from Prefect
    display_name = flow_name or name
    if display_name is None:
        try:
            from prefect.context import get_run_context

            context = get_run_context()
            flow_name_from_context = context.flow.name if hasattr(context, "flow") else None
            display_name = flow_name_from_context if flow_name_from_context else "Python Flow Execution"
        except Exception:
            # Fallback if context is not available (e.g., running outside Prefect)
            display_name = "Python Flow Execution"

    _current_session = FlowSession(
        username=username,
        chip_id=chip_id,
        qids=qids,
        execution_id=execution_id,
        backend=backend,
        name=display_name,
        tags=tags,
        use_lock=use_lock,
        note=note,
    )
    return _current_session


def get_session() -> FlowSession:
    """Get the current calibration session.

    Returns:
        Current FlowSession instance

    Raises:
        RuntimeError: If no session has been initialized

    Example:
        ```python
        session = get_session()
        result = session.execute_task("CheckFreq", "0")
        ```

    """
    if _current_session is None:
        msg = "No active calibration session. Call init_calibration() first."
        raise RuntimeError(msg)
    return _current_session


def finish_calibration() -> None:
    """Finish the current calibration session.

    This is a convenience wrapper around session.finish_calibration().

    Example:
        ```python
        @flow
        def my_flow():
            init_calibration(...)
            # ... calibration tasks
            finish_calibration()
        ```

    """
    session = get_session()
    session.finish_calibration()


def execute_schedule(
    tasks: list[str],
    schedule: ScheduleNode,
    task_details: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Execute calibration tasks according to a schedule definition.

    This function provides workflow orchestration similar to dispatch_cal_flow,
    but within Python Flow Editor. It supports SerialNode, ParallelNode (as sequential),
    and BatchNode schedules.

    Args:
        tasks: List of task names to execute
        schedule: Schedule definition (SerialNode, ParallelNode, or BatchNode)
        task_details: Optional task-specific configuration

    Returns:
        Dictionary mapping qubit IDs to their output parameters

    Note:
        ParallelNode is executed sequentially in Python Flow Editor.
        For true parallel execution via deployments, use dispatch_cal_flow.

    Example:
        ```python
        from qdash.datamodel.menu import SerialNode, ParallelNode

        # Serial execution of qubits
        schedule = SerialNode(serial=["0", "1", "2"])
        results = execute_schedule(
            tasks=["CheckFreq", "CheckRabi"],
            schedule=schedule
        )

        # Parallel schedule (executed sequentially in Python Flow)
        schedule = ParallelNode(parallel=["0", "1", "2"])
        results = execute_schedule(
            tasks=["CheckFreq", "CheckRabi"],
            schedule=schedule
        )

        # Nested schedule
        schedule = SerialNode(serial=[
            ParallelNode(parallel=["0", "1"]),
            SerialNode(serial=["2", "3"])
        ])
        results = execute_schedule(tasks=["CheckFreq"], schedule=schedule)
        ```

    """
    session = get_session()
    logger = get_run_logger()
    results: dict[str, dict[str, Any]] = {}

    if task_details is None:
        task_details = {}

    def _execute_qubits(qids: list[str]) -> None:
        """Execute all tasks for given qubits."""
        for qid in qids:
            if qid not in results:
                results[qid] = {}
            for task_name in tasks:
                task_result = session.execute_task(task_name, qid, task_details)
                results[qid].update(task_result)

    def _process_schedule(node: ScheduleNode | str) -> None:
        """Recursively process schedule nodes."""
        if isinstance(node, str):
            # Leaf node: single qubit ID
            _execute_qubits([node])
        elif isinstance(node, SerialNode):
            # Execute each sub-node sequentially
            logger.info(f"Executing SerialNode with {len(node.serial)} items")
            for sub_node in node.serial:
                _process_schedule(sub_node)
        elif isinstance(node, ParallelNode):
            # Note: In Python Flow Editor, this is executed sequentially
            # For true parallel execution, use dispatch_cal_flow
            logger.info(
                f"Executing ParallelNode with {len(node.parallel)} items "
                "(sequentially - use dispatch_cal_flow for true parallelism)"
            )
            for sub_node in node.parallel:
                _process_schedule(sub_node)
        elif isinstance(node, BatchNode):
            # Execute all qubits in batch
            logger.info(f"Executing BatchNode with qubits: {node.batch}")
            _execute_qubits(node.batch)

    # Start processing from root schedule
    _process_schedule(schedule)

    return results
