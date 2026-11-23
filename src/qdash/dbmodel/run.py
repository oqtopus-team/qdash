"""Persistence model for runs: one record per launch, written before the launch.

The collection keeps its original name, ``calibration_pipeline_runs``. Renaming it would make
two ledgers for one launch during an upgrade or a rollback, and a retry looked up in one of
them could launch a run the other already holds; one collection with additive fields cannot.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from qdash.common.utils.datetime import now
from qdash.datamodel.launch_origin import ReportedLaunchOrigin  # noqa: TC001 - Bunnet field
from qdash.datamodel.run import (
    CalibrationPipelineRunStatus,
    CalibrationRunKind,
    CalibrationRunTrigger,
    RunAdmission,
    RunAssociation,
)

RUN_COLLECTION = "calibration_pipeline_runs"
# The unique index of the run scope (see ``RunDocument.idempotency_scope``).
RUN_SCOPE_INDEX = "run_idempotency_scope_unique"
# The unique index runs were keyed by before they had a scope. A run without a calibration
# session cannot be held to it (every such run would share the null session), so
# ``python -m qdash.dbmodel.migration prepare-run-scope`` drops it before
# automatic grouping is turned off. It is no longer declared, so it is not created again.
LEGACY_SESSION_KEY_INDEX = "project_id_1_calibration_session_id_1_idempotency_key_1"
# Ordered keys of the two indexes above, as ``index_information()`` reports them.
RUN_SCOPE_INDEX_KEYS = (("project_id", 1), ("idempotency_scope", 1))
LEGACY_SESSION_KEY_INDEX_KEYS = (
    ("project_id", 1),
    ("calibration_session_id", 1),
    ("idempotency_key", 1),
)
# A launch reports back within seconds; a run still ``dispatching`` after this, or a
# reservation still pending after this, belongs to a request that may have died.
RUN_DISPATCH_STALE_AFTER = timedelta(minutes=5)


class RunDocument(Document):
    """One run, recorded before its launch: the authority for retrying and carrying it out.

    Identity and retry: ``run_id`` is unique. A run recorded by this release is found by a
    retry through ``idempotency_scope``, unique per project: for a request's key it is
    derived from the signed-in user and the key, never from the calibration session, so a
    retry finds the run whether or not it joined a session and whether or not that session
    still exists. ``request_hash`` is what a retry must repeat; for a request that named a
    calibration session it includes that session, so the same key with another session is a
    different request. A run recorded before scopes existed has none and is found by its
    original scope, ``(project_id, calibration_session_id, idempotency_key)``.

    Launch: ``dispatch_token`` names the attempt that holds the launch; only that attempt
    settles it, and only a flow run presenting it can bind the run (``flow_run_id``), once.
    ``admission`` says whether that attempt may be carried out. Once dispatched, the run's
    step executions are the executions of the project and chip whose
    ``note.calibration_run_id`` is ``run_id``, or, for runs recorded before that note existed,
    whose ``note.flow_run_id`` is ``flow_run_id``.

    Grouping: ``calibration_session_id`` is the calibration session the run belongs to, or
    None. Removing the association, or turning grouping off, changes none of the above.

    A run the worker found unrecorded (a scheduled flow run) is inserted by the worker when
    the flow starts, already ``dispatched``, with IDs derived from its flow run, so a Prefect
    retry of the same flow run finds it instead of adding another.
    """

    run_id: str
    project_id: str
    # The calibration session the run belongs to; None for a run that joins none. Every run
    # recorded before runs could stand alone has one.
    calibration_session_id: str | None = None
    # How the run joined its session (``none`` for a run without one); None for a run
    # recorded before this was stored.
    association: RunAssociation | None = None
    chip_id: str
    run_kind: CalibrationRunKind = CalibrationRunKind.PIPELINE
    trigger: CalibrationRunTrigger = CalibrationRunTrigger.API
    # What the run launched: the workflow name, the pipeline name, or the task and target.
    run_name: str = ""
    # For an agent action's run: the agent session and the action that dispatched it.
    agent_session_id: str | None = None
    action_id: str | None = None
    # The key as the caller sent it (or as QDash generated it, ``srv-``; or derived from the
    # flow run, ``flow-run:``, or the action, ``agent-action:``). Shown, never looked up alone.
    idempotency_key: str
    # What a retry is found by, unique in the project: ``key:<digest of user and key>`` for a
    # request's key, ``flow-run:<id>`` for a run the worker recorded, ``agent-action:<id>``
    # for an agent action. None for a run recorded before scopes existed.
    idempotency_scope: str | None = None
    request_hash: str
    requested_by: str
    # How the caller said it started the run (client reported, never verified); None when it
    # reported nothing. ``requested_by`` stays the user the request authenticated.
    reported_origin: ReportedLaunchOrigin | None = None
    status: CalibrationPipelineRunStatus = CalibrationPipelineRunStatus.DISPATCHING
    dispatch_token: str
    # The calibration session reservation of the attempt that holds ``dispatch_token``, or
    # None for a run that joins no session. The attempt launches only after removing that
    # reservation, so a run still ``dispatching`` whose reservation is pending or was cleared
    # by a close was never launched.
    reservation_id: str | None = None
    # Whether the attempt that holds ``dispatch_token`` may be carried out: written
    # ``pending`` with a reservation and ``admitted`` once the reservation was finalized, or
    # ``admitted`` at once for a run without one. The worker reads it here, never from the
    # session. None for a run recorded before it was stored, whose admission is read from its
    # session's pending reservations as it was then.
    admission: RunAdmission | None = None
    attempts: int = 1
    # Only for ``run_kind`` ``pipeline``; ``run_name`` names every kind.
    pipeline_name: str = ""
    backend_name: str = ""
    flow_run_id: str | None = None
    # The execution QDash pre-created for the first step; None when pre-creation failed.
    execution_id: str | None = None
    # The dispatch response, returned unchanged to a retry of the same request.
    response: dict[str, Any] | None = None
    error: str = ""
    # The normalized spec QDash validated for the attempt that holds the launch: the exact
    # request, so the audit can compare requested and executed run parameters. None for runs
    # recorded before it was stored.
    spec: dict[str, Any] | None = None
    # The decision of the session this run carries out, named by the request; None when the
    # request named none (every run recorded before decisions existed).
    decision_id: str | None = None
    requested_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """MongoDB collection settings."""

        name = RUN_COLLECTION
        indexes: ClassVar = [
            IndexModel([("run_id", ASCENDING)], unique=True),
            IndexModel(
                [("project_id", ASCENDING), ("idempotency_scope", ASCENDING)],
                name=RUN_SCOPE_INDEX,
                unique=True,
                partialFilterExpression={"idempotency_scope": {"$type": "string"}},
            ),
            # A retry of a run recorded before scopes existed is found by its original scope.
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("calibration_session_id", ASCENDING),
                    ("requested_at", ASCENDING),
                ]
            ),
            # The Execution list finds the run a step execution belongs to by its flow run.
            IndexModel([("project_id", ASCENDING), ("flow_run_id", ASCENDING)]),
            IndexModel(
                [("project_id", ASCENDING), ("agent_session_id", ASCENDING)],
                sparse=True,
            ),
        ]
