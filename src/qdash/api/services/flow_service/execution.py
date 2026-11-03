"""Execution lock coordination and Prefect flow-run dispatch."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from qdash.api.services.flow_service.prefect_gateway import PrefectGateway
from qdash.common.config.path_resolver import execution_calib_data_dir
from qdash.common.execution_resources import (
    resolve_execution_resource_scope,
    resolve_workflow_resource_scope,
)
from qdash.common.utils.datetime import now
from qdash.config import get_settings
from qdash.datamodel.execution import ExecutionModel, ExecutionStatusModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.repository import MongoExecutionRepository
from qdash.repository.execution_id import generate_execution_id

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from qdash.repository import MongoExecutionLockRepository

logger = logging.getLogger("uvicorn.app")

EXECUTION_IN_PROGRESS_DETAIL = (
    "Another calibration execution is using overlapping hardware resources"
)

_WHOLE_CHIP_REASON = (
    "This workflow requires the entire chip for its steps. "
    "Another calibration is using this chip; wait for it to finish."
)
_SCOPED_CONFLICT_REASON = (
    "Another calibration is using hardware required by this run. "
    "Wait for it to finish or select different targets."
)


class FlowDispatchError(RuntimeError):
    """Raised when Prefect cannot create a flow run for a dispatched execution."""


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Prefect and QDash identifiers for a dispatched run."""

    flow_run_id: str
    flow_run_url: str
    execution_id: str | None
    qdash_ui_url: str


