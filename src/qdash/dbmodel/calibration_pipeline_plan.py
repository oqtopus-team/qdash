"""Persistence model for stored calibration pipeline plans.

A plan is a validated pipeline spec that an agent or a user stored so that a person can approve
running it by reference instead of re-reading a transcribed spec. It is a proposal only: it
starts nothing, reserves nothing, and grants nothing. Running it is a separate request
(``POST /calibration-pipelines/plans/{plan_id}/execute``) that names the review digest the
person approved.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from qdash.common.utils.datetime import now

PLAN_COLLECTION = "calibration_pipeline_plans"
# How long a stored plan can be executed. Expiry is checked on every read, independent of
# the deletion below; an expired plan is never made executable again.
PLAN_TTL = timedelta(hours=24)
# How long an expired plan is kept before MongoDB deletes it, so a late creation retry still
# gets "expired" rather than a new plan, and its review stays readable for a while.
PLAN_RETENTION_AFTER_EXPIRY = timedelta(days=7)
# The largest spec a plan stores, as UTF-8 JSON.
MAX_PLAN_SPEC_BYTES = 256 * 1024


class CalibrationPipelinePlanDocument(Document):
    """One stored plan: the normalized spec and the review content an approval covers.

    ``plan_id`` is an opaque, fresh identifier. ``creation_scope`` is the creator and the
    idempotency key the plan was created with, unique per project: a repeated creation with
    the same key returns this plan (or reports it expired) and never stores another one or
    changes this one. ``request_hash`` is what such a repetition must repeat. The document is
    written once and never updated.
    """

    plan_id: str
    project_id: str
    created_by: str
    chip_id: str
    backend_name: str
    creation_scope: str
    request_hash: str
    # The normalized spec, with every default task list written out (what is dispatched).
    spec: dict[str, Any]
    # ``qdash.datamodel.calibration_plan.review_content``: what an approval binds to.
    review: dict[str, Any]
    review_digest: str
    # The validation answer shown with the plan: resolved steps and calls, targets, warnings.
    preview: dict[str, Any]
    created_at: datetime = Field(default_factory=now)
    expires_at: datetime
    delete_after: datetime

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """MongoDB collection settings."""

        name = PLAN_COLLECTION
        indexes: ClassVar = [
            IndexModel([("plan_id", ASCENDING)], unique=True),
            IndexModel(
                [("project_id", ASCENDING), ("creation_scope", ASCENDING)],
                name="plan_creation_scope_unique",
                unique=True,
            ),
            IndexModel([("delete_after", ASCENDING)], expireAfterSeconds=0),
        ]
