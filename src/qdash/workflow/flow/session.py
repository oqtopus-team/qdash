"""Python Flow Editor - Session management and helper functions for custom calibration flows.

This module provides a high-level API for creating custom calibration workflows
using Python code. It leverages the refactored TaskManager architecture with
integrated save processing.

Example:
    Basic calibration flow:

    ```python
    from prefect import flow
    from qdash.workflow.flow import init_calibration, calibrate_qubits_parallel, finish_calibration

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

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pendulum
from prefect import get_run_logger
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_history import ChipHistoryDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.workflow.caltasks.active_protocols import generate_task_instances
from qdash.workflow.engine.backend.factory import create_backend
from qdash.workflow.engine.calibration.execution.manager import ExecutionManager
from qdash.workflow.engine.calibration.params_updater import get_params_updater
from qdash.workflow.engine.calibration.prefect_tasks import execute_dynamic_task_by_qid
from qdash.workflow.engine.calibration.task.manager import TaskManager
from qdash.workflow.flow.github import GitHubIntegration, GitHubPushConfig

if TYPE_CHECKING:
    from qdash.workflow.flow.config import FlowSessionConfig


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
        backend_name: Backend type ('qubex' or 'fake')
        execution_manager: Manages execution state and history
        backend: Backend instance for device communication

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
        backend_name: str = "qubex",
        name: str = "Python Flow Execution",
        tags: list[str] | None = None,
        use_lock: bool = True,
        note: dict[str, Any] | None = None,
        enable_github_pull: bool = False,
        github_push_config: GitHubPushConfig | None = None,
        muxes: list[int] | None = None,
    ) -> None:
        """Initialize a new calibration flow session.

        Args:
            username: Username for the session
            chip_id: Target chip ID
            qids: List of qubit IDs to calibrate (required for qubex initialization)
            execution_id: Unique execution identifier (e.g., "20240101-001").
                If None, auto-generates using current date and counter.
            backend_name: Backend type, either 'qubex' or 'fake' (default: 'qubex')
            name: Human-readable name for the execution (default: 'Python Flow Execution')
            tags: List of tags for categorization (default: ['python_flow'])
            use_lock: Whether to use ExecutionLock to prevent concurrent calibrations (default: True)
            note: Additional notes to store with execution (default: {})
            enable_github_pull: Whether to pull latest config from GitHub before starting (default: False)
            github_push_config: Configuration for GitHub push operations (default: disabled)
            muxes: List of MUX IDs for system-level tasks like CheckSkew (default: None)

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

        # Auto-generate execution_id if not provided
        if execution_id is None:
            execution_id = generate_execution_id(username, chip_id)

        self.execution_id = execution_id

        # Initialize GitHub integration
        self.github_integration = GitHubIntegration(
            username=username,
            chip_id=chip_id,
            execution_id=execution_id,
        )
        self.github_push_config = github_push_config or GitHubPushConfig()
        self.enable_github_pull = enable_github_pull

        # Acquire lock if requested
        if use_lock:
            if ExecutionLockDocument.get_lock_status():
                msg = "Calibration is already running. Cannot start a new session."
                raise RuntimeError(msg)
            ExecutionLockDocument.lock()
            self._lock_acquired = True

        # Wrap all initialization in try/except to ensure lock is released on failure
        try:
            self._initialize_session(
                username=username,
                chip_id=chip_id,
                qids=qids,
                execution_id=execution_id,
                backend_name=backend_name,
                name=name,
                tags=tags,
                note=note,
                enable_github_pull=enable_github_pull,
                muxes=muxes,
            )
        except Exception:
            # Release lock if initialization fails
            if self._lock_acquired:
                ExecutionLockDocument.unlock()
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
                ExecutionLockDocument.unlock()
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

    @classmethod
    def from_config(cls, config: "FlowSessionConfig") -> "FlowSession":
        """Create a FlowSession from a FlowSessionConfig.

        This factory method provides a clean way to create FlowSession instances
        from immutable configuration objects.

        Args:
            config: FlowSessionConfig with all session parameters

        Returns:
            New FlowSession instance

        Example:
            ```python
            from qdash.workflow.flow.config import FlowSessionConfig

            config = FlowSessionConfig.create(
                username="alice",
                chip_id="chip_1",
                qids=["0", "1", "2"],
                backend_name="qubex",
            )
            session = FlowSession.from_config(config)
            ```
        """

        return cls(
            username=config.username,
            chip_id=config.chip_id,
            qids=list(config.qids),
            execution_id=config.execution_id,
            backend_name=config.backend_name,
            name=config.name,
            tags=list(config.tags) if config.tags else None,
            use_lock=config.use_lock,
            note=dict(config.note) if config.note else None,
            enable_github_pull=config.enable_github_pull,
            github_push_config=config.github_push_config,
            muxes=list(config.muxes) if config.muxes else None,
        )


