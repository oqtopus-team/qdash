"""CalService - High-level API for calibration workflows.

This module provides a clean, service-oriented API for calibration tasks.
It wraps low-level session management and provides simple methods for
common calibration patterns.

Example:
    Basic calibration flow:

    ```python
    from prefect import flow
    from qdash.workflow.flow import CalService

    @flow
    def simple_calibration(username, chip_id, qids, flow_name=None, project_id=None):
        cal = CalService(username, chip_id, flow_name=flow_name, project_id=project_id)
        return cal.run(qids=qids, tasks=["CheckRabi", "CreateHPIPulse", "CheckHPIPulse"])
    ```
"""

import json
import logging
from pathlib import Path
from typing import Any

import pendulum
from prefect import get_run_logger, task

logger = logging.getLogger(__name__)
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_history import ChipHistoryDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.user import UserDocument
from qdash.workflow.caltasks.active_protocols import generate_task_instances
from qdash.workflow.engine.backend.factory import create_backend
from qdash.workflow.engine.calibration.execution.manager import ExecutionManager
from qdash.workflow.engine.calibration.params_updater import get_params_updater
from qdash.workflow.engine.calibration.prefect_tasks import execute_dynamic_task_by_qid
from qdash.workflow.engine.calibration.task.manager import TaskManager
from qdash.workflow.flow.github import GitHubIntegration, GitHubPushConfig


def generate_execution_id(username: str, chip_id: str, project_id: str | None = None) -> str:
    """Generate a unique execution ID based on the current date and an execution index.

    This function creates execution IDs in the format YYYYMMDD-NNN, where:
    - YYYYMMDD is the current date in JST timezone
    - NNN is a zero-padded 3-digit counter for that day

    Args:
        username: Username for the execution
        chip_id: Chip ID for the execution
        project_id: Project ID for the execution (optional)

    Returns:
        Generated execution ID (e.g., "20240101-001")

    Example:
        ```python
        exec_id = generate_execution_id("alice", "chip_1")
        print(exec_id)  # "20240123-001"
        ```

    """
    date_str = pendulum.now(tz="Asia/Tokyo").date().strftime("%Y%m%d")
    execution_index = ExecutionCounterDocument.get_next_index(date_str, username, chip_id, project_id=project_id)
    return f"{date_str}-{execution_index:03d}"


