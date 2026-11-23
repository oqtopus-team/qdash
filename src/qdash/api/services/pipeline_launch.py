"""Record the origin a caller reported when it launched a pipeline."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pymongo.errors import DuplicateKeyError

from qdash.dbmodel.pipeline_launch import PipelineLaunchDocument

if TYPE_CHECKING:
    from qdash.api.schemas.flow import ExecuteFlowResponse
    from qdash.datamodel.launch_origin import ReportedLaunchOrigin

logger = logging.getLogger("uvicorn.app")


def record_pipeline_launch(
    *,
    project_id: str,
    chip_id: str,
    username: str,
    dispatched: ExecuteFlowResponse,
    reported_origin: ReportedLaunchOrigin | None,
) -> None:
    """Store the reported origin of a launched pipeline, keyed by its flow run.

    Best effort: the run has already started, and a failure here only leaves it without an
    origin claim, which readers show as unspecified. Nothing is written without a report.
    """
    if reported_origin is None or not dispatched.flow_run_id:
        return
    execution_id = dispatched.execution_id
    try:
        PipelineLaunchDocument(
            project_id=project_id,
            chip_id=chip_id,
            flow_run_id=dispatched.flow_run_id,
            # The response falls back to the flow run ID when no execution was pre-created.
            execution_id=execution_id if execution_id != dispatched.flow_run_id else None,
            requested_by=username,
            reported_origin=reported_origin,
        ).insert()
    except DuplicateKeyError:
        # A flow run is launched once; a second write for it adds nothing.
        return
    except Exception:
        logger.exception(
            "Failed to record the reported origin of pipeline flow run %s", dispatched.flow_run_id
        )