class ExecutionCoordinator:
    """Claim the execution lock, dispatch the run and record it before it starts."""

    def __init__(
        self,
        *,
        lock_repository: MongoExecutionLockRepository | None = None,
        execution_repository: MongoExecutionRepository | None = None,
        prefect: PrefectGateway | None = None,
        id_factory: Callable[..., str] = generate_execution_id,
    ) -> None:
        self._locks = lock_repository
        self._executions = execution_repository
        self._prefect = prefect or PrefectGateway()
        self._new_execution_id = id_factory

    def availability(
        self,
        *,
        project_id: str,
        chip_id: str,
        parameters: dict[str, Any],
        workflow: bool,
    ) -> tuple[bool, str | None]:
        """Report whether the hardware a run needs is free, without claiming it."""
        if self._locks is None:
            raise HTTPException(status_code=503, detail="Execution availability is unavailable")

        scope = (
            resolve_workflow_resource_scope(chip_id)
            if workflow
            else resolve_execution_resource_scope(chip_id, parameters)
        )
        if self._locks.has_conflict(project_id, scope):
            return False, _WHOLE_CHIP_REASON if workflow else _SCOPED_CONFLICT_REASON
        return True, None

    async def dispatch_run(
        self,
        *,
        project_id: str,
        username: str,
        chip_id: str,
        name: str,
        deployment_id: UUID | str,
        parameters: dict[str, Any],
        tags: list[str] | None = None,
        workflow: bool = False,
    ) -> DispatchResult:
        """Dispatch a run that owns the execution lock until the flow adopts it."""
        claimed_execution_id = self._claim(
            project_id=project_id,
            username=username,
            chip_id=chip_id,
            parameters=parameters,
            workflow=workflow,
        )

        try:
            flow_run_id = await self._prefect.create_flow_run(
                deployment_id=deployment_id,
                parameters=parameters,
            )
        except Exception as exc:
            # Nothing reached Prefect, so the flow will never adopt the lock.
            self._release(project_id, claimed_execution_id)
            raise FlowDispatchError(str(exc)) from exc

        execution_id = self._create_scheduled_execution(
            project_id=project_id,
            username=username,
            chip_id=chip_id,
            name=name,
            flow_run_id=flow_run_id,
            execution_id=claimed_execution_id,
            tags=tags,
        )
        if execution_id is None:
            self._release(project_id, claimed_execution_id)

        settings = get_settings()
        return DispatchResult(
            flow_run_id=flow_run_id,
            flow_run_url=_flow_run_url(settings.prefect_port, flow_run_id),
            execution_id=execution_id,
            qdash_ui_url=_qdash_ui_url(settings.ui_port, chip_id, execution_id),
        )

    async def dispatch_background(
        self,
        *,
        deployment_id: UUID | str,
        parameters: dict[str, Any],
    ) -> str:
        """Dispatch a run that owns no execution lock and records no execution row."""
        try:
            flow_run_id = await self._prefect.create_flow_run(
                deployment_id=deployment_id,
                parameters=parameters,
            )
        except Exception as exc:
            raise FlowDispatchError(str(exc)) from exc

        return flow_run_id

    async def read_deployment_id(self, deployment_name: str) -> UUID:
        """Resolve the deployment ID of a system deployment."""
        return await self._prefect.read_deployment_id(deployment_name)

    async def delete_deployment(self, deployment_id: str) -> None:
        """Drop the Prefect deployment of a flow that is being deleted."""
        await self._prefect.delete_deployment(deployment_id)

    def _claim(
        self,
        *,
        project_id: str,
        username: str,
        chip_id: str,
        parameters: dict[str, Any],
        workflow: bool,
    ) -> str | None:
        """Claim the project execution lock for a run about to be dispatched.

        The claim is atomic, so concurrent requests are serialized before any
        Prefect flow run is created. It is skipped when no ``chip_id`` can be
        resolved, since there is then no execution ID to own the lock; such a
        run falls back to the flow taking the lock itself, as cron schedules
        do.
        """
        if self._locks is None or not chip_id:
            return None

        execution_id = self._new_execution_id(username, chip_id, project_id=project_id)
        scope = (
            resolve_workflow_resource_scope(chip_id)
            if workflow
            else resolve_execution_resource_scope(chip_id, parameters)
        )
        if not self._locks.try_lock(
            project_id=project_id,
            execution_id=execution_id,
            chip_id=scope.chip_id,
            resources=scope.resources,
            exclusive=scope.exclusive,
        ):
            raise HTTPException(status_code=409, detail=EXECUTION_IN_PROGRESS_DETAIL)
        return execution_id

    def _release(self, project_id: str, execution_id: str | None) -> None:
        """Release a lock claimed for a run that never reached the flow process.

        Once the ``scheduled`` execution exists, the lock is released by
        whoever closes it, so this only covers dispatch failures in between.
        Releasing is best effort: a failure here is logged rather than raised
        over the original error.
        """
        if execution_id is None or self._locks is None:
            return
        try:
            self._locks.unlock(project_id=project_id, execution_id=execution_id)
        except Exception:
            logger.warning(
                "Failed to release the execution lock claimed for execution_id=%s",
                execution_id,
                exc_info=True,
            )

    def _create_scheduled_execution(
        self,
        *,
        project_id: str,
        username: str,
        chip_id: str | None,
        name: str,
        flow_run_id: str,
        execution_id: str | None = None,
        tags: list[str] | None = None,
    ) -> str | None:
        """Pre-create a scheduled execution row for a freshly created flow run.

        This makes the run visible in execution history immediately, before the
        flow process itself has had a chance to create its own execution record,
        so that a run which fails or is orphaned before reaching that point can
        still be found and closed (by the flow's own hooks or by reconciliation).

        Pre-creation is deliberately best effort: the Prefect flow run has
        already been created by the time this runs, and a bookkeeping failure
        here is not a reason to cancel a healthy calibration. On failure the
        run is left going and ``CalibService._initialize()`` allocates an
        execution ID of its own at flow start, exactly as it does for runs that
        never went through the API (cron schedules). Callers fall back to the
        flow run ID for the response, so the only thing lost is the
        ``scheduled`` row that would have been visible before the flow started.
        """
        if not chip_id:
            logger.warning(
                f"Skipping scheduled execution pre-creation for flow run "
                f"{flow_run_id}: no chip_id could be resolved"
            )
            return None

        try:
            if execution_id is None:
                execution_id = self._new_execution_id(username, chip_id, project_id=project_id)
            calib_data_path = str(execution_calib_data_dir(username, execution_id))

            model = ExecutionModel(
                project_id=project_id,
                username=username,
                name=name,
                execution_id=execution_id,
                calib_data_path=calib_data_path,
                note={"flow_run_id": flow_run_id},
                status=ExecutionStatusModel.SCHEDULED,
                tags=tags or [],
                chip_id=chip_id,
                start_at=now(),
                end_at=None,
                elapsed_time=None,
                message="",
                system_info=SystemInfoModel(),
            )
            (self._executions or MongoExecutionRepository()).save(model)
            return execution_id
        except Exception:
            logger.warning(
                "Failed to pre-create scheduled execution for flow_run_id=%s",
                flow_run_id,
                exc_info=True,
            )
            return None


def _flow_run_url(prefect_port: int, flow_run_id: str) -> str:
    """Build the Prefect UI URL of a flow run."""
    return f"http://localhost:{prefect_port}/runs/flow-run/{flow_run_id}"


def _qdash_ui_url(ui_port: int, chip_id: str | None, execution_id: str | None) -> str:
    """Build the QDash UI URL of an execution."""
    base = f"http://localhost:{ui_port}/execution"
    if not chip_id:
        return base
    if not execution_id:
        return f"{base}/{chip_id}"
    return f"{base}/{chip_id}/{execution_id}"