class CalService:
    """High-level API for calibration workflows.

    Provides a clean, intuitive interface for common calibration patterns
    with automatic session management and error handling.

    Attributes:
        username: Username for the calibration session
        chip_id: Target chip ID
        flow_name: Flow name for tracking
        project_id: Project ID for multi-tenancy

    Example:
        Simple API usage:

        ```python
        cal = CalService("alice", "64Qv3")
        results = cal.run(qids=["0", "1"], tasks=["CheckRabi", "CreateHPIPulse"])
        ```

        Advanced low-level access:

        ```python
        cal = CalService("alice", "64Qv3", qids=["0", "1"])
        result = cal.execute_task("CheckFreq", "0")
        cal.finish_calibration()
        ```
    """

    def __init__(
        self,
        username: str,
        chip_id: str,
        qids: list[str] | None = None,
        execution_id: str | None = None,
        backend_name: str = "qubex",
        name: str | None = None,
        flow_name: str | None = None,
        tags: list[str] | None = None,
        use_lock: bool = True,
        note: dict[str, Any] | None = None,
        enable_github_pull: bool | None = None,
        enable_github: bool = True,
        github_push_config: GitHubPushConfig | None = None,
        muxes: list[int] | None = None,
        project_id: str | None = None,
    ) -> None:
        """Initialize the calibration service.

        Supports two usage patterns:

        1. High-level API (lazy initialization):
           ```python
           cal = CalService("alice", "64Qv3")
           cal.run(qids=["0", "1"], tasks=["CheckRabi"])
           ```

        2. Low-level API (immediate initialization):
           ```python
           cal = CalService("alice", "64Qv3", qids=["0", "1"])
           cal.execute_task("CheckRabi", "0")
           cal.finish_calibration()
           ```

        Args:
            username: Username for the session
            chip_id: Target chip ID
            qids: List of qubit IDs to calibrate. If None, session is lazily initialized.
            execution_id: Unique execution identifier (e.g., "20240101-001").
                If None, auto-generates using current date and counter.
            backend_name: Backend type, either 'qubex' or 'fake' (default: 'qubex')
            name: Human-readable name for the execution (deprecated, use flow_name)
            flow_name: Flow name for display in execution list (auto-injected by API)
            tags: List of tags for categorization
            use_lock: Whether to use ExecutionLock to prevent concurrent calibrations (default: True)
            note: Additional notes to store with execution (default: {})
            enable_github_pull: Whether to pull latest config from GitHub before starting
            enable_github: Enable GitHub integration (default: True). Sets both pull and push.
            github_push_config: Configuration for GitHub push operations
            muxes: List of MUX IDs for system-level tasks like CheckSkew (default: None)
            project_id: Project ID for multi-tenancy support. If None, auto-resolved
                from username's default_project_id.

        Raises:
            RuntimeError: If use_lock=True and another calibration is already running

        """
        self.username = username
        self.chip_id = chip_id
        self.qids = qids
        self.muxes = muxes
        self.backend_name = backend_name
        self.use_lock = use_lock
        self._lock_acquired = False
        self._last_executed_task_id_by_qid: dict[str, str] = {}  # Track last task_id per qid

        # Store flow_name (priority: flow_name > name)
        self.flow_name = flow_name or name

        # GitHub configuration
        self.enable_github = enable_github
        # enable_github_pull: explicit value > enable_github default
        self._enable_github_pull = enable_github_pull if enable_github_pull is not None else enable_github

        # Auto-resolve project_id from username if not provided
        # This works because only owners can run calibrations (1 user = 1 project policy)
        if project_id is None:
            user = UserDocument.find_one({"username": username}).run()
            if user and user.default_project_id:
                project_id = user.default_project_id
                logger.info(f"Auto-resolved project_id={project_id} from user={username}")
            else:
                raise ValueError(
                    f"Could not resolve project_id for user={username}. "
                    f"User found: {user is not None}, "
                    f"default_project_id: {user.default_project_id if user else 'N/A'}. "
                    f"Either provide project_id explicitly or ensure user has default_project_id set."
                )
        self.project_id = project_id

        # Session state
        self._initialized = False
        self.execution_id = execution_id
        self.execution_manager = None
        self.task_manager = None
        self.backend = None
        self.github_integration = None
        self.github_push_config = github_push_config

        # If qids provided, initialize immediately (low-level API mode)
        if qids is not None:
            self._initialize(qids, tags, note)

    def _initialize(
        self,
        qids: list[str],
        tags: list[str] | None = None,
        note: dict[str, Any] | None = None,
    ) -> None:
        """Initialize session with given qids (internal method).

        Args:
            qids: List of qubit IDs to calibrate
            tags: List of tags for categorization
            note: Additional notes to store with execution

        """
        if self._initialized:
            return

        self.qids = qids

        # Auto-generate execution_id if not provided
        if self.execution_id is None:
            self.execution_id = generate_execution_id(self.username, self.chip_id, project_id=self.project_id)

        # Initialize GitHub integration
        self.github_integration = GitHubIntegration(
            username=self.username,
            chip_id=self.chip_id,
            execution_id=self.execution_id,
        )

        # Setup github_push_config if not provided
        if self.github_push_config is None and self.enable_github:
            from qdash.workflow.flow.github import ConfigFileType

            self.github_push_config = GitHubPushConfig(
                enabled=self.enable_github,
                file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS],
            )
        elif self.github_push_config is None:
            self.github_push_config = GitHubPushConfig()

        # Acquire lock if requested
        if self.use_lock:
            if ExecutionLockDocument.get_lock_status(project_id=self.project_id):
                msg = "Calibration is already running. Cannot start a new session."
                raise RuntimeError(msg)
            ExecutionLockDocument.lock(project_id=self.project_id)
            self._lock_acquired = True

        # Wrap all initialization in try/except to ensure lock is released on failure
        try:
            self._initialize_session(
                username=self.username,
                chip_id=self.chip_id,
                qids=qids,
                execution_id=self.execution_id,
                backend_name=self.backend_name,
                name=self.flow_name or "Python Flow Execution",
                tags=tags,
                note=note,
                enable_github_pull=self._enable_github_pull,
                muxes=self.muxes,
                project_id=self.project_id,
            )
            self._initialized = True
        except Exception:
            # Release lock if initialization fails
            if self._lock_acquired:
                ExecutionLockDocument.unlock(project_id=self.project_id)
                self._lock_acquired = False
            raise

    def _initialize_session(
        self,
        username: str,
        chip_id: str,
        qids: list[str],
        execution_id: str,
        backend_name: str,
        name: str,
        tags: list[str] | None,
        note: dict[str, Any] | None,
        enable_github_pull: bool,
        muxes: list[int] | None,
        project_id: str | None = None,
    ) -> None:
        """Initialize session components after lock acquisition.

        This method is separated from __init__ to enable proper exception handling
        with lock release on failure.

        Args:
            username: Username for the session
            chip_id: Target chip ID
            qids: List of qubit IDs
            execution_id: Execution identifier
            backend_name: Backend type
            name: Human-readable name
            tags: Tags for categorization
            note: Additional notes
            enable_github_pull: Whether to pull from GitHub
            muxes: MUX IDs for system-level tasks
            project_id: Project ID for multi-tenancy support

        """
        # Set default tags and note
        # Use name (which is flow_name or display_name) as default tag
        if tags is None:
            tags = [name]
        if note is None:
            note = {}

        # Setup calibration directory
        date_str, index = execution_id.split("-")
        user_path = f"/app/calib_data/{username}"
        classifier_dir = f"{user_path}/.classifier"
        calib_data_path = f"{user_path}/{date_str}/{index}"

        # Create directory structure (matching create_directory_task behavior)
        Path(calib_data_path).mkdir(parents=True, exist_ok=True)
        Path(classifier_dir).mkdir(exist_ok=True)
        Path(f"{calib_data_path}/task").mkdir(exist_ok=True)
        Path(f"{calib_data_path}/fig").mkdir(exist_ok=True)
        Path(f"{calib_data_path}/calib").mkdir(exist_ok=True)
        Path(f"{calib_data_path}/calib_note").mkdir(exist_ok=True)

        # Pull config from GitHub if requested
        if enable_github_pull:
            logger = get_run_logger()
            if GitHubIntegration.check_credentials():
                commit_id = self.github_integration.pull_config()
                if commit_id:
                    note["config_commit_id"] = commit_id
            else:
                logger.warning("GitHub credentials not configured, skipping pull")

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
                project_id=project_id,
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
        # Use task_manager.id for note_path (same as setup_calibration)
        note_path = f"{calib_data_path}/calib_note/{self.task_manager.id}.json"
        session_config = {
            "task_type": "qubit",
            "username": username,
            "qids": qids,
            "note_path": note_path,
            "chip_id": chip_id,
            "classifier_dir": classifier_dir,
        }

        # Add muxes if provided
        if muxes is not None:
            session_config["muxes"] = muxes

        self.backend = create_backend(
            backend=backend_name,
            config=session_config,
        )

        # Save calibration_note before connecting (loads parameter overrides)
        if self.backend.name == "qubex":
            self.backend.save_note(
                username=username,
                chip_id=chip_id,
                calib_dir=calib_data_path,
                execution_id=execution_id,
                task_manager_id=self.task_manager.id,
                project_id=self.project_id,
            )

        self.backend.connect()

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

    def _get_relevant_qubit_ids(self, qid: str) -> list[str]:
        """Get the list of qubit IDs relevant to a task execution.

        For qubit tasks, this returns just the target qid.
        For coupling tasks (e.g., "0-1"), this returns both individual qubits.

        Args:
            qid: The qubit or coupling ID

        Returns:
            List of relevant qubit IDs

        """
        if "-" in qid:
            # Coupling ID like "0-1" - extract individual qubit IDs
            return qid.split("-")
        return [qid]

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
            backend=self.backend_name,
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
            project_id=self.project_id,
        ).reload()

        # Create a new TaskManager for this specific execution
        # This ensures each execution has a separate task_result entry
        import uuid
        from copy import deepcopy

        from qdash.datamodel.task import CalibDataModel

        execution_task_manager = TaskManager(
            username=self.username,
            execution_id=self.execution_id,
            qids=[qid],
            calib_dir=self.task_manager.calib_dir,
        )
        execution_task_manager.id = str(uuid.uuid4())

        # Copy only the relevant calibration data for this qid to reduce overhead
        # For qubit tasks: copy data for the target qid
        # For coupling tasks: qid is like "0-1", copy both individual qubit data and coupling data
        relevant_qubit_ids = self._get_relevant_qubit_ids(qid)
        execution_task_manager.calib_data = CalibDataModel(
            qubit={
                q: deepcopy(self.task_manager.calib_data.qubit[q])
                for q in relevant_qubit_ids
                if q in self.task_manager.calib_data.qubit
            },
            coupling={
                c: deepcopy(self.task_manager.calib_data.coupling[c])
                for c in [qid]
                if qid in self.task_manager.calib_data.coupling
            },
        )
        # controller_info is typically small, deepcopy is acceptable
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
            backend=self.backend,
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

    def record_stage_result(self, stage_name: str, result: dict[str, Any]) -> None:
        """Record the result of a calibration stage for tracking and history.

        This method stores stage-specific results in the execution note, which is
        persisted to MongoDB and visible in the execution history. Useful for:
        - Recording dynamically determined values during execution
        - Tracking intermediate decisions and metrics
        - Multi-stage calibration workflows with clear stage boundaries

        Args:
            stage_name: Name of the stage (e.g., "stage1_frequency_scan", "stage2_optimization")
            result: Dictionary containing stage results (any JSON-serializable data)
                Common fields: status, metrics, decisions, qubits, timestamps, etc.

        Example:
            ```python
            # Stage 1: Frequency characterization
            stage1_results = {}
            for qid in qids:
                freq_result = session.execute_task("CheckFreq", qid)
                stage1_results[qid] = {
                    "frequency": freq_result.get("qubit_frequency"),
                    "quality": "high" if freq_result.get("contrast", 0) > 0.8 else "low"
                }

            # Record stage 1 results with decision logic
            session.record_stage_result("stage1_frequency_scan", {
                "status": "completed",
                "qubits": stage1_results,
                "decision": "proceed_to_rabi" if all(r["quality"] == "high" for r in stage1_results.values()) else "retry_frequency"
            })

            # Stage 2: Use stage 1 results to determine next actions
            stage1_data = session.get_stage_result("stage1_frequency_scan")
            if stage1_data["decision"] == "proceed_to_rabi":
                for qid in qids:
                    session.execute_task("CheckRabi", qid)
            ```

        """
        logger = get_run_logger()

        # Initialize stage_results dict in note if it doesn't exist
        if "stage_results" not in self.execution_manager.note:
            self.execution_manager.note["stage_results"] = {}

        # Store stage result with timestamp
        self.execution_manager.note["stage_results"][stage_name] = {
            "result": result,
            "timestamp": pendulum.now(tz="Asia/Tokyo").to_iso8601_string(),
        }

        # Persist to database immediately
        self.execution_manager.save()
        logger.info(f"Recorded stage result for '{stage_name}'")

    def get_stage_result(self, stage_name: str) -> dict[str, Any] | None:
        """Get the recorded result of a previous calibration stage.

        Args:
            stage_name: Name of the stage to retrieve

        Returns:
            Stage result dictionary, or None if stage not found

        Example:
            ```python
            # Retrieve stage 1 results to determine stage 2 logic
            stage1_data = session.get_stage_result("stage1_frequency_scan")
            if stage1_data and stage1_data["decision"] == "proceed_to_rabi":
                # Execute stage 2 tasks
                pass
            ```

        """
        stage_results = self.execution_manager.note.get("stage_results", {})
        stage_data = stage_results.get(stage_name)

        if stage_data:
            return stage_data["result"]
        return None

    def _sync_backend_params_before_push(self, logger) -> None:
        """Sync recent calibration results into backend YAML params prior to GitHub push."""
        updater_instance = get_params_updater(self.backend, self.chip_id)
        if updater_instance is None:
            return

        for qid, params in self.execution_manager.calib_data.qubit.items():
            if "-" in qid or not params:
                continue
            try:
                updater_instance.update(qid, params)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to sync params for qid={qid}: {exc}")

    def finish_calibration(
        self,
        update_chip_history: bool = True,
        push_to_github: bool | None = None,
        export_note_to_file: bool = False,
    ) -> dict[str, Any] | None:
        """Complete the calibration session and save final state.

        This method performs cleanup and finalization:
        - Marks the execution as complete
        - Updates ChipDocument and ChipHistoryDocument (if requested)
        - Exports calibration note to file (if requested)
        - Pushes results to GitHub (if configured)
        - Releases the execution lock (if it was acquired)

        Args:
            update_chip_history: Whether to update ChipHistoryDocument (default: True)
            push_to_github: Override github_push_config.enabled if specified
            export_note_to_file: Whether to export calibration note to local file (default: False)
                Useful for debugging or archival purposes. The note is always available
                in MongoDB regardless of this setting.

        Returns:
            Push results dictionary if push was performed, else None

        Example:
            ```python
            # Basic usage
            session.finish_calibration()

            # With explicit push override
            push_results = session.finish_calibration(push_to_github=True)
            print(f"Pushed files: {push_results}")

            # Export note to file for debugging
            session.finish_calibration(export_note_to_file=True)
            ```

        """
        logger = get_run_logger()
        push_results = None

        try:
            # Reload and complete execution
            self.execution_manager = self.execution_manager.reload().complete_execution()

            # Update chip history for the specific chip being calibrated
            if update_chip_history:
                try:
                    # Use chip_id from session instead of "current" chip to avoid
                    # updating wrong chip's history when calibrating older chips
                    chip_doc = ChipDocument.get_chip_by_id(username=self.username, chip_id=self.chip_id)
                    if chip_doc is not None:
                        ChipHistoryDocument.create_history(chip_doc)
                    else:
                        logger.warning(
                            f"Chip '{self.chip_id}' not found for user '{self.username}', " "skipping history update"
                        )
                except Exception as e:
                    # If chip history update fails, log but don't fail the calibration
                    logger.warning(f"Failed to update chip history: {e}")

            # Export calibration note to file if requested
            if export_note_to_file:
                try:
                    from qdash.dbmodel.calibration_note import CalibrationNoteDocument

                    latest_doc = CalibrationNoteDocument.find_one(
                        {
                            "username": self.username,
                            "task_id": self.task_manager.id,
                            "execution_id": self.execution_id,
                            "chip_id": self.chip_id,
                        }
                    ).run()

                    if latest_doc:
                        note_path = Path(
                            f"{self.execution_manager.calib_data_path}/calib_note/{self.task_manager.id}.json"
                        )
                        note_path.parent.mkdir(parents=True, exist_ok=True)
                        note_path.write_text(json.dumps(latest_doc.note, indent=2, ensure_ascii=False))
                        logger.info(f"Exported calibration note to {note_path}")
                    else:
                        logger.warning(f"No calibration note found for task_id={self.task_manager.id}")
                except Exception as e:
                    logger.error(f"Failed to export calibration note: {e}")

            # Push to GitHub if configured
            should_push = push_to_github if push_to_github is not None else self.github_push_config.enabled

            if should_push:
                self._sync_backend_params_before_push(logger)
                if GitHubIntegration.check_credentials():
                    try:
                        push_results = self.github_integration.push_files(self.github_push_config)

                        # Store push results in execution note
                        if push_results:
                            self.execution_manager.note["github_push_results"] = push_results
                            self.execution_manager.save()
                            logger.info(f"GitHub push completed: {push_results}")
                    except Exception as e:
                        logger.error(f"Failed to push to GitHub: {e}")
                        push_results = {"error": str(e)}
                else:
                    logger.warning("GitHub credentials not configured, skipping push")

        finally:
            # Always release lock if we acquired it
            if self.use_lock and self._lock_acquired:
                ExecutionLockDocument.unlock(project_id=self.project_id)
                self._lock_acquired = False

        return push_results

    def fail_calibration(self, error_message: str = "") -> None:
        """Mark the calibration as failed and cleanup.

        This should be called in exception handlers to properly mark
        the execution as failed and release resources.

        Args:
            error_message: Description of the failure

        Example:
            ```python
            try:
                cal.execute_task("CheckFreq", "0")
            except Exception as e:
                cal.fail_calibration(str(e))
                raise
            ```

        """
        try:
            # Reload and mark as failed
            if self.execution_manager:
                self.execution_manager = self.execution_manager.reload().fail_execution()
        finally:
            # Always release lock if we acquired it
            if self.use_lock and self._lock_acquired:
                ExecutionLockDocument.unlock(project_id=self.project_id)
                self._lock_acquired = False
            self._initialized = False

    # =========================================================================
    # High-level API Methods
    # =========================================================================

    def run(self, groups: list[list[str]], tasks: list[str]) -> dict:
        """Run calibration with group-based parallelism.

        Groups execute in PARALLEL, qubits within each group execute SEQUENTIALLY.

        Args:
            groups: List of qubit groups (e.g., [["0", "1"], ["2", "3"]])
            tasks: List of task names to execute

        Returns:
            Results dictionary keyed by qubit ID

        Example:
            ```python
            cal = CalService("alice", "64Qv3")
            results = cal.run(
                groups=[["0", "1"], ["2", "3"]],
                tasks=["CheckRabi", "CreateHPIPulse"]
            )
            # Group0: Q0 → Q1 (sequential)  ─┐
            #                                 ├─ PARALLEL
            # Group1: Q2 → Q3 (sequential)  ─┘
            ```
        """
        logger = get_run_logger()
        all_qids = [qid for group in groups for qid in group]
        logger.info(f"Running calibration: {len(groups)} groups, {len(all_qids)} qubits")

        try:
            self._initialize(all_qids)

            futures = [_execute_group.submit(self, group, tasks) for group in groups]
            results_list = [f.result() for f in futures]

            results = {}
            for r in results_list:
                results.update(r)

            self.finish_calibration()
            return results

        except Exception as e:
            logger.error(f"Calibration failed: {e}")
            self.fail_calibration(str(e))
            raise

    def run_full_chip(
        self,
        mux_ids: list[int] | None = None,
        exclude_qids: list[str] | None = None,
        tasks_1q: list[str] | None = None,
        tasks_2q: list[str] | None = None,
        mode: str = "synchronized",
        fidelity_threshold: float = 0.90,
        max_parallel_ops: int = 10,
    ) -> dict:
        """Run full chip calibration (1-qubit + 2-qubit).

        Performs complete chip calibration with automatic quality filtering.

        Args:
            mux_ids: MUX IDs to calibrate (default: all 16)
            exclude_qids: Qubit IDs to exclude
            tasks_1q: 1-qubit tasks (default: standard suite)
            tasks_2q: 2-qubit tasks (default: standard suite)
            mode: "synchronized" or "scheduled"
            fidelity_threshold: Minimum X90 fidelity for 2Q candidates
            max_parallel_ops: Max parallel CR operations

        Returns:
            Results with "1qubit" and "2qubit" keys

        Example:
            ```python
            cal = CalService("alice", "64Qv3")
            results = cal.run_full_chip(mux_ids=[0, 1, 2, 3])
            ```
        """
        from qdash.workflow.flow.scheduled import (
            calibrate_one_qubit_scheduled,
            calibrate_one_qubit_synchronized,
            calibrate_two_qubit_scheduled,
            extract_candidate_qubits,
        )

        logger = get_run_logger()

        if mux_ids is None:
            mux_ids = list(range(16))
        if exclude_qids is None:
            exclude_qids = []
        if tasks_1q is None:
            tasks_1q = [
                "CheckRabi",
                "CreateHPIPulse",
                "CheckHPIPulse",
                "CreatePIPulse",
                "CheckPIPulse",
                "CheckT1",
                "CheckT2Echo",
                "CreateDRAGHPIPulse",
                "CheckDRAGHPIPulse",
                "CreateDRAGPIPulse",
                "CheckDRAGPIPulse",
                "ReadoutClassification",
                "RandomizedBenchmarking",
                "X90InterleavedRandomizedBenchmarking",
            ]
        if tasks_2q is None:
            tasks_2q = ["CheckCrossResonance", "CreateZX90", "CheckZX90", "CheckBellState"]

        logger.info(f"Running full chip calibration: mode={mode}")

        # Stage 1: 1-qubit calibration
        if mode == "synchronized":
            results_1q = calibrate_one_qubit_synchronized(
                username=self.username,
                chip_id=self.chip_id,
                mux_ids=mux_ids,
                exclude_qids=exclude_qids,
                tasks=tasks_1q,
                flow_name=self.flow_name,
                project_id=self.project_id,
            )
        else:
            results_1q = calibrate_one_qubit_scheduled(
                username=self.username,
                chip_id=self.chip_id,
                mux_ids=mux_ids,
                exclude_qids=exclude_qids,
                tasks=tasks_1q,
                flow_name=self.flow_name,
                project_id=self.project_id,
            )

        # Stage 2: Extract candidates
        candidates = extract_candidate_qubits(results_1q, fidelity_threshold)
        logger.info(f"1-qubit success: {len(candidates)} qubits")

        if len(candidates) == 0:
            logger.warning("No candidates, skipping 2-qubit")
            return {"1qubit": results_1q, "2qubit": {}}

        # Stage 3: 2-qubit calibration
        results_2q = calibrate_two_qubit_scheduled(
            username=self.username,
            chip_id=self.chip_id,
            candidate_qubits=candidates,
            tasks=tasks_2q,
            flow_name=self.flow_name,
            project_id=self.project_id,
            max_parallel_ops=max_parallel_ops,
        )

        return {"1qubit": results_1q, "2qubit": results_2q}

    def sweep(
        self,
        qids: list[str],
        task: str,
        params: list[dict[str, Any]],
    ) -> list[dict]:
        """Run parameter sweep over a task.

        Executes the same task multiple times with different parameter values.

        Args:
            qids: Qubit IDs to calibrate
            task: Task name to execute
            params: List of parameter dictionaries for each iteration

        Returns:
            List of results for each iteration

        Example:
            ```python
            cal = CalService("alice", "64Qv3")
            results = cal.sweep(
                qids=["0", "1"],
                task="CheckQubitSpectroscopy",
                params=[
                    {"readout_amplitude": {"value": 0.05}},
                    {"readout_amplitude": {"value": 0.10}},
                    {"readout_amplitude": {"value": 0.15}},
                ]
            )
            ```
        """
        logger = get_run_logger()
        logger.info(f"Running sweep: {task}, {len(params)} iterations")

        try:
            self._initialize(qids)

            all_results = []
            for i, param_values in enumerate(params):
                logger.info(f"Iteration {i + 1}/{len(params)}: {param_values}")
                task_details = {task: {"input_parameters": param_values}}

                iteration_results = {}
                for qid in qids:
                    try:
                        result = self.execute_task(task, qid, task_details=task_details)
                        iteration_results[qid] = {"status": "success", "result": result}
                    except Exception as e:
                        iteration_results[qid] = {"status": "failed", "error": str(e)}

                all_results.append(
                    {
                        "iteration": i,
                        "params": param_values,
                        "results": iteration_results,
                    }
                )

            self.finish_calibration()
            return all_results

        except Exception as e:
            logger.error(f"Sweep failed: {e}")
            self.fail_calibration(str(e))
            raise

    def two_qubit(
        self,
        pairs: list[tuple[str, str]],
        tasks: list[str] | None = None,
    ) -> dict:
        """Run 2-qubit coupling calibration.

        Calibrates coupling between qubit pairs.

        Args:
            pairs: List of (control, target) qubit pairs
            tasks: 2-qubit task names (default: standard suite)

        Returns:
            Results keyed by coupling ID (e.g., "0-1")

        Example:
            ```python
            cal = CalService("alice", "64Qv3")
            results = cal.two_qubit(
                pairs=[("0", "1"), ("2", "3")]
            )
            ```
        """
        logger = get_run_logger()

        if tasks is None:
            tasks = ["CheckCrossResonance", "CreateZX90", "CheckZX90", "CheckBellState"]

        coupling_qids = [f"{c}-{t}" for c, t in pairs]
        all_qids = list(set(q for pair in pairs for q in pair))
        logger.info(f"Running 2-qubit calibration: {len(pairs)} pairs")

        try:
            self._initialize(all_qids)

            futures = [_execute_coupling.submit(self, qid, tasks) for qid in coupling_qids]
            results = {qid: f.result() for qid, f in zip(coupling_qids, futures)}

            self.finish_calibration()
            return results

        except Exception as e:
            logger.error(f"Calibration failed: {e}")
            self.fail_calibration(str(e))
            raise

    def check_skew(self, muxes: list[int] | None = None) -> dict:
        """Run system-level skew check.

        Args:
            muxes: MUX IDs to check (default: all except 3)

        Returns:
            CheckSkew task result

        Example:
            ```python
            cal = CalService("alice", "64Qv3")
            result = cal.check_skew(muxes=[0, 1, 2])
            ```
        """
        logger = get_run_logger()

        if muxes is None:
            muxes = [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]

        logger.info(f"Running CheckSkew: {len(muxes)} MUX channels")

        try:
            self.muxes = muxes
            self._initialize([])

            result = self.execute_task(
                "CheckSkew",
                qid="",
                task_details={"CheckSkew": {"muxes": muxes}},
            )

            self.finish_calibration()
            return result

        except Exception as e:
            logger.error(f"CheckSkew failed: {e}")
            self.fail_calibration(str(e))
            raise


