"""Persistence model for the origin a caller reported when it launched a pipeline."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Bunnet resolves this runtime annotation
from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from qdash.common.utils.datetime import now
from qdash.datamodel.launch_origin import (  # noqa: TC001 - Bunnet resolves this runtime annotation
    ReportedLaunchOrigin,
)


class PipelineLaunchDocument(Document):
    """The origin reported for one dispatched pipeline flow run.

    Written by the API after it created the flow run, only when the request reported an
    origin. Every step execution of the pipeline carries ``flow_run_id`` in
    ``note.flow_run_id``, so the report applies to all of them. ``requested_by`` is the user
    the request authenticated; ``reported_origin`` is what the caller said and is never
    verified.
    """

    project_id: str
    chip_id: str
    flow_run_id: str
    # The execution QDash pre-created for the first step; None when pre-creation failed.
    execution_id: str | None = None
    requested_by: str
    reported_origin: ReportedLaunchOrigin
    created_at: datetime = Field(default_factory=now)

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """MongoDB collection settings."""

        name = "pipeline_launches"
        indexes: ClassVar = [
            IndexModel(
                [("project_id", ASCENDING), ("flow_run_id", ASCENDING)],
                unique=True,
            ),
        ]
