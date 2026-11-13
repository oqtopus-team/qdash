"""Internal calibration session: one Execution's lifecycle and task execution.

``CalibSession`` is what steps, strategies and workers operate on. Workflows do
not create it: ``CalibService.run`` and the system flows build it from typed
:class:`~qdash.workflow.service._internal.settings.SessionSettings`, and an
isolated worker builds it from the :class:`WorkerSpec` its owner hands over.

A session has one of two roles:

- ``SessionRole.OWNER`` creates, starts and closes its Execution and holds the
  hardware reservation (for a pipeline, across all of its steps).
- ``SessionRole.WORKER`` borrows its owner's Execution and reservation. It never
  claims an API-scheduled execution, takes or releases the lock, records a
  terminal status, updates chip history or talks to GitHub.

Every owned Execution is opened and closed by :meth:`CalibSession.owned_execution`,
which records success, failure or cancellation, or leaves the Execution open for
the Prefect terminal hooks after an external termination signal.
"""

from __future__ import annotations

import contextlib
import enum
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from qdash.datamodel.task_invocation import TaskInvocation
    from qdash.repository.protocols import (
        ExecutionCounterRepository,
        ExecutionLockRepository,
    )
    from qdash.workflow.engine.backend.base import BaseBackend
    from qdash.workflow.engine.execution.service import ExecutionService
    from qdash.workflow.engine.task.context import TaskContext
    from qdash.workflow.service.steps import Step
    from qdash.workflow.service.targets import Target

from prefect import get_run_logger

from qdash.common.execution_resources import (
    ExecutionResourceScope,
    merge_resource_scopes,
    resolve_execution_resource_scope,
    scope_contains,
)
from qdash.common.utils.datetime import now
from qdash.workflow.engine import CalibConfig, CalibOrchestrator
from qdash.workflow.engine.params_updater import get_params_updater
from qdash.workflow.engine.task_parameters import (
    INPUT,
    RUN,
    merge_task_parameters,
    normalize_task_settings,
    validate_task_names,
)
from qdash.workflow.service._internal.lifecycle import (
    is_cancellation,
    is_external_termination,
)
from qdash.workflow.service._internal.settings import (
    ReservationScope,
    SessionSettings,
    WorkerLease,
    WorkerSpec,
)
from qdash.workflow.service.execution_id import generate_execution_id
from qdash.workflow.service.github import GitHubIntegration, GitHubPushConfig

logger = logging.getLogger(__name__)


def _with_settings(
    invocation: TaskInvocation | None, settings: dict[str, Any]
) -> TaskInvocation | None:
    """Record the effective call settings on a planned call's invocation."""
    if invocation is None:
        return None
    return invocation.model_copy(update={"settings": settings})


def configured_layout(step: Any) -> str | None:
    """The configuration mode a ConfigureAll step selects, if any."""
    from qdash.workflow.service.steps.box_setup import ConfigureAll

    if not isinstance(step, ConfigureAll):
        return None
    run = step.calls()[0].settings().get(RUN, {})
    entry = run.get("configuration_mode")
    value = entry.get("value") if isinstance(entry, dict) else entry
    return value if isinstance(value, str) and value else None


def read_flow_run_id_from_context() -> str | None:
    """Return the current Prefect flow run id, if any."""
    try:
        from prefect.context import get_run_context

        ctx = get_run_context()
        flow_run = getattr(ctx, "flow_run", None)
        if flow_run:
            return str(flow_run.id)
    except Exception:
        logger.debug("No Prefect run context available for flow_run_id")
    return None


class SessionRole(enum.Enum):
    """Who owns the Execution and the hardware reservation of a session."""

    OWNER = "owner"
    WORKER = "worker"


@dataclass
class SessionRepositories:
    """Repositories a session uses; ``None`` selects the MongoDB implementation."""

    lock_repo: ExecutionLockRepository | None = None
    counter_repo: ExecutionCounterRepository | None = None
    execution_repo: Any | None = None