# Internal task functions for parallel execution
@task
def _execute_group(cal: "CalService", qids: list[str], tasks: list[str]) -> dict:
    """Execute tasks for a group of qubits (internal task)."""
    results = {}
    for qid in qids:
        try:
            result = {}
            for task_name in tasks:
                result[task_name] = cal.execute_task(task_name, qid)
            result["status"] = "success"
        except Exception as e:
            result = {"status": "failed", "error": str(e)}
        results[qid] = result
    return results


@task
def _execute_coupling(cal: "CalService", coupling_qid: str, tasks: list[str]) -> dict:
    """Execute tasks for a coupling pair (internal task)."""
    try:
        result = {}
        for task_name in tasks:
            result[task_name] = cal.execute_task(task_name, coupling_qid)
        result["status"] = "success"
    except Exception as e:
        result = {"status": "failed", "error": str(e)}
    return result


# =============================================================================
# Internal Session Management (for scheduled.py)
# =============================================================================

from qdash.workflow.flow.context import (
    clear_current_session,
    get_current_session,
    set_current_session,
)


def init_calibration(
    username: str,
    chip_id: str,
    qids: list[str],
    execution_id: str | None = None,
    backend_name: str = "qubex",
    flow_name: str | None = None,
    tags: list[str] | None = None,
    use_lock: bool = True,
    note: dict[str, Any] | None = None,
    enable_github_pull: bool = False,
    github_push_config: GitHubPushConfig | None = None,
    muxes: list[int] | None = None,
    project_id: str | None = None,
) -> CalService:
    """Initialize a session and set it in global context (internal use)."""
    session = CalService(
        username=username,
        chip_id=chip_id,
        qids=qids,
        execution_id=execution_id,
        backend_name=backend_name,
        flow_name=flow_name,
        tags=tags,
        use_lock=use_lock,
        note=note,
        enable_github_pull=enable_github_pull,
        github_push_config=github_push_config,
        muxes=muxes,
        project_id=project_id,
    )
    set_current_session(session)
    return session


def get_session() -> CalService:
    """Get the current session from global context (internal use)."""
    session = get_current_session()
    if session is None:
        msg = "No active calibration session."
        raise RuntimeError(msg)
    return session


def finish_calibration(
    update_chip_history: bool = True,
    push_to_github: bool | None = None,
    export_note_to_file: bool = False,
) -> dict[str, Any] | None:
    """Finish the current session and clear from global context (internal use)."""
    session = get_session()
    result = session.finish_calibration(
        update_chip_history=update_chip_history,
        push_to_github=push_to_github,
        export_note_to_file=export_note_to_file,
    )
    clear_current_session()
    return result
