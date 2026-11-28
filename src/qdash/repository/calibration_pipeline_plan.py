"""Stored calibration pipeline plans: written once, read by their creator only."""

from __future__ import annotations

from qdash.dbmodel.calibration_pipeline_plan import CalibrationPipelinePlanDocument


def find_plan(
    project_id: str, created_by: str, plan_id: str
) -> CalibrationPipelinePlanDocument | None:
    """The plan of this project created by this user, or None (also for another user's)."""
    return CalibrationPipelinePlanDocument.find_one(
        {"project_id": project_id, "plan_id": plan_id, "created_by": created_by}
    ).run()


def find_plan_by_scope(
    project_id: str, creation_scope: str
) -> CalibrationPipelinePlanDocument | None:
    """The plan created with this creation scope (creator and idempotency key), or None."""
    return CalibrationPipelinePlanDocument.find_one(
        {"project_id": project_id, "creation_scope": creation_scope}
    ).run()


def insert_plan(doc: CalibrationPipelinePlanDocument) -> None:
    """Insert a new plan; ``DuplicateKeyError`` when its creation scope is taken."""
    doc.insert()