# Global session storage for Prefect context
# Note: Using SessionContext for thread-safe management while maintaining
# backward compatibility with direct _current_session access
from qdash.workflow.flow.context import (
    clear_current_session,
    get_current_session,
    set_current_session,
)

_current_session: FlowSession | None = None  # Backward compatibility alias


def init_calibration(
    username: str,
    chip_id: str,
    qids: list[str],
    execution_id: str | None = None,
    backend_name: str = "qubex",
    name: str | None = None,
    flow_name: str | None = None,
    tags: list[str] | None = None,
    use_lock: bool = True,
    note: dict[str, Any] | None = None,
    enable_github_pull: bool = False,
    github_push_config: GitHubPushConfig | None = None,
    muxes: list[int] | None = None,
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
        backend_name: Backend type ('qubex' or 'fake')
        name: Human-readable name for the execution (deprecated, use flow_name instead).
            If None, auto-detects from Prefect flow name or defaults to "Python Flow Execution".
        flow_name: Flow name (file name without .py extension) for display in execution list.
            This takes precedence over 'name' parameter.
        tags: List of tags for categorization
        use_lock: Whether to use ExecutionLock to prevent concurrent calibrations
        note: Additional notes to store with execution
        enable_github_pull: Whether to pull latest config from GitHub before starting (default: False)
        github_push_config: Configuration for GitHub push operations (default: disabled)
        muxes: List of MUX IDs for system-level tasks like CheckSkew (default: None)

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

        ```python
        # With GitHub integration
        from qdash.workflow.flow import GitHubPushConfig, ConfigFileType

        @flow
        def calibration_with_github(username, chip_id, qids):
            session = init_calibration(
                username, chip_id, qids,
                enable_github_pull=True,
                github_push_config=GitHubPushConfig(
                    enabled=True,
                    file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.PROPS]
                )
            )
            # ... calibration tasks
            finish_calibration()
        ```

        ```python
        # For system-level tasks like CheckSkew
        @flow
        def skew_calibration(username, chip_id, muxes):
            session = init_calibration(
                username, chip_id, qids=[],
                muxes=muxes
            )
            # ... execute CheckSkew task
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

    session = FlowSession(
        username=username,
        chip_id=chip_id,
        qids=qids,
        execution_id=execution_id,
        backend_name=backend_name,
        name=display_name,
        tags=tags,
        use_lock=use_lock,
        note=note,
        enable_github_pull=enable_github_pull,
        github_push_config=github_push_config,
        muxes=muxes,
    )

    # Use SessionContext for thread-safe management
    set_current_session(session)
    _current_session = session  # Backward compatibility
    return session


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
    session = get_current_session()
    if session is None:
        msg = "No active calibration session. Call init_calibration() first."
        raise RuntimeError(msg)
    return session


def finish_calibration(
    update_chip_history: bool = True,
    push_to_github: bool | None = None,
    export_note_to_file: bool = False,
) -> dict[str, Any] | None:
    """Finish the current calibration session.

    This is a convenience wrapper around session.finish_calibration().

    Args:
        update_chip_history: Whether to update ChipHistoryDocument (default: True)
        push_to_github: Override github_push_config.enabled if specified
        export_note_to_file: Whether to export calibration note to local file (default: False)

    Returns:
        Push results dictionary if push was performed, else None

    Example:
        ```python
        @flow
        def my_flow():
            init_calibration(...)
            # ... calibration tasks
            finish_calibration()

            # With file export for debugging
            finish_calibration(export_note_to_file=True)
        ```

    """
    global _current_session  # noqa: PLW0603

    session = get_session()
    result = session.finish_calibration(
        update_chip_history=update_chip_history,
        push_to_github=push_to_github,
        export_note_to_file=export_note_to_file,
    )

    # Clear session after completion
    clear_current_session()
    _current_session = None  # Backward compatibility

    return result
