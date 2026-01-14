"""Calibration orchestrator for workflow execution.

This module handles the lifecycle of a calibration session:
- Directory structure creation
- ExecutionService, TaskContext, Backend initialization
- Session cleanup and finalization
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from prefect import get_run_logger
from qdash.workflow.engine.backend.factory import create_backend
from qdash.workflow.engine.execution.service import ExecutionService
from qdash.workflow.engine.task.context import TaskContext
from qdash.workflow.engine.task.history_recorder import TaskHistoryRecorder

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.base import BaseBackend
    from qdash.workflow.engine.config import CalibConfig
    from qdash.workflow.service.github import GitHubIntegration


class CalibOrchestrator:
    """Orchestrates the lifecycle of a calibration session.

    This class handles:
    - Directory structure creation
    - ExecutionService, TaskContext, Backend initialization
    - Session cleanup and finalization

    Example:
        ```python
        config = CalibConfig(
            username="alice",
            chip_id="64Qv3",
            qids=["0", "1"],
            execution_id="20240101-001",
        )
        orchestrator = CalibOrchestrator(config)
        orchestrator.initialize()

        # Use orchestrator components
        orchestrator.execution_service.save()
        orchestrator.task_context.get_task(...)
        orchestrator.backend.connect()
        ```
    """

    def __init__(
        self,
        config: CalibConfig,
        github_integration: GitHubIntegration | None = None,
    ) -> None:
        """Initialize the session manager.

        Args:
            config: Session configuration
            github_integration: Optional GitHub integration for config pull
        """
        self.config = config
        self.github_integration = github_integration

        # Session components (initialized in initialize())
        self._execution_service: ExecutionService | None = None
        self._task_context: TaskContext | None = None
        self._backend: BaseBackend | None = None
        self._initialized = False

        # Task execution state
        self._last_executed_task_id_by_qid: dict[str, str] = {}

    @property
    def execution_service(self) -> ExecutionService:
        """Get the ExecutionService instance."""
        if self._execution_service is None:
            raise RuntimeError("Session not initialized. Call initialize() first.")
        return self._execution_service

    @property
    def task_context(self) -> TaskContext:
        """Get the TaskContext instance."""
        if self._task_context is None:
            raise RuntimeError("Session not initialized. Call initialize() first.")
        return self._task_context

    @property
    def backend(self) -> BaseBackend:
        """Get the Backend instance."""
        if self._backend is None:
            raise RuntimeError("Session not initialized. Call initialize() first.")
        return self._backend

    @property
    def is_initialized(self) -> bool:
        """Check if the session is initialized."""
        return self._initialized

    def _create_history_recorder(self) -> TaskHistoryRecorder:
        """Create a TaskHistoryRecorder with optional provenance tracking.

        Returns:
            TaskHistoryRecorder configured based on enable_provenance_tracking
        """
        provenance_recorder = None
        if self.config.enable_provenance_tracking:
            from qdash.workflow.engine.task.provenance_recorder import (
                ProvenanceRecorder,
            )

            provenance_recorder = ProvenanceRecorder()

        return TaskHistoryRecorder(provenance_recorder=provenance_recorder)

    def initialize(self) -> None:
        """Initialize the calibration session.

        This method:
        1. Creates directory structure
        2. Pulls config from GitHub (if configured)
        3. Initializes ExecutionService
        4. Initializes TaskContext
        5. Initializes and connects Backend
        """
        if self._initialized:
            return

        config = self.config
        logger = get_run_logger()

        # Create directory structure
        self._create_directories()

        # Pull config from GitHub if requested
        if config.enable_github_pull:
            self._pull_github_config(logger)

        # Initialize ExecutionService (skip if in wrapper mode)
        if not config.skip_execution:
            self._execution_service = ExecutionService.create(
                username=config.username,
                execution_id=config.execution_id,
                calib_data_path=config.calib_data_path,
                chip_id=config.chip_id,
                name=config.flow_name or "Python Flow Execution",
                tags=config.tags,
                note=config.note,
                project_id=config.project_id,
            )
            self._execution_service.save_with_tags()
            self._execution_service.start_execution()
        else:
            logger.info("Skipping Execution creation (wrapper mode)")

        # Initialize TaskContext with optional provenance tracking
        self._task_context = TaskContext(
            username=config.username,
            execution_id=config.execution_id,
            qids=config.qids,
            calib_dir=config.calib_data_path,
            history_recorder=self._create_history_recorder(),
        )

        # Initialize Backend
        self._backend = self._create_backend()
        self._backend.connect()

        self._initialized = True
        logger.info(f"Session initialized: execution_id={config.execution_id}")

    def _create_directories(self) -> None:
        """Create the calibration directory structure."""
        config = self.config
        Path(config.calib_data_path).mkdir(parents=True, exist_ok=True)
        Path(config.classifier_dir).mkdir(exist_ok=True)
        Path(f"{config.calib_data_path}/task").mkdir(exist_ok=True)
        Path(f"{config.calib_data_path}/fig").mkdir(exist_ok=True)
        Path(f"{config.calib_data_path}/calib").mkdir(exist_ok=True)
        Path(f"{config.calib_data_path}/calib_note").mkdir(exist_ok=True)

    def _pull_github_config(self, logger: Any) -> None:
        """Pull configuration from GitHub."""
        from qdash.workflow.service.github import GitHubIntegration

        if GitHubIntegration.check_credentials() and self.github_integration is not None:
            commit_id = self.github_integration.pull_config()
            if commit_id and self.config.note is not None:
                self.config.note["config_commit_id"] = commit_id
        else:
            logger.warning("GitHub credentials not configured, skipping pull")

    def _create_backend(self) -> BaseBackend:
        """Create and configure the backend."""
        config = self.config

        # task_context must be initialized before calling this method
        assert self._task_context is not None, "TaskContext must be initialized first"

        # Build note_path using task_context.id
        note_path = f"{config.calib_data_path}/calib_note/{self._task_context.id}.json"

        session_config: dict[str, Any] = {
            "task_type": "qubit",
            "username": config.username,
            "qids": config.qids,
            "note_path": note_path,
            "chip_id": config.chip_id,
            "classifier_dir": config.classifier_dir,
            "project_id": config.project_id,
        }

        if config.muxes is not None:
            session_config["muxes"] = config.muxes

        backend = create_backend(
            backend=config.backend_name,
            config=session_config,
        )

        # Save calibration_note before connecting (loads parameter overrides)
        if backend.name == "qubex":
            backend.save_note(
                username=config.username,
                chip_id=config.chip_id,
                calib_dir=config.calib_data_path,
                execution_id=config.execution_id,
                task_manager_id=self._task_context.id,
                project_id=config.project_id,
            )

        return backend

    def complete(
        self,
        update_chip_history: bool = True,
        export_note_to_file: bool = False,
    ) -> None:
        """Mark the session as complete.

        Args:
            update_chip_history: Whether to update ChipHistoryDocument
            export_note_to_file: Whether to export calibration note to file
        """
        if not self._initialized:
            return

        from qdash.repository import (
            MongoChipHistoryRepository,
            MongoChipRepository,
        )

        logger = get_run_logger()
        config = self.config

        # Skip completion if in wrapper mode (no ExecutionService)
        if self._execution_service is None:
            logger.info("Skipping completion (wrapper mode - no Execution)")
            return

        # Reload and complete execution
        self._execution_service = self.execution_service.reload().complete_execution()

        # Update chip history
        if update_chip_history:
            try:
                chip_repo = MongoChipRepository()
                chip = chip_repo.get_chip_by_id(username=config.username, chip_id=config.chip_id)
                if chip is not None:
                    history_repo = MongoChipHistoryRepository()
                    history_repo.create_history(username=config.username, chip_id=config.chip_id)
                else:
                    logger.warning(
                        f"Chip '{config.chip_id}' not found for user '{config.username}', "
                        "skipping history update"
                    )
            except Exception as e:
                logger.warning(f"Failed to update chip history: {e}")

        # Export calibration note to file if requested
        if export_note_to_file:
            self._export_note_to_file(logger)

    def fail(self) -> None:
        """Mark the session as failed."""
        if self._execution_service is not None:
            self._execution_service = self._execution_service.reload().fail_execution()

    def _export_note_to_file(self, logger: Any) -> None:
        """Export calibration note to a JSON file."""
        from qdash.repository import MongoCalibrationNoteRepository

        config = self.config

        try:
            repo = MongoCalibrationNoteRepository()
            latest_note = repo.find_one(
                username=config.username,
                task_id=self.task_context.id,
                execution_id=config.execution_id,
                chip_id=config.chip_id,
            )

            if latest_note:
                note_path = Path(f"{config.calib_data_path}/calib_note/{self.task_context.id}.json")
                note_path.parent.mkdir(parents=True, exist_ok=True)
                note_path.write_text(json.dumps(latest_note.note, indent=2, ensure_ascii=False))
                logger.info(f"Exported calibration note to {note_path}")
            else:
                logger.warning(f"No calibration note found for task_id={self.task_context.id}")
        except Exception as e:
            logger.error(f"Failed to export calibration note: {e}")

    # =========================================================================
    # Task Execution
    # =========================================================================

    def run_task(
        self,
        task_name: str,
        qid: str,
        task_details: dict[str, Any] | None = None,
        upstream_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a calibration task.

        This is the main entry point for task execution. The flow is:
        1. Create task instance
        2. Prepare execution context
        3. Execute via Prefect task
        4. Merge results back

        Args:
            task_name: Name of the task (e.g., 'CheckRabi')
            qid: Qubit ID to calibrate
            task_details: Optional task configuration
            upstream_id: Optional upstream task_id for dependency tracking

        Returns:
            Task output parameters including task_id
        """
        # Step 1: Create task instance
        task_instance = self._create_task_instance(task_name, task_details)
        task_type = task_instance.get_task_type()

        # Step 2: Register task in workflow
        self._ensure_task_in_workflow(task_name, task_type, qid)

        # Step 3: Prepare execution context
        exec_context = self._prepare_execution_context(qid, upstream_id)

        # Step 4: Execute via Prefect
        executed_context = self._run_prefect_task(task_instance, exec_context, qid)

        # Step 5: Merge results and return
        return self._merge_and_extract_results(executed_context, task_name, task_type, qid)

    def _create_task_instance(
        self,
        task_name: str,
        task_details: dict[str, Any] | None,
    ) -> Any:
        """Create a task instance from task name."""
        from qdash.workflow.calibtasks.active_protocols import generate_task_instances

        if task_details is None:
            task_details = {}
        if task_name not in task_details:
            task_details[task_name] = {}

        task_instances = generate_task_instances(
            task_names=[task_name],
            task_details=task_details,
            backend=self.config.backend_name,
        )
        return task_instances[task_name]

    def _prepare_execution_context(
        self,
        qid: str,
        upstream_id: str | None,
    ) -> TaskContext:
        """Prepare a TaskContext for task execution."""
        from copy import deepcopy

        from qdash.datamodel.task import CalibDataModel

        config = self.config

        # Create new context for this execution with optional provenance tracking
        exec_context = TaskContext(
            username=config.username,
            execution_id=config.execution_id,
            qids=[qid],
            calib_dir=self.task_context.calib_dir,
            history_recorder=self._create_history_recorder(),
        )

        # Copy relevant calibration data
        relevant_qids = self._get_relevant_qubit_ids(qid)
        exec_context.state.calib_data = CalibDataModel(
            qubit={
                q: deepcopy(self.task_context.calib_data.qubit[q])
                for q in relevant_qids
                if q in self.task_context.calib_data.qubit
            },
            coupling={
                c: deepcopy(self.task_context.calib_data.coupling[c])
                for c in [qid]
                if qid in self.task_context.calib_data.coupling
            },
        )
        # Set upstream task dependency
        if upstream_id is not None:
            exec_context.set_upstream_task_id(upstream_id)
        else:
            last_id = self._last_executed_task_id_by_qid.get(qid, "")
            exec_context.set_upstream_task_id(last_id)

        return exec_context

    def _run_prefect_task(
        self,
        task_instance: Any,
        exec_context: TaskContext,
        qid: str,
    ) -> TaskContext:
        """Execute task via Prefect and return executed context."""
        from qdash.workflow.engine.task_runner import execute_dynamic_task_by_qid_service

        # Get latest execution service state
        execution_service = ExecutionService.from_existing(self.config.execution_id)
        if execution_service is None:
            execution_service = self.execution_service

        # Run Prefect task
        result = execute_dynamic_task_by_qid_service.with_options(
            timeout_seconds=task_instance.timeout,
            task_run_name=task_instance.name,
            log_prints=True,
        )(
            backend=self.backend,
            execution_service=execution_service,
            task_context=exec_context,
            task_instance=task_instance,
            qid=qid,
        )
        execution_service, executed_context = result

        # Update execution service reference
        self._execution_service = execution_service

        return cast(TaskContext, executed_context)

    def _merge_and_extract_results(
        self,
        executed_context: TaskContext,
        task_name: str,
        task_type: str,
        qid: str,
    ) -> dict[str, Any]:
        """Merge execution results back to main context and extract output."""
        # Merge calibration data
        self.task_context.state.calib_data.qubit.update(executed_context.calib_data.qubit)
        self.task_context.state.calib_data.coupling.update(executed_context.calib_data.coupling)
        # Track task_id for upstream dependency
        executed_task = executed_context.get_task(task_name=task_name, task_type=task_type, qid=qid)
        self._last_executed_task_id_by_qid[qid] = executed_task.task_id

        # Extract and return output parameters
        result = executed_context.get_output_parameter_by_task_name(
            task_name, task_type=task_type, qid=qid
        )
        result["task_id"] = executed_task.task_id

        return dict(result)

    def _ensure_task_in_workflow(self, task_name: str, task_type: str, qid: str) -> None:
        """Ensure task exists in TaskContext's workflow structure."""
        from qdash.datamodel.task import (
            CouplingTaskModel,
            GlobalTaskModel,
            QubitTaskModel,
            SystemTaskModel,
        )

        # Check if task already exists
        if task_type == "qubit":
            if qid in self.task_context.task_result.qubit_tasks:
                existing_tasks = [t.name for t in self.task_context.task_result.qubit_tasks[qid]]
                if task_name in existing_tasks:
                    return
            task = QubitTaskModel(name=task_name, upstream_id="", qid=qid)
            self.task_context.task_result.qubit_tasks.setdefault(qid, []).append(task)
        elif task_type == "coupling":
            if qid in self.task_context.task_result.coupling_tasks:
                existing_tasks = [t.name for t in self.task_context.task_result.coupling_tasks[qid]]
                if task_name in existing_tasks:
                    return
            coupling_task = CouplingTaskModel(name=task_name, upstream_id="", qid=qid)
            self.task_context.task_result.coupling_tasks.setdefault(qid, []).append(coupling_task)
        elif task_type == "global":
            existing_tasks = [t.name for t in self.task_context.task_result.global_tasks]
            if task_name in existing_tasks:
                return
            global_task = GlobalTaskModel(name=task_name, upstream_id="")
            self.task_context.task_result.global_tasks.append(global_task)
        elif task_type == "system":
            existing_tasks = [t.name for t in self.task_context.task_result.system_tasks]
            if task_name in existing_tasks:
                return
            system_task = SystemTaskModel(name=task_name, upstream_id="")
            self.task_context.task_result.system_tasks.append(system_task)

        # Save updated workflow
        self.task_context.save()

    def _get_relevant_qubit_ids(self, qid: str) -> list[str]:
        """Get the list of qubit IDs relevant to a task execution."""
        if "-" in qid:
            return qid.split("-")
        return [qid]
