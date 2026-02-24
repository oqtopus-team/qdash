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

from __future__ import annotations

import contextlib
import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from qdash.repository.protocols import (
        ExecutionCounterRepository,
        ExecutionLockRepository,
        UserRepository,
    )
    from qdash.workflow.engine.backend.base import BaseBackend
    from qdash.workflow.engine.execution.service import ExecutionService
    from qdash.workflow.engine.task.context import TaskContext
    from qdash.workflow.service.steps import Step
    from qdash.workflow.service.targets import Target

from prefect import get_run_logger
from qdash.common.backend_config import get_default_backend
from qdash.common.datetime_utils import now
from qdash.workflow.engine import CalibConfig, CalibOrchestrator
from qdash.workflow.engine.params_updater import get_params_updater
from qdash.workflow.service.execution_id import generate_execution_id
from qdash.workflow.service.github import GitHubIntegration, GitHubPushConfig

logger = logging.getLogger(__name__)

__all__ = [
    "CalibService",
    "generate_execution_id",
    # Re-exported for backward compatibility (used by strategy.py, two_qubit.py)
    "finish_calibration",
    "get_session",
    "init_calibration",
]


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
        backend_name: str | None = None,
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
        skip_execution: bool = False,
        default_run_parameters: dict[str, Any] | None = None,
        source_execution_id: str | None = None,
        *,
        user_repo: UserRepository | None = None,
        lock_repo: ExecutionLockRepository | None = None,
        counter_repo: ExecutionCounterRepository | None = None,
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
            backend_name: Backend type, either 'qubex' or 'fake' (default: from backend.yaml)
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
            skip_execution: Skip Execution document creation (for wrapper/parent sessions
                where child sessions will create their own Executions). Default: False.
            user_repo: Repository for user lookup (DI). If None, uses MongoUserRepository.
            lock_repo: Repository for lock operations (DI). If None, uses MongoExecutionLockRepository.
            counter_repo: Repository for counter operations (DI). If None, uses MongoExecutionCounterRepository.

        Raises:
            RuntimeError: If use_lock=True and another calibration is already running

        """
        self.username = username
        self.chip_id = chip_id
        self.qids = qids
        self.muxes = muxes
        self.backend_name = backend_name or get_default_backend()
        self.use_lock = use_lock
        self.skip_execution = skip_execution
        self.default_run_parameters = default_run_parameters or {}
        self._lock_acquired = False

        # Resolve source_execution_id from Prefect runtime context if not provided
        if source_execution_id is None:
            source_execution_id = self._read_source_execution_id_from_context()
        self.source_execution_id = source_execution_id

        # Store injected repositories for later use
        self._user_repo = user_repo
        self._lock_repo = lock_repo
        self._counter_repo = counter_repo

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
            if self._user_repo is None:
                from qdash.repository import MongoUserRepository

                self._user_repo = MongoUserRepository()

            default_project_id = self._user_repo.get_default_project_id(username)
            if default_project_id:
                project_id = default_project_id
                logger.info(f"Auto-resolved project_id={project_id} from user={username}")
            else:
                raise ValueError(
                    f"Could not resolve project_id for user={username}. "
                    f"default_project_id is not set. "
                    f"Either provide project_id explicitly or ensure user has default_project_id set."
                )
        self.project_id = project_id

        # Auto-load default_run_parameters from flow document if not explicitly provided
        if not self.default_run_parameters and self.flow_name:
            self._load_default_run_parameters()
        logger.debug(
            "CalibService.__init__ flow_name=%s default_run_parameters=%s",
            self.flow_name,
            self.default_run_parameters,
        )

        # Session state
        self._initialized = False
        self.execution_id: str | None = execution_id
        self._orchestrator: CalibOrchestrator | None = None
        self.github_integration: GitHubIntegration | None = None
        self.github_push_config: GitHubPushConfig | None = github_push_config
        self.tags: list[str] | None = tags
        self.note: dict[str, Any] | None = note

        # If qids provided, initialize immediately (low-level API mode)
        if qids is not None:
            self._initialize(qids, tags, note)

    @staticmethod
    def _read_source_execution_id_from_context() -> str | None:
        """Try to read source_execution_id from Prefect flow run parameters."""
        try:
            from prefect.context import get_run_context

            ctx = get_run_context()
            if ctx and ctx.flow_run and ctx.flow_run.parameters:
                value = ctx.flow_run.parameters.get("source_execution_id")
                return str(value) if value is not None else None
        except Exception:
            logger.debug("No Prefect run context available for source_execution_id")
        return None

    def _load_default_run_parameters(self) -> None:
        """Load default_run_parameters from the flow document in MongoDB."""
        try:
            from qdash.repository.flow import MongoFlowRepository

            flow_repo = MongoFlowRepository()
            flow_name = self.flow_name or ""
            flow = flow_repo.find_by_user_and_name(self.username, flow_name, self.project_id)
            if flow and flow.default_run_parameters:
                self.default_run_parameters = flow.default_run_parameters
                logger.debug(
                    "Loaded default_run_parameters from flow '%s': %s",
                    self.flow_name,
                    flow.default_run_parameters,
                )
        except Exception:
            logger.warning(
                f"Failed to load default_run_parameters for flow '{self.flow_name}'",
                exc_info=True,
            )

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
                self.username,
                self.chip_id,
                project_id=self.project_id,
                counter_repo=self._counter_repo,
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
            if self._lock_repo is None:
                from qdash.repository import MongoExecutionLockRepository

                self._lock_repo = MongoExecutionLockRepository()

            if self._lock_repo.is_locked(project_id=self.project_id):
                msg = "Calibration is already running. Cannot start a new session."
                raise RuntimeError(msg)
            self._lock_repo.lock(project_id=self.project_id)
            self._lock_acquired = True

        # Wrap all initialization in try/except to ensure lock is released on failure
        try:
            # Create CalibConfig
            logger.debug("CalibConfig default_run_parameters=%s", self.default_run_parameters)
            config = CalibConfig(
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
                skip_execution=self.skip_execution,
                default_run_parameters=self.default_run_parameters,
            )

            # Create snapshot loader if re-executing from a previous execution
            snapshot_loader = None
            if self.source_execution_id:
                from qdash.workflow.engine.task.snapshot_loader import (
                    SnapshotParameterLoader,
                )

                snapshot_loader = SnapshotParameterLoader(
                    source_execution_id=self.source_execution_id,
                    project_id=self.project_id,
                )
                logger.info(
                    "Created SnapshotParameterLoader for source_execution_id=%s",
                    self.source_execution_id,
                )

            # Create and initialize CalibOrchestrator
            self._orchestrator = CalibOrchestrator(
                config=config,
                github_integration=self.github_integration,
                snapshot_loader=snapshot_loader,
            )
            self._orchestrator.initialize()
            self._initialized = True
        except Exception:
            # Release lock if initialization fails
            if self._lock_acquired and self._lock_repo is not None:
                self._lock_repo.unlock(project_id=self.project_id)
                self._lock_acquired = False
            raise

    @property
    def execution_service(self) -> ExecutionService | None:
        """Get the ExecutionService from CalibOrchestrator."""
        if self._orchestrator is None:
            return None
        # Access private attribute to avoid RuntimeError from property
        return self._orchestrator._execution_service

    @execution_service.setter
    def execution_service(self, value: ExecutionService | None) -> None:
        """Set execution_service (for backward compatibility with reload)."""
        if self._orchestrator is not None:
            self._orchestrator._execution_service = value

    @property
    def task_context(self) -> TaskContext | None:
        """Get the TaskContext from CalibOrchestrator."""
        if self._orchestrator is None:
            return None
        # Access private attribute to avoid RuntimeError from property
        return self._orchestrator._task_context

    @property
    def backend(self) -> BaseBackend | None:
        """Get the Backend from CalibOrchestrator."""
        if self._orchestrator is None:
            return None
        # Access private attribute to avoid RuntimeError from property
        return self._orchestrator._backend

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
        assert self._orchestrator is not None, "Session not initialized"
        result: dict[str, Any] = self._orchestrator.run_task(
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
        assert self.execution_service is not None, "ExecutionService not initialized"
        return self.execution_service.calib_data.qubit.get(qid, {}).get(param_name)

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
        assert self.execution_service is not None, "ExecutionService not initialized"
        if qid not in self.execution_service.calib_data.qubit:
            self.execution_service.calib_data.qubit[qid] = {}
        self.execution_service.calib_data.qubit[qid][param_name] = value

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
        assert self.execution_service is not None, "ExecutionService not initialized"
        logger = get_run_logger()

        # Record stage result using the structured ExecutionNote API
        timestamp = now()
        self.execution_service.note.record_stage(stage_name, result, timestamp)

        # Persist to database immediately
        self.execution_service.save()
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
        assert self.execution_service is not None, "ExecutionService not initialized"
        stage_result = self.execution_service.note.get_stage(stage_name)

        if stage_result:
            return dict(stage_result.result)
        return None

    def _finalize_stale_running_tasks(
        self,
        logger: Any,
        message: str = "Task was still running when execution completed",
    ) -> None:
        """Finalize any tasks still in RUNNING status for this execution.

        During Dask parallel execution, tasks may remain in RUNNING status if:
        - The MongoDB write for final status fails
        - Prefect task timeout prevents the finally block from completing
        - A Dask worker process crashes
        - There is latency between Dask future resolution and MongoDB write completion

        This method retries several times with progressive backoff delays to handle
        the latency case, then marks any remaining running tasks as FAILED before
        the execution status is updated, ensuring data consistency.

        Args:
            logger: Logger instance for output
            message: Failure message to set on stale tasks

        """
        if self.execution_service is None or self.execution_id is None:
            return

        project_id = self.execution_service.project_id
        if project_id is None:
            return

        try:
            from qdash.repository import MongoTaskResultHistoryRepository

            repo = MongoTaskResultHistoryRepository()

            # Progressive backoff delays (in seconds) to handle MongoDB write latency
            # from Dask workers. Starts short to minimize latency in the common case,
            # then increases to handle slower edge cases.
            retry_delays = [0.5, 1, 2, 3, 5]

            for attempt, delay in enumerate(retry_delays):
                count = repo.finalize_running_tasks(
                    project_id=project_id,
                    execution_id=self.execution_id,
                    message=message,
                )
                if count > 0:
                    logger.warning(
                        f"[attempt {attempt + 1}/{len(retry_delays)}] "
                        f"Finalized {count} stale task(s) still in RUNNING status "
                        f"for execution {self.execution_id}"
                    )
                    if attempt < len(retry_delays) - 1:
                        # Wait before re-checking in case more tasks
                        # are still being written by Dask workers
                        time.sleep(delay)
                else:
                    if attempt == 0:
                        logger.info(
                            f"All tasks in terminal state for execution {self.execution_id}"
                        )
                    break
        except Exception as e:
            logger.warning(f"Failed to finalize stale running tasks: {e}")

    def _sync_backend_params_before_push(self, logger: Any) -> None:
        """Sync recent calibration results into backend YAML params prior to GitHub push."""
        assert self.execution_service is not None, "ExecutionService not initialized"
        updater_instance = get_params_updater(self.backend, self.chip_id)
        if updater_instance is None:
            return

        for qid, params in self.execution_service.calib_data.qubit.items():
            if "-" in qid or not params:
                continue
            try:
                updater_instance.update(qid, params)
            except Exception as exc:
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
            # Skip finalization if this session doesn't own the execution.
            # This covers two cases:
            # 1. Wrapper mode (no ExecutionService was created)
            # 2. Isolated Dask worker sessions (skip_execution=True) that
            #    may have borrowed the parent's ExecutionService via
            #    _run_prefect_task — they must NOT complete/modify it.
            if self.execution_service is None or self.skip_execution:
                logger.info("Skipping finalization (no owned Execution)")
                return None

            assert self.task_context is not None, "TaskContext not initialized"
            assert self.github_push_config is not None, "GitHubPushConfig not initialized"

            # Finalize any tasks still in RUNNING status before completing execution.
            self._finalize_stale_running_tasks(logger)

            # Reload and complete execution
            self.execution_service = self.execution_service.reload().complete()

            if update_chip_history:
                self._update_chip_history(logger)

            if export_note_to_file:
                self._export_calibration_note(logger)

            push_results = self._push_to_github_if_configured(logger, push_to_github)

        finally:
            self._release_lock_if_acquired()

        return push_results

    def _update_chip_history(self, logger: Any) -> None:
        """Update chip history for the specific chip being calibrated."""
        try:
            from qdash.repository import (
                MongoChipHistoryRepository,
                MongoChipRepository,
            )

            chip_repo = MongoChipRepository()
            chip = chip_repo.get_chip_by_id(username=self.username, chip_id=self.chip_id)
            if chip is not None:
                history_repo = MongoChipHistoryRepository()
                history_repo.create_history(username=self.username, chip_id=self.chip_id)
            else:
                logger.warning(
                    f"Chip '{self.chip_id}' not found for user '{self.username}', "
                    "skipping history update"
                )
        except Exception as e:
            logger.warning(f"Failed to update chip history: {e}")

    def _export_calibration_note(self, logger: Any) -> None:
        """Export calibration note to a local JSON file."""
        assert self.task_context is not None
        assert self.execution_service is not None
        try:
            from qdash.repository import MongoCalibrationNoteRepository

            repo = MongoCalibrationNoteRepository()
            latest_note = repo.find_one(
                username=self.username,
                task_id=self.task_context.id,
                execution_id=self.execution_id,
                chip_id=self.chip_id,
            )

            if latest_note:
                note_path = Path(
                    f"{self.execution_service.calib_data_path}/calib_note/{self.task_context.id}.json"
                )
                note_path.parent.mkdir(parents=True, exist_ok=True)
                note_path.write_text(json.dumps(latest_note.note, indent=2, ensure_ascii=False))
                logger.info(f"Exported calibration note to {note_path}")
            else:
                logger.warning(f"No calibration note found for task_id={self.task_context.id}")
        except Exception as e:
            logger.error(f"Failed to export calibration note: {e}")

    def _push_to_github_if_configured(
        self, logger: Any, push_to_github: bool | None
    ) -> dict[str, Any] | None:
        """Push results to GitHub if configured."""
        assert self.github_push_config is not None
        assert self.execution_service is not None

        should_push = (
            push_to_github if push_to_github is not None else self.github_push_config.enabled
        )
        if not should_push:
            return None

        self._sync_backend_params_before_push(logger)
        if GitHubIntegration.check_credentials() and self.github_integration is not None:
            try:
                push_results = self.github_integration.push_files(self.github_push_config)
                if push_results:
                    self.execution_service.note.github_push_results = push_results
                    self.execution_service.save()
                    logger.info(f"GitHub push completed: {push_results}")
                return push_results
            except Exception as e:
                logger.error(f"Failed to push to GitHub: {e}")
                return {"error": str(e)}
        else:
            logger.warning("GitHub credentials not configured, skipping push")
            return None

    def _release_lock_if_acquired(self) -> None:
        """Release the execution lock if it was acquired by this session."""
        if self.use_lock and self._lock_acquired and self._lock_repo is not None:
            self._lock_repo.unlock(project_id=self.project_id)
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
                cal.execute_task("CheckFreq", "0")
            except Exception as e:
                cal.fail_calibration(str(e))
                raise
            ```

        """
        run_logger = get_run_logger()
        try:
            # Skip if this session doesn't own the execution
            if self.skip_execution:
                return

            # Finalize any tasks still in RUNNING status before failing execution
            if self.execution_service:
                self._finalize_stale_running_tasks(
                    run_logger,
                    message="Task was still running when execution failed",
                )
            # Reload and mark as failed
            if self.execution_service:
                self.execution_service = self.execution_service.reload().fail()
        finally:
            self._release_lock_if_acquired()
            self._initialized = False

    # =========================================================================
    # High-level API Methods
    # =========================================================================

    def run(
        self,
        targets: Target,
        steps: Sequence[Step],
    ) -> dict[str, Any]:
        """Run calibration pipeline with targets and steps.

        Args:
            targets: Target specification (MuxTargets, QubitTargets, etc.)
            steps: List of Step objects defining the calibration pipeline

        Returns:
            Results dictionary. Structure depends on the steps executed.

        Example:
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
        """
        return self._run_pipeline(targets, steps)

    def _run_pipeline(
        self,
        targets: Target,
        steps: Sequence[Step],
    ) -> dict[str, Any]:
        """Execute a calibration pipeline with steps.

        Args:
            targets: Target specification
            steps: List of steps to execute

        Returns:
            Dictionary with typed results from each step
        """
        from qdash.workflow.service.session_context import (
            clear_current_session,
            set_current_session,
        )
        from qdash.workflow.service.steps import Pipeline, StepContext

        logger = get_run_logger()

        # Set this CalibService as the current session for task execution
        set_current_session(self)

        try:
            # Initialize session if not already initialized
            qids = targets.to_qids(self.chip_id)
            if not self._initialized:
                self._initialize(qids, self.tags, self.note)

            # Validate pipeline dependencies
            pipeline = Pipeline(steps)
            logger.info(f"Starting calibration pipeline with {len(pipeline)} steps")

            # Initialize context
            ctx = StepContext()
            ctx.candidate_qids = qids

            # Execute steps sequentially
            for i, step in enumerate(pipeline):
                logger.info(f"Step {i + 1}/{len(pipeline)}: {step.name}")
                try:
                    ctx = step.execute(self, targets, ctx)
                except Exception as e:
                    logger.error(f"Step {step.name} failed: {e}")
                    raise

            logger.info("Pipeline completed successfully")

            # Finalize execution (mark as completed, update chip history)
            self.finish_calibration()
        except Exception:
            # Mark execution as failed on error and release lock (best effort)
            with contextlib.suppress(Exception):
                self.fail_calibration()
            raise
        finally:
            # Clear session when done
            clear_current_session()

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


# =============================================================================
# Internal Session Management (re-exported for backward compatibility)
# =============================================================================

from qdash.workflow.service._internal.session_helpers import (
    finish_calibration,
    get_session,
    init_calibration,
)
