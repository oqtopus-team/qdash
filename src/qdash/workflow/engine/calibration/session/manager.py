"""Session manager for calibration workflows.

This module handles the lifecycle of a calibration session:
- Directory structure creation
- ExecutionService, TaskSession, Backend initialization
- Session cleanup and finalization
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from prefect import get_run_logger

from qdash.workflow.engine.backend.base import BaseBackend
from qdash.workflow.engine.backend.factory import create_backend
from qdash.workflow.engine.calibration.execution.service import ExecutionService
from qdash.workflow.engine.calibration.session.config import SessionConfig
from qdash.workflow.engine.calibration.task.session import TaskSession

if TYPE_CHECKING:
    from qdash.workflow.service.github import GitHubIntegration, GitHubPushConfig


class SessionManager:
    """Manages the lifecycle of a calibration session.

    This class handles:
    - Directory structure creation
    - ExecutionService, TaskSession, Backend initialization
    - Session cleanup and finalization

    Example:
        ```python
        config = SessionConfig(
            username="alice",
            chip_id="64Qv3",
            qids=["0", "1"],
            execution_id="20240101-001",
        )
        session = SessionManager(config)
        session.initialize()

        # Use session components
        session.execution_service.save()
        session.task_session.get_task(...)
        session.backend.connect()
        ```
    """

    def __init__(
        self,
        config: SessionConfig,
        github_integration: "GitHubIntegration | None" = None,
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
        self._task_session: TaskSession | None = None
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
    def task_session(self) -> TaskSession:
        """Get the TaskSession instance."""
        if self._task_session is None:
            raise RuntimeError("Session not initialized. Call initialize() first.")
        return self._task_session

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

    def initialize(self) -> None:
        """Initialize the calibration session.

        This method:
        1. Creates directory structure
        2. Pulls config from GitHub (if configured)
        3. Initializes ExecutionService
        4. Initializes TaskSession
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

        # Initialize ExecutionService
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

        # Initialize TaskSession
        self._task_session = TaskSession(
            username=config.username,
            execution_id=config.execution_id,
            qids=config.qids,
            calib_dir=config.calib_data_path,
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

        # task_session must be initialized before calling this method
        assert self._task_session is not None, "TaskSession must be initialized first"

        # Build note_path using task_session.id
        note_path = f"{config.calib_data_path}/calib_note/{self._task_session.id}.json"

        session_config: dict[str, Any] = {
            "task_type": "qubit",
            "username": config.username,
            "qids": config.qids,
            "note_path": note_path,
            "chip_id": config.chip_id,
            "classifier_dir": config.classifier_dir,
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
                task_manager_id=self._task_session.id,
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

        from qdash.dbmodel.chip import ChipDocument
        from qdash.dbmodel.chip_history import ChipHistoryDocument

        logger = get_run_logger()
        config = self.config

        # Reload and complete execution
        self._execution_service = self.execution_service.reload().complete_execution()

        # Update chip history
        if update_chip_history:
            try:
                chip_doc = ChipDocument.get_chip_by_id(
                    username=config.username, chip_id=config.chip_id
                )
                if chip_doc is not None:
                    ChipHistoryDocument.create_history(chip_doc)
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
        from qdash.dbmodel.calibration_note import CalibrationNoteDocument

        config = self.config

        try:
            latest_doc = CalibrationNoteDocument.find_one(
                {
                    "username": config.username,
                    "task_id": self.task_session.id,
                    "execution_id": config.execution_id,
                    "chip_id": config.chip_id,
                }
            ).run()

            if latest_doc:
                note_path = Path(
                    f"{config.calib_data_path}/calib_note/{self.task_session.id}.json"
                )
                note_path.parent.mkdir(parents=True, exist_ok=True)
                note_path.write_text(json.dumps(latest_doc.note, indent=2, ensure_ascii=False))
                logger.info(f"Exported calibration note to {note_path}")
            else:
                logger.warning(f"No calibration note found for task_id={self.task_session.id}")
        except Exception as e:
            logger.error(f"Failed to export calibration note: {e}")

    # =========================================================================
    # Task Execution
    # =========================================================================

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
        """
        from copy import deepcopy

        from qdash.datamodel.task import CalibDataModel
        from qdash.workflow.calibtasks.active_protocols import generate_task_instances
        from qdash.workflow.engine.calibration.prefect_tasks import (
            execute_dynamic_task_by_qid_service,
        )

        config = self.config

        if task_details is None:
            task_details = {}

        # Ensure task_details has an entry for this task
        if task_name not in task_details:
            task_details[task_name] = {}

        # Generate task instance
        task_instances = generate_task_instances(
            task_names=[task_name],
            task_details=task_details,
            backend=config.backend_name,
        )

        task_instance = task_instances[task_name]
        task_type = task_instance.get_task_type()

        # Add task to workflow if not already present
        self._ensure_task_in_workflow(task_name, task_type, qid)

        # Reload execution service to get latest state
        execution_service = ExecutionService.from_existing(config.execution_id)
        if execution_service is None:
            execution_service = self.execution_service

        # Create a new TaskSession for this specific execution
        execution_task_session = TaskSession(
            username=config.username,
            execution_id=config.execution_id,
            qids=[qid],
            calib_dir=self.task_session.calib_dir,
        )

        # Copy only the relevant calibration data for this qid
        relevant_qubit_ids = self._get_relevant_qubit_ids(qid)
        execution_task_session.state.calib_data = CalibDataModel(
            qubit={
                q: deepcopy(self.task_session.calib_data.qubit[q])
                for q in relevant_qubit_ids
                if q in self.task_session.calib_data.qubit
            },
            coupling={
                c: deepcopy(self.task_session.calib_data.coupling[c])
                for c in [qid]
                if qid in self.task_session.calib_data.coupling
            },
        )
        execution_task_session.controller_info = deepcopy(self.task_session.controller_info)

        # Set upstream_id for sequential task dependency tracking
        if upstream_id is not None:
            execution_task_session.set_upstream_task_id(upstream_id)
        else:
            last_id = self._last_executed_task_id_by_qid.get(qid, "")
            execution_task_session.set_upstream_task_id(last_id)

        # Execute task
        execution_service, executed_task_session = execute_dynamic_task_by_qid_service.with_options(
            timeout_seconds=task_instance.timeout,
            task_run_name=task_instance.name,
            log_prints=True,
        )(
            backend=self.backend,
            execution_service=execution_service,
            task_session=execution_task_session,
            task_instance=task_instance,
            qid=qid,
        )

        # Merge results back to main task_session
        self.task_session.state.calib_data.qubit.update(
            executed_task_session.calib_data.qubit
        )
        self.task_session.state.calib_data.coupling.update(
            executed_task_session.calib_data.coupling
        )
        self.task_session.controller_info.update(executed_task_session.controller_info)

        # Update execution service
        self._execution_service = execution_service

        # Store the executed task's task_id for upstream tracking
        executed_task = executed_task_session.get_task(
            task_name=task_name, task_type=task_instance.get_task_type(), qid=qid
        )
        self._last_executed_task_id_by_qid[qid] = executed_task.task_id

        # Return output parameters
        result = executed_task_session.get_output_parameter_by_task_name(
            task_name,
            task_type=task_instance.get_task_type(),
            qid=qid,
        )
        result["task_id"] = executed_task.task_id

        return dict(result)

    def _ensure_task_in_workflow(self, task_name: str, task_type: str, qid: str) -> None:
        """Ensure task exists in TaskSession's workflow structure."""
        from qdash.datamodel.task import (
            CouplingTaskModel,
            GlobalTaskModel,
            QubitTaskModel,
            SystemTaskModel,
        )

        # Check if task already exists
        if task_type == "qubit":
            if qid in self.task_session.task_result.qubit_tasks:
                existing_tasks = [
                    t.name for t in self.task_session.task_result.qubit_tasks[qid]
                ]
                if task_name in existing_tasks:
                    return
            task = QubitTaskModel(name=task_name, upstream_id="", qid=qid)
            self.task_session.task_result.qubit_tasks.setdefault(qid, []).append(task)
        elif task_type == "coupling":
            if qid in self.task_session.task_result.coupling_tasks:
                existing_tasks = [
                    t.name for t in self.task_session.task_result.coupling_tasks[qid]
                ]
                if task_name in existing_tasks:
                    return
            task = CouplingTaskModel(name=task_name, upstream_id="", qid=qid)
            self.task_session.task_result.coupling_tasks.setdefault(qid, []).append(task)
        elif task_type == "global":
            existing_tasks = [t.name for t in self.task_session.task_result.global_tasks]
            if task_name in existing_tasks:
                return
            task = GlobalTaskModel(name=task_name, upstream_id="")
            self.task_session.task_result.global_tasks.append(task)
        elif task_type == "system":
            existing_tasks = [t.name for t in self.task_session.task_result.system_tasks]
            if task_name in existing_tasks:
                return
            task = SystemTaskModel(name=task_name, upstream_id="")
            self.task_session.task_result.system_tasks.append(task)

        # Save updated workflow
        self.task_session.save()

    def _get_relevant_qubit_ids(self, qid: str) -> list[str]:
        """Get the list of qubit IDs relevant to a task execution."""
        if "-" in qid:
            return qid.split("-")
        return [qid]