class CalibSession:
    """One calibration Execution: its lifecycle, reservation and task execution."""

    def __init__(
        self,
        settings: SessionSettings,
        *,
        lease: WorkerLease | None = None,
        repositories: SessionRepositories | None = None,
    ) -> None:
        """Create a session; ``lease`` makes it a worker borrowing its owner's Execution.

        Raises:
            ValueError: A per-task default names a task the backend does not register.
        """
        validate_task_names(settings.task_defaults, settings.backend_name)
        self.settings = settings
        self.role = SessionRole.WORKER if lease is not None else SessionRole.OWNER
        repositories = repositories or SessionRepositories()
        self._lock_repo = repositories.lock_repo
        self._counter_repo = repositories.counter_repo
        self._execution_repo = repositories.execution_repo

        self.qids: list[str] | None = None
        self.execution_id: str | None = lease.execution_id if lease is not None else None
        self._reserved_scope: ExecutionResourceScope | None = (
            lease.reservation.to_scope()
            if lease is not None and lease.reservation is not None
            else None
        )
        self._lock_acquired = False
        self._lock_execution_id: str | None = None
        self._initialized = False
        self._pipeline_active = False
        # Version of the plan being run, recorded on each task's invocation.
        self.plan_digest: str | None = None
        self._configuration_mode = settings.configuration_mode
        self._orchestrator: CalibOrchestrator | None = None
        self.github_integration: GitHubIntegration | None = None

    # -- Settings views ------------------------------------------------------

    @property
    def is_worker(self) -> bool:
        return self.role is SessionRole.WORKER

    @property
    def username(self) -> str:
        return self.settings.username

    @property
    def chip_id(self) -> str:
        return self.settings.chip_id

    @property
    def project_id(self) -> str:
        return self.settings.project_id

    @property
    def backend_name(self) -> str:
        return self.settings.backend_name

    @property
    def flow_name(self) -> str | None:
        return self.settings.flow_name

    @property
    def tags(self) -> list[str] | None:
        return self.settings.tags

    @property
    def note(self) -> dict[str, Any] | None:
        return self.settings.note

    @property
    def default_run_parameters(self) -> dict[str, Any]:
        return self.settings.default_run_parameters

    @property
    def task_parameters(self) -> dict[str, dict[str, Any]]:
        """Per-task defaults resolved by QDash (pipeline specs and single-task runs)."""
        return self.settings.task_defaults

    @property
    def configuration_mode(self) -> str | None:
        """The configuration mode in effect, resolved from the backend once initialized."""
        return self._configuration_mode

    @property
    def github_push_config(self) -> GitHubPushConfig:
        return self.settings.github.push

    def worker_spec(self) -> WorkerSpec:
        """What isolated workers of the current Execution inherit; the only such builder."""
        if self.execution_id is None:
            raise RuntimeError("Workers can only borrow an initialized Execution")
        return WorkerSpec(
            settings=self.settings.with_configuration_mode(self._configuration_mode).for_worker(),
            lease=WorkerLease(
                execution_id=self.execution_id,
                reservation=(
                    ReservationScope.of(self._reserved_scope)
                    if self._reserved_scope is not None
                    else None
                ),
            ),
        )

    # -- Reservation and Execution identity ----------------------------------

    def _ensure_execution_id(self) -> None:
        """Adopt the API reservation or mint a history ID, retaining the lock owner."""
        flow_run_id = read_flow_run_id_from_context()
        claimed_execution_id: str | None = None
        supplied_execution_id = self.execution_id is not None
        if self.execution_id is None:
            # Owners adopt the API's pre-created execution: minting another ID
            # would collide with the lock the API pre-acquired for it. Workers
            # always arrive with their owner's execution_id and never claim.
            if flow_run_id is not None and not self.is_worker:
                if self._execution_repo is None:
                    from qdash.repository import MongoExecutionRepository

                    self._execution_repo = MongoExecutionRepository()
                claimed_execution_id = self._execution_repo.claim_scheduled_execution(
                    project_id=self.project_id, flow_run_id=flow_run_id
                )
                if claimed_execution_id is not None:
                    logger.info(
                        "Adopted pre-created execution_id=%s for flow_run_id=%s",
                        claimed_execution_id,
                        flow_run_id,
                    )

            self.execution_id = claimed_execution_id or generate_execution_id(
                self.username,
                self.chip_id,
                project_id=self.project_id,
                counter_repo=self._counter_repo,
            )

        if self._lock_execution_id is None:
            self._lock_execution_id = (
                f"flow:{flow_run_id}"
                if self._pipeline_active
                and flow_run_id
                and claimed_execution_id is None
                and not supplied_execution_id
                else self.execution_id
            )

    def _acquire_resource_scope(self, scope: ExecutionResourceScope) -> None:
        """Atomically reserve the whole plan, never dropping already held resources."""
        if self.is_worker:
            return
        self._ensure_execution_id()
        if self._lock_repo is None:
            from qdash.repository import MongoExecutionLockRepository

            self._lock_repo = MongoExecutionLockRepository()
        if self._reserved_scope is not None:
            scope = merge_resource_scopes(self._reserved_scope, scope)
        if not self._lock_repo.try_lock(
            project_id=self.project_id,
            execution_id=self._lock_execution_id,
            chip_id=scope.chip_id,
            resources=scope.resources,
            exclusive=scope.exclusive,
        ):
            raise RuntimeError("Calibration is already running. Cannot start a new session.")
        self._reserved_scope = scope
        self._lock_acquired = True

    def _validate_resource_scope(self, parameters: dict[str, Any]) -> None:
        """Reject operations beyond the plan, including operations in borrowed workers."""
        if self._reserved_scope is None:
            return
        if parameters.get("qids") == []:
            return
        requested = resolve_execution_resource_scope(self.chip_id, parameters)
        if not scope_contains(self._reserved_scope, requested):
            raise RuntimeError("Requested hardware is outside the workflow's reserved resources")

    def _initialize(self, qids: list[str], *, connect_backend: bool = True) -> None:
        """Create this session's Execution state and backend for ``qids``.

        An owner reserves ``qids`` first unless it already holds a reservation;
        a worker validates ``qids`` against the reservation it borrows.
        """
        if self._initialized:
            return

        self.qids = qids
        flow_run_id = read_flow_run_id_from_context()

        self._ensure_execution_id()
        self._validate_resource_scope({"qids": qids})
        assert self.execution_id is not None

        self.github_integration = GitHubIntegration(
            username=self.username,
            chip_id=self.chip_id,
            execution_id=self.execution_id,
            project_id=self.project_id,
        )

        # A pipeline reserves its complete plan before any step starts. Later
        # step execution IDs never change the reservation owner or narrow scope.
        if not self.is_worker and not self._lock_acquired:
            self._acquire_resource_scope(
                resolve_execution_resource_scope(self.chip_id, {"qids": qids})
            )

        # Interruptions before the caller holds a session also release the claim.
        try:
            note = dict(self.note or {})
            if flow_run_id:
                note["flow_run_id"] = flow_run_id
            if self._reserved_scope is not None:
                note["hardware_reservation"] = {
                    "chip_id": self._reserved_scope.chip_id,
                    "resources": list(self._reserved_scope.resources),
                    "exclusive": self._reserved_scope.exclusive,
                }

            settings = self.settings
            config = CalibConfig(
                username=self.username,
                chip_id=self.chip_id,
                qids=qids,
                execution_id=self.execution_id,
                backend_name=self.backend_name,
                flow_name=self.flow_name,
                tags=self.tags,
                note=note,
                project_id=self.project_id,
                enable_github_pull=settings.github.pull,
                skip_execution=self.is_worker,
                connect_backend=connect_backend,
                default_run_parameters=self.default_run_parameters,
                task_parameters=self.task_parameters,
                force_update_params=settings.force_update_params,
            )
            if self._configuration_mode is not None:
                config.configuration_mode = self._configuration_mode
            else:
                # Keep CalibConfig's environment-backed default and hand the
                # resolved value to this session's workers.
                self._configuration_mode = config.configuration_mode

            snapshot_loader = None
            snapshot = settings.snapshot
            if snapshot.active:
                from qdash.workflow.engine.task.snapshot_loader import (
                    SnapshotParameterLoader,
                )

                snapshot_loader = SnapshotParameterLoader(
                    source_execution_id=snapshot.execution_id,
                    project_id=self.project_id,
                    source_task_id=snapshot.task_id,
                    snapshot_exempt_tasks=set(snapshot.exempt_tasks),
                )
                logger.info(
                    "Created SnapshotParameterLoader for source_task_id=%s, source_execution_id=%s",
                    snapshot.task_id,
                    snapshot.execution_id,
                )

            self._orchestrator = CalibOrchestrator(
                config=config,
                github_integration=self.github_integration,
                snapshot_loader=snapshot_loader,
            )
            self._orchestrator._source_task_id = snapshot.task_id
            self._orchestrator.initialize()

            self._initialized = True
        except BaseException:
            if self._lock_acquired and self._lock_repo is not None and not self._pipeline_active:
                self._lock_repo.unlock(
                    project_id=self.project_id,
                    execution_id=self._lock_execution_id,
                )
                self._lock_acquired = False
                self._lock_execution_id = None
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

    def _disconnect_backend(self) -> None:
        """Release this session's backend without changing Execution ownership."""
        backend = self.backend
        if backend is None:
            return
        try:
            backend.disconnect()
        except Exception:
            logger.exception("Failed to disconnect backend for execution %s", self.execution_id)

    def execute_task(
        self,
        task_name: str,
        qid: str,
        upstream_id: str | None = None,
        *,
        parameters: dict[str, Any] | None = None,
        invocation: TaskInvocation | None = None,
    ) -> dict[str, Any]:
        """Execute a calibration task with integrated save processing.

        Args:
            task_name: Name of the task to execute (e.g., 'CheckFreq')
            qid: Qubit ID to calibrate
            upstream_id: Optional explicit upstream task_id for dependency tracking
            parameters: Settings for this call only, in the form of one
                ``task_parameters`` entry: ``run``, ``input``, and
                ``update_calibration_parameters``. They take precedence over the
                session's per-task defaults.
            invocation: The planned step and call this run executes, recorded on
                the task result together with the effective call settings. Steps
                set it for every call; direct calls may leave it unset.

        Returns:
            Dictionary containing the task's output parameters and task_id

        Example:
            ```python
            result = session.execute_task("CheckFreq", "0")
            print(f"Frequency: {result.get('qubit_frequency')}")

            # With explicit upstream_id for group execution
            result1 = session.execute_task("CheckRabi", "33")
            result2 = session.execute_task("CheckRabi", "32", upstream_id=result1["task_id"])

            # Override one input for this call only
            session.execute_task("CheckRabi", "0", parameters={"input": {"control_amplitude": 0.05}})
            ```
        """
        if not self.is_worker and not self._lock_acquired:
            raise RuntimeError("No hardware reservation is held for this execution")
        settings = normalize_task_settings(task_name, parameters)
        effective_settings = merge_task_parameters(
            {task_name: self.task_parameters.get(task_name, {RUN: {}, INPUT: {}})},
            {task_name: settings},
        )[task_name]
        resource_parameters: dict[str, Any] = {"qid": qid}
        if task_name == "ConfigureAll":
            resource_parameters = {
                "mux_ids": effective_settings[RUN].get("mux_ids", {}).get("value")
            }
        self._validate_resource_scope(resource_parameters)
        assert self._orchestrator is not None, "Session not initialized"
        result: dict[str, Any] = self._orchestrator.run_task(
            task_name,
            qid,
            settings,
            upstream_id,
            invocation=_with_settings(invocation, effective_settings),
        )
        return result

    def execute_task_batch(
        self,
        task_name: str,
        qids: list[str],
        upstream_id: str | None = None,
        *,
        parameters: dict[str, Any] | None = None,
        invocation: TaskInvocation | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Execute one calibration task with a single batch_run over qids.

        ``parameters`` and ``invocation`` behave as in ``execute_task``.
        """
        if not self.is_worker and not self._lock_acquired:
            raise RuntimeError("No hardware reservation is held for this execution")
        settings = normalize_task_settings(task_name, parameters)
        effective_settings = merge_task_parameters(
            {task_name: self.task_parameters.get(task_name, {RUN: {}, INPUT: {}})},
            {task_name: settings},
        )[task_name]
        self._validate_resource_scope({"qids": qids})
        assert self._orchestrator is not None, "Session not initialized"
        return self._orchestrator.run_task_batch(
            task_name,
            qids,
            settings,
            upstream_id,
            invocation=_with_settings(invocation, effective_settings),
        )

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

    def _finalize_tasks_on_cancel(
        self,
        logger: Any,
        message: str = "Execution was cancelled",
    ) -> None:
        """Mark non-terminal tasks as cancelled for this execution.

        Unlike _finalize_stale_running_tasks which only targets RUNNING tasks,
        this method also marks SCHEDULED and PENDING tasks as cancelled.

        Args:
            logger: Logger instance for output
            message: Cancellation message to set on tasks

        """
        if self.execution_service is None or self.execution_id is None:
            return

        project_id = self.execution_service.project_id
        if project_id is None:
            return

        try:
            from qdash.repository import MongoTaskResultHistoryRepository

            repo = MongoTaskResultHistoryRepository()

            retry_delays = [0.5, 1, 2, 3, 5]

            for attempt, delay in enumerate(retry_delays):
                count = repo.finalize_tasks_on_cancel(
                    project_id=project_id,
                    execution_id=self.execution_id,
                    message=message,
                )
                if count > 0:
                    logger.warning(
                        f"[attempt {attempt + 1}/{len(retry_delays)}] "
                        f"Cancelled {count} non-terminal task(s) "
                        f"for execution {self.execution_id}"
                    )
                    if attempt < len(retry_delays) - 1:
                        time.sleep(delay)
                else:
                    if attempt == 0:
                        logger.info(
                            f"All tasks in terminal state for execution {self.execution_id}"
                        )
                    break
        except Exception as e:
            logger.warning(f"Failed to finalize tasks on cancel: {e}")

    def _sync_backend_params_before_push(self, logger: Any) -> GitHubPushConfig:
        """Sync recent calibration results into backend YAML params prior to GitHub push.

        Returns the push configuration for this execution. ``params_file_names`` is
        narrowed to the files this execution touched on a copy, because pipeline
        steps share ``self.github_push_config``: narrowing it in place would leave
        later steps with only the files an earlier step touched.
        """
        assert self.execution_service is not None, "ExecutionService not initialized"
        self._merge_task_result_calib_data_before_push(logger)
        updater_instance = get_params_updater(self.backend, self.chip_id)
        if updater_instance is None:
            return self.github_push_config

        from qdash.workflow.engine.params_updater import resolve_param_yaml_file_names

        push_candidate_files: set[str] = set()
        for qid, params in self.execution_service.calib_data.qubit.items():
            if "-" in qid or not params:
                continue
            push_candidate_files.update(resolve_param_yaml_file_names(params))
            try:
                push_candidate_files.update(updater_instance.update(qid, params))
            except Exception as exc:
                logger.warning(f"Failed to sync params for qid={qid}: {exc}")

        configured_param_files = self.github_push_config.params_file_names
        if configured_param_files is None:
            return self.github_push_config
        skipped_files = sorted(set(configured_param_files) - push_candidate_files)
        if skipped_files:
            logger.info(
                "Skipping params files not touched by this calibration: %s",
                ", ".join(skipped_files),
            )
        return self.github_push_config.model_copy(
            update={
                "params_file_names": [
                    file_name
                    for file_name in configured_param_files
                    if file_name in push_candidate_files
                ]
            }
        )

    def _merge_task_result_calib_data_before_push(self, logger: Any) -> None:
        """Reload completed task outputs into parent calib_data before GitHub push.

        Parallel strategies run isolated child sessions. Those sessions persist
        TaskResultHistoryDocument rows, but their in-memory calib_data does not
        flow back to the parent process. Rebuild the parent in-memory calib_data
        from completed task results before deciding which params YAML files changed.
        """
        assert self.execution_service is not None, "ExecutionService not initialized"
        execution_id = getattr(self, "execution_id", None)
        if not execution_id:
            return

        try:
            from bunnet import SortDirection

            from qdash.datamodel.task import (
                CalibDataModel,
                ParameterModel,
                TaskResultOutputParameterModel,
                TaskTypes,
            )
            from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

            docs = (
                TaskResultHistoryDocument.find(
                    {
                        "project_id": self.project_id,
                        "execution_id": execution_id,
                        "status": "completed",
                    }
                )
                .sort([("end_at", SortDirection.ASCENDING)])
                .run()
            )

            calib_data = CalibDataModel()
            names_by_task: dict[tuple[str, str, str], set[str]] = {}
            name_owner: dict[tuple[str, str, str], tuple[str, str, str]] = {}
            stale_names: set[tuple[str, str, str]] = set()
            for doc in docs:
                if not doc.qid or not doc.output_parameters:
                    continue

                published_by_doc: dict[str, ParameterModel] = {}
                for name, value in doc.output_parameters.items():
                    try:
                        output_parameter = (
                            value
                            if isinstance(value, TaskResultOutputParameterModel)
                            else TaskResultOutputParameterModel.model_validate(value)
                        )
                        if not output_parameter.database_updated:
                            continue
                        parameter = ParameterModel.model_validate(
                            output_parameter.model_dump(exclude_none=True)
                        )
                    except Exception:
                        logger.debug(
                            "Skipping invalid output parameter %s from task_id=%s",
                            name,
                            doc.task_id,
                            exc_info=True,
                        )
                        continue

                    # Key by the published calibration parameter names recorded at
                    # save time, matching the in-memory calib_data of the task run.
                    # Results persisted before per-destination metadata existed only
                    # carry the output name.
                    if output_parameter.database_updates:
                        published_targets = [
                            (
                                str(update["parameter_name"]),
                                update.get("updated_value", parameter.value),
                            )
                            for update in output_parameter.database_updates
                            if update.get("updated") is True
                        ]
                    else:
                        published_targets = [(name, parameter.value)]
                    for published_name, published_value in published_targets:
                        published_by_doc[published_name] = parameter.model_copy(
                            update={"parameter_name": published_name, "value": published_value}
                        )

                if not published_by_doc:
                    continue
                task_key = (doc.name, doc.task_type, doc.qid)
                previous_names = names_by_task.get(task_key, set())
                is_coupling = doc.task_type == TaskTypes.COUPLING or "-" in doc.qid
                target_data = calib_data.coupling if is_coupling else calib_data.qubit
                for old_name in previous_names - published_by_doc.keys():
                    owner_key = (doc.task_type, doc.qid, old_name)
                    if name_owner.get(owner_key) == task_key:
                        target_data.get(doc.qid, {}).pop(old_name, None)
                        stale_names.add(owner_key)
                        del name_owner[owner_key]
                for published_name, published in published_by_doc.items():
                    owner_key = (doc.task_type, doc.qid, published_name)
                    if is_coupling:
                        calib_data.put_coupling_data(doc.qid, published_name, published)
                    else:
                        calib_data.put_qubit_data(doc.qid, published_name, published)
                    name_owner[owner_key] = task_key
                    stale_names.discard(owner_key)
                names_by_task[task_key] = set(published_by_doc)

            if calib_data.qubit or calib_data.coupling:
                self.execution_service.merge_calib_data(calib_data)
                logger.info(
                    "Merged task result calib_data before GitHub push: %d qubit(s), %d coupling(s)",
                    len(calib_data.qubit),
                    len(calib_data.coupling),
                )
            current_data = self.execution_service.calib_data
            for task_type, qid, stale_name in stale_names:
                target_data = (
                    current_data.coupling
                    if task_type == TaskTypes.COUPLING or "-" in qid
                    else current_data.qubit
                )
                target_data.get(qid, {}).pop(stale_name, None)
        except Exception as exc:
            logger.warning(f"Failed to merge task result calib_data before push: {exc}")

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
            # Workers borrow their owner's Execution and must not close it.
            if self.execution_service is None or self.is_worker:
                logger.info("Skipping finalization (no owned Execution)")
                return None

            assert self.task_context is not None, "TaskContext not initialized"

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
            try:
                self._disconnect_backend()
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
            chip = chip_repo.find_by_id(project_id=self.project_id, chip_id=self.chip_id)
            if chip is not None:
                history_repo = MongoChipHistoryRepository()
                history_repo.create_history(
                    username=self.username,
                    chip_id=self.chip_id,
                    project_id=self.project_id,
                )
            else:
                logger.warning(
                    f"Chip '{self.chip_id}' not found in project '{self.project_id}', "
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
        assert self.execution_service is not None

        should_push = (
            push_to_github if push_to_github is not None else self.github_push_config.enabled
        )
        if not should_push:
            return None

        push_config = self._sync_backend_params_before_push(logger)
        if GitHubIntegration.check_credentials() and self.github_integration is not None:
            try:
                push_results = self.github_integration.push_files(push_config)
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
        if getattr(self, "_pipeline_active", False):
            return
        if self._lock_acquired and self._lock_repo is not None:
            self._lock_repo.unlock(
                project_id=self.project_id,
                execution_id=self._lock_execution_id,
            )
            self._lock_acquired = False
            self._lock_execution_id = None

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
            # Workers borrow their owner's Execution and must not close it.
            if self.is_worker:
                return

            # Finalize any tasks still in RUNNING status before failing execution
            if self.execution_service:
                self._finalize_stale_running_tasks(
                    run_logger,
                    message="Task was still running when execution failed",
                )
            # Reload and mark as failed
            if self.execution_service:
                self.execution_service = self.execution_service.reload().fail(error_message)
        finally:
            try:
                self._disconnect_backend()
            finally:
                self._release_lock_if_acquired()
                self._initialized = False

    def cancel_calibration(self) -> None:
        """Mark the calibration as cancelled and cleanup.

        This should be called when a Prefect CancelledRun exception is caught
        to properly distinguish cancellation from failure.
        """
        run_logger = get_run_logger()
        try:
            if self.is_worker:
                return

            # Mark non-terminal tasks as cancelled
            if self.execution_service:
                self._finalize_tasks_on_cancel(run_logger)

            # Reload and mark execution as cancelled
            if self.execution_service:
                self.execution_service = self.execution_service.reload().cancel()
        finally:
            try:
                self._disconnect_backend()
            finally:
                self._release_lock_if_acquired()
                self._initialized = False

    def abandon_calibration(self) -> None:
        """Release resources without recording a terminal status.

        Called when the flow process is interrupted by a signal. Whether the run
        was cancelled or killed is only known from the flow run's terminal state,
        so the execution is left open for ``on_flow_cancellation`` /
        ``on_flow_crashed``, or the API reconciliation, to close.
        """
        try:
            self._disconnect_backend()
        finally:
            self._release_lock_if_acquired()
            self._initialized = False

    # =========================================================================
    # High-level API Methods
    # =========================================================================

    # -- Lifecycle ownership -------------------------------------------------

    def _close_after(self, exc: BaseException) -> None:
        """Record how an owned Execution ended and release its resources."""
        run_logger = get_run_logger()
        if is_cancellation(exc):
            run_logger.info("Execution was cancelled")
            self.cancel_calibration()
        elif is_external_termination(exc):
            run_logger.info(
                "Interrupted by a termination signal; "
                "leaving the execution for the flow run hooks to close"
            )
            self.abandon_calibration()
        else:
            self.fail_calibration(str(exc))

    @contextlib.contextmanager
    def owned_execution(
        self, qids: list[str], *, connect_backend: bool = True
    ) -> Iterator[CalibSession]:
        """Open this owner's Execution for ``qids`` and close it however the block ends.

        Success completes the Execution (chip history, GitHub push). An exception
        fails it, a cancellation cancels it, and an external termination signal
        only releases resources so the Prefect terminal hooks record the outcome.
        Outside a pipeline the reservation is released as well.
        """
        if self.is_worker:
            raise RuntimeError("A worker session borrows its Execution and cannot own one")
        try:
            self._initialize(qids, connect_backend=connect_backend)
            yield self
            self.finish_calibration()
        except BaseException as exc:
            with contextlib.suppress(Exception):
                self._close_after(exc)
            raise

    def release_borrowed(self) -> None:
        """Release a worker's backend; the owner keeps the Execution and reservation."""
        self._disconnect_backend()
        self._initialized = False

    def _start_next_step(self, settings: SessionSettings) -> None:
        """Forget the previous step's Execution while keeping the pipeline reservation."""
        self._initialized = False
        self._orchestrator = None
        self.execution_id = None
        self.settings = settings

    def run_pipeline(self, targets: Target, steps: Sequence[Step]) -> dict[str, Any]:
        """Reserve the whole plan, then run each hardware step in its own Execution.

        Returns:
            Dictionary with typed results from each step
        """
        from qdash.workflow.service.pipeline_resources import plan_pipeline_resources
        from qdash.workflow.service.session_context import (
            clear_current_session,
            set_current_session,
        )
        from qdash.workflow.service.steps import Pipeline, StepContext
        from qdash.workflow.service.steps.base import TransformStep

        run_logger = get_run_logger()
        if self.is_worker:
            raise RuntimeError("A worker session cannot run a pipeline")

        set_current_session(self)
        self._pipeline_active = True
        original_settings = base_settings = self.settings
        pipeline_flow_name = base_settings.flow_name

        try:
            qids = targets.to_qids(self.chip_id)
            # Validate pipeline dependencies, step ids and filter references
            pipeline = Pipeline(steps)
            # Manual rounds are checked against the chip before anything is
            # reserved or measured, so a bad round fails the run up front.
            for step in pipeline:
                step.preflight(self)
            calibration_plan = self.calibration_plan(list(pipeline))
            self.plan_digest = calibration_plan["digest"]
            pipeline_note = {**(base_settings.note or {}), "calibration_plan": calibration_plan}
            self._acquire_resource_scope(plan_pipeline_resources(self.chip_id, targets, steps))
            run_logger.info(f"Starting calibration pipeline with {len(pipeline)} steps")

            ctx = StepContext()
            ctx.candidate_qids = qids
            completed_steps = 0

            for i, step in enumerate(pipeline):
                run_logger.info(f"Step {i + 1}/{len(pipeline)}: {step.name}")
                # Transform-only steps do not create an Execution.
                if isinstance(step, TransformStep):
                    ctx = step.execute(self, targets, ctx)
                    continue
                self._validate_resource_scope({"qids": ctx.candidate_qids})
                layout = configured_layout(step)
                if layout is not None:
                    # The step, the steps after it and their workers share the layout.
                    base_settings = base_settings.with_configuration_mode(layout)
                    self._configuration_mode = layout
                step_settings = base_settings.with_metadata(
                    flow_name=(
                        f"{pipeline_flow_name}_{step.name}" if pipeline_flow_name else step.name
                    ),
                    note={
                        **pipeline_note,
                        "step_name": step.name,
                        "step_id": getattr(step, "resolved_step_id", step.name),
                        "step_index": i + 1,
                        "pipeline_name": pipeline_flow_name,
                    },
                )
                if completed_steps:
                    self._start_next_step(step_settings)
                else:
                    # The first step keeps an execution_id adopted while reserving.
                    self.settings = step_settings
                try:
                    with self.owned_execution(
                        ctx.candidate_qids, connect_backend=step.connect_parent_backend
                    ):
                        ctx = step.execute(self, targets, ctx)
                except Exception as e:
                    run_logger.error(f"Step {step.name} failed: {e}")
                    raise
                completed_steps += 1

            run_logger.info("Pipeline completed successfully")

        except BaseException as exc:
            with contextlib.suppress(Exception):
                run_logger.error(
                    "Pipeline aborted by %s (cause=%s, context=%s, group=%s)",
                    type(exc).__name__,
                    type(exc.__cause__).__name__ if exc.__cause__ else None,
                    type(exc.__context__).__name__ if exc.__context__ else None,
                    [type(sub).__name__ for sub in getattr(exc, "exceptions", [])] or None,
                )
            raise
        finally:
            self.settings = original_settings
            self._configuration_mode = original_settings.configuration_mode
            self.plan_digest = None
            self._pipeline_active = False
            try:
                self._release_lock_if_acquired()
            finally:
                clear_current_session()

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
        if ctx.filters:
            results["filters"] = ctx.filters
        if ctx.metadata:
            results["metadata"] = ctx.metadata
        if ctx.step_results:
            results["steps"] = ctx.step_results
        return results

    def calibration_plan(self, steps: Sequence[Step]) -> dict[str, Any]:
        """The validated plan recorded in every step Execution's note.

        Lists each step's step_id and its resolved calls together with the
        workflow's per-task defaults and shared run defaults, and a digest of all
        of it that identifies this plan version on every task result
        (``invocation.plan_digest``). Each task result's own run and input
        parameter snapshots stay the record of what actually ran; the plan alone
        does not recreate hardware or calibration state.
        """
        from qdash.datamodel.task_call import calls_json, plan_digest
        from qdash.workflow.service.steps.base import CalibrationStep

        planned_steps: list[dict[str, Any]] = []
        for index, step in enumerate(steps, start=1):
            entry: dict[str, Any] = {
                "index": index,
                "name": step.name,
                "type": type(step).__name__,
                "kind": "calibration" if isinstance(step, CalibrationStep) else "transform",
            }
            if isinstance(step, CalibrationStep):
                entry["step_id"] = step.resolved_step_id
                entry["continue_on_failure"] = step.continue_on_failure
                entry["calls"] = calls_json(step.calls())
            else:
                reference = {
                    key: getattr(step, key)
                    for key in ("step", "call_id", "metric", "threshold")
                    if getattr(step, key, None) is not None
                }
                if reference:
                    entry["reference"] = reference
            planned_steps.append(entry)
        plan: dict[str, Any] = {
            "steps": planned_steps,
            "task_parameters": self.task_parameters,
            "default_run_parameters": self.default_run_parameters,
        }
        return {"digest": plan_digest(plan), **plan}


@contextlib.contextmanager
def borrowed_session(spec: WorkerSpec, qids: list[str]) -> Iterator[CalibSession]:
    """Run as an isolated worker of ``spec``'s owner for ``qids``.

    The worker inherits every measurement setting of its owner and borrows the
    owner's Execution and reservation. Leaving the block only releases the
    worker's backend: the owner records the terminal status, updates chip
    history, pushes to GitHub and releases the reservation.
    """
    session = CalibSession(spec.settings, lease=spec.lease)
    session._initialize(qids)
    try:
        yield session
    finally:
        session.release_borrowed()
