"""CalibService - High-level API for calibration workflows.

This module provides a clean, service-oriented API for calibration tasks.
It wraps low-level session management and provides a step-based pipeline
approach for building calibration workflows.

Example:
    Step-based calibration flow:

    ```python
    from prefect import flow
    from qdash.workflow.service import CalibService
    from qdash.workflow.service.targets import MuxTargets
    from qdash.workflow.service.steps import OneQubitCheck, FilterByStatus, OneQubitFineTune

    @flow
    def calibration_flow(username, chip_id, flow_name=None, project_id=None):
        cal = CalibService(username, chip_id, flow_name=flow_name, project_id=project_id)
        targets = MuxTargets([0, 1, 2, 3])
        return cal.run(targets, steps=[
            OneQubitCheck(),
            FilterByStatus(),
            OneQubitFineTune(),
        ])
    ```
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qdash.workflow.service.steps import Step
    from qdash.workflow.service.targets import Target

import pendulum
from prefect import get_run_logger

from qdash.workflow.service._internal.prefect_tasks import (
    execute_group as _execute_group,
)

logger = logging.getLogger(__name__)
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_history import ChipHistoryDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.user import UserDocument
from qdash.workflow.engine.backend.base import BaseBackend
from qdash.workflow.engine.calibration.execution.manager import ExecutionManager
from qdash.workflow.engine.calibration.params_updater import get_params_updater
from qdash.workflow.engine.calibration.session import SessionConfig, SessionManager
from qdash.workflow.engine.calibration.task.manager import TaskManager
from qdash.workflow.service.github import GitHubIntegration, GitHubPushConfig


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
    execution_index = ExecutionCounterDocument.get_next_index(
        date_str, username, chip_id, project_id=project_id
    )
    return f"{date_str}-{execution_index:03d}"


class CalibService:
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
        cal = CalibService("alice", "64Qv3")
        results = cal.run(qids=["0", "1"], tasks=["CheckRabi", "CreateHPIPulse"])
        ```

        Advanced low-level access:

        ```python
        cal = CalibService("alice", "64Qv3", qids=["0", "1"])
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
           cal = CalibService("alice", "64Qv3")
           cal.run(qids=["0", "1"], tasks=["CheckRabi"])
           ```

        2. Low-level API (immediate initialization):
           ```python
           cal = CalibService("alice", "64Qv3", qids=["0", "1"])
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

        # Store flow_name (priority: flow_name > name)
        self.flow_name = flow_name or name

        # GitHub configuration
        self.enable_github = enable_github
        # enable_github_pull: explicit value > enable_github default
        self._enable_github_pull = (
            enable_github_pull if enable_github_pull is not None else enable_github
        )

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
        self.execution_id: str | None = execution_id
        self._session_manager: SessionManager | None = None
        self.github_integration: GitHubIntegration | None = None
        self.github_push_config: GitHubPushConfig | None = github_push_config

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
            self.execution_id = generate_execution_id(
                self.username, self.chip_id, project_id=self.project_id
            )

        # Initialize GitHub integration
        self.github_integration = GitHubIntegration(
            username=self.username,
            chip_id=self.chip_id,
            execution_id=self.execution_id,
        )

        # Setup github_push_config if not provided
        if self.github_push_config is None and self.enable_github:
            from qdash.workflow.service.github import ConfigFileType

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
            # Create SessionConfig
            config = SessionConfig(
                username=self.username,
                chip_id=self.chip_id,
                qids=qids,
                execution_id=self.execution_id,
                backend_name=self.backend_name,
                flow_name=self.flow_name,
                tags=tags,
                note=note,
                muxes=self.muxes,
                project_id=self.project_id,
                enable_github_pull=self._enable_github_pull,
            )

            # Create and initialize SessionManager
            self._session_manager = SessionManager(
                config=config,
                github_integration=self.github_integration,
            )
            self._session_manager.initialize()
            self._initialized = True
        except Exception:
            # Release lock if initialization fails
            if self._lock_acquired:
                ExecutionLockDocument.unlock(project_id=self.project_id)
                self._lock_acquired = False
            raise

    @property
    def execution_manager(self) -> ExecutionManager | None:
        """Get the ExecutionManager from SessionManager."""
        if self._session_manager is None:
            return None
        return self._session_manager.execution_manager

    @execution_manager.setter
    def execution_manager(self, value: ExecutionManager | None) -> None:
        """Set execution_manager (for backward compatibility with reload)."""
        if self._session_manager is not None:
            self._session_manager._execution_manager = value

    @property
    def task_manager(self) -> TaskManager | None:
        """Get the TaskManager from SessionManager."""
        if self._session_manager is None:
            return None
        return self._session_manager.task_manager

    @property
    def backend(self) -> BaseBackend | None:
        """Get the Backend from SessionManager."""
        if self._session_manager is None:
            return None
        return self._session_manager.backend

    def execute_task(
        self,
        task_name: str,
        qid: str,
        task_details: dict[str, Any] | None = None,
        upstream_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a calibration task with integrated save processing.

        Args:
            task_name: Name of the task to execute (e.g., 'CheckFreq')
            qid: Qubit ID to calibrate
            task_details: Optional task-specific configuration parameters
            upstream_id: Optional explicit upstream task_id for dependency tracking

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
        assert self._session_manager is not None, "Session not initialized"
        result: dict[str, Any] = self._session_manager.execute_task(
            task_name, qid, task_details, upstream_id
        )
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
        assert self.execution_manager is not None, "ExecutionManager not initialized"
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
        assert self.execution_manager is not None, "ExecutionManager not initialized"
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
        assert self.execution_manager is not None, "ExecutionManager not initialized"
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
        assert self.execution_manager is not None, "ExecutionManager not initialized"
        stage_results = self.execution_manager.note.get("stage_results", {})
        stage_data = stage_results.get(stage_name)

        if stage_data:
            return dict(stage_data["result"])
        return None

    def _sync_backend_params_before_push(self, logger: Any) -> None:
        """Sync recent calibration results into backend YAML params prior to GitHub push."""
        assert self.execution_manager is not None, "ExecutionManager not initialized"
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
        assert self.execution_manager is not None, "ExecutionManager not initialized"
        assert self.task_manager is not None, "TaskManager not initialized"
        assert self.github_push_config is not None, "GitHubPushConfig not initialized"
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
                    chip_doc = ChipDocument.get_chip_by_id(
                        username=self.username, chip_id=self.chip_id
                    )
                    if chip_doc is not None:
                        ChipHistoryDocument.create_history(chip_doc)
                    else:
                        logger.warning(
                            f"Chip '{self.chip_id}' not found for user '{self.username}', "
                            "skipping history update"
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
                        note_path.write_text(
                            json.dumps(latest_doc.note, indent=2, ensure_ascii=False)
                        )
                        logger.info(f"Exported calibration note to {note_path}")
                    else:
                        logger.warning(
                            f"No calibration note found for task_id={self.task_manager.id}"
                        )
                except Exception as e:
                    logger.error(f"Failed to export calibration note: {e}")

            # Push to GitHub if configured
            should_push = (
                push_to_github if push_to_github is not None else self.github_push_config.enabled
            )

            if should_push:
                self._sync_backend_params_before_push(logger)
                if GitHubIntegration.check_credentials() and self.github_integration is not None:
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

    def run(
        self,
        targets: "Target | list[list[str]]",
        steps: "list[Step] | None" = None,
        tasks: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run calibration pipeline with targets and steps.

        This is the primary API for running calibration workflows. Supports two modes:

        1. **Step-based (recommended)**: Define calibration as a series of steps
        2. **Legacy group-based**: Direct qubit groups with task list

        Args:
            targets: Either a Target object (MuxTargets, QubitTargets, etc.)
                     or a list of qubit groups for legacy mode
            steps: List of Step objects defining the calibration pipeline.
                   If provided, `tasks` is ignored.
            tasks: Task list for legacy mode (only used if steps is None)

        Returns:
            Results dictionary. Structure depends on the steps executed.

        Example (Step-based - recommended):
            ```python
            from qdash.workflow.service import CalibService
            from qdash.workflow.service.targets import MuxTargets
            from qdash.workflow.service.steps import (
                OneQubitCheck,
                OneQubitFineTune,
                FilterByFidelity,
                TwoQubitCalibration,
            )

            cal = CalibService("alice", "64Qv3")
            targets = MuxTargets([0, 1, 2, 3])

            results = cal.run(targets, steps=[
                OneQubitCheck(),
                OneQubitFineTune(),
                FilterByFidelity(threshold=0.9),
                TwoQubitCalibration(),
            ])
            ```

        Example (Legacy group-based):
            ```python
            cal = CalibService("alice", "64Qv3")
            results = cal.run(
                targets=[["0", "1"], ["2", "3"]],
                tasks=["CheckRabi", "CreateHPIPulse"],
            )
            ```
        """
        from qdash.workflow.service.targets import Target

        # Dispatch based on argument types
        if isinstance(targets, Target):
            if steps is None:
                raise ValueError("steps must be provided when using Target")
            return self._run_pipeline(targets, steps)
        else:
            # Legacy mode: targets is list[list[str]]
            if tasks is None:
                raise ValueError("tasks must be provided for legacy group-based mode")
            return self._run_groups(targets, tasks)

    def _run_pipeline(
        self,
        targets: "Target",
        steps: "list[Step]",
    ) -> dict[str, Any]:
        """Execute a calibration pipeline with steps.

        Args:
            targets: Target specification
            steps: List of steps to execute

        Returns:
            Dictionary with typed results from each step
        """
        from qdash.workflow.service.steps import Pipeline, StepContext

        logger = get_run_logger()

        # Validate pipeline dependencies
        pipeline = Pipeline(steps)
        logger.info(f"Starting calibration pipeline with {len(pipeline)} steps")

        # Initialize context
        ctx = StepContext()
        ctx.candidate_qids = targets.to_qids(self.chip_id)

        # Execute steps sequentially
        for i, step in enumerate(pipeline):
            logger.info(f"Step {i + 1}/{len(pipeline)}: {step.name}")
            try:
                ctx = step.execute(self, targets, ctx)
            except Exception as e:
                logger.error(f"Step {step.name} failed: {e}")
                raise

        logger.info("Pipeline completed successfully")

        # Build results from typed context fields
        results: dict[str, Any] = {
            "candidate_qids": ctx.candidate_qids,
            "candidate_couplings": ctx.candidate_couplings,
        }
        if ctx.one_qubit_check is not None:
            results["one_qubit_check"] = ctx.one_qubit_check
        if ctx.one_qubit_fine_tune is not None:
            results["one_qubit_fine_tune"] = ctx.one_qubit_fine_tune
        if ctx.two_qubit is not None:
            results["two_qubit"] = ctx.two_qubit
        if ctx.skew_check is not None:
            results["skew_check"] = ctx.skew_check
        if ctx.filters:
            results["filters"] = ctx.filters
        if ctx.metadata:
            results["metadata"] = ctx.metadata

        return results

    def _run_groups(
        self,
        groups: list[list[str]],
        tasks: list[str],
    ) -> dict[str, Any]:
        """Run calibration with group-based parallelism (legacy mode).

        Groups execute in PARALLEL, qubits within each group execute SEQUENTIALLY.

        Args:
            groups: List of qubit groups (e.g., [["0", "1"], ["2", "3"]])
            tasks: List of task names to execute

        Returns:
            Results dictionary keyed by qubit ID
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

    def check_skew(self, muxes: list[int] | None = None) -> dict[str, Any]:
        """Run system-level skew check.

        Args:
            muxes: MUX IDs to check (default: all except 3)

        Returns:
            CheckSkew task result

        Example:
            ```python
            cal = CalibService("alice", "64Qv3")
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


# =============================================================================
# Internal Session Management (for scheduled.py and strategy.py)
# =============================================================================

from qdash.workflow.service.context import (
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
) -> CalibService:
    """Initialize a session and set it in global context (internal use)."""
    session = CalibService(
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


def get_session() -> CalibService:
    """Get the current session from global context (internal use)."""
    session = get_current_session()
    if session is None:
        msg = "No active calibration session."
        raise RuntimeError(msg)
    assert isinstance(session, CalibService), "Session must be a CalibService instance"
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
