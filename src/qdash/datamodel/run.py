"""Runs: one launch QDash records before it creates the flow run that carries it out.

A run is the durable record of one launch, whatever it launched (a saved workflow, a
calibration pipeline, a single task, or an agent action). It owns what makes the launch safe
to retry and to execute: the launch intent and its request hash, the idempotency scope a
retry is found by, the dispatch token of the attempt that holds the launch, the dispatch
outcome, the admission of that attempt, and the binding to the one flow run that carries it
out. The worker stamps the run's ID on every step execution, so the step executions in
``execution_history`` and ``task_result_history`` stay the measurement record and the run
says which launch they came from.

A run may also belong to a calibration session, which records the purpose it was started for
(``calibration_session_id``). That association is optional: a run without one is just as
valid, retryable, and bindable, and nothing about a run's guarantees is read from its
session. A session can stop new runs from joining it (a close); it can never invalidate a run
already admitted, and it never authorizes an operation.

Some names keep the vocabulary of the first kind of run, pipeline runs, because they are part
of the API schema or the stored data: the enums below keep their class names (their OpenAPI
component names), the collection is still ``calibration_pipeline_runs``, and the flow-run
context key is still ``qdash_calibration_run``. ``RunKind``, ``RunTrigger``, and
``RunDispatchStatus`` are the canonical names in code.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# Key of the Prefect flow-run context that carries a run's identity to the worker. The wire
# name is unchanged so that a worker and an API of the same release agree on it.
RUN_CONTEXT_KEY = "qdash_calibration_run"


class CalibrationRunKind(StrEnum):
    """What one run launched.

    ``pipeline``: a calibration pipeline spec (every run recorded before other kinds existed).
    ``workflow``: a saved workflow (flow). ``task``: one catalog task, from the Task Workbench
    or a re-execution. ``agent_action``: the task an agent session's action ran.
    """

    PIPELINE = "pipeline"
    WORKFLOW = "workflow"
    TASK = "task"
    AGENT_ACTION = "agent_action"


class CalibrationRunTrigger(StrEnum):
    """Who started a run, as QDash recorded it.

    ``api``: a signed-in request to QDash recorded the run before launching it. ``schedule``:
    Prefect's scheduler started the flow run from a cron schedule; the worker recorded it when
    the flow started. ``worker``: the worker found a flow run QDash had not recorded (a
    one-time schedule, or a run started in Prefect directly) and recorded it when it started.
    """

    API = "api"
    SCHEDULE = "schedule"
    WORKER = "worker"


class CalibrationPipelineRunStatus(StrEnum):
    """Dispatch state of one run, whatever its kind.

    ``dispatching``: the request was recorded and its launch has not reported back.
    ``dispatched``: QDash created the run's flow run; its executions carry its ``run_id``.
    ``rejected``: QDash refused the launch before any flow run was created (the hardware was
    busy, the worker deployment was missing, or the attempt was never admitted); a retry with
    the same key may launch it.
    ``unknown``: the launch failed in a way that may have created a flow run anyway, or it
    stayed ``dispatching`` past the time a launch takes. A retry with the same key never
    launches it again.
    """

    DISPATCHING = "dispatching"
    DISPATCHED = "dispatched"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


# Canonical names in code; the classes keep their names for the API schema.
RunKind = CalibrationRunKind
RunTrigger = CalibrationRunTrigger
RunDispatchStatus = CalibrationPipelineRunStatus


class RunAdmission(StrEnum):
    """Whether the attempt that holds a run's launch may be carried out by a flow run.

    Stored on the run itself, so the worker checks it without reading any calibration
    session. ``pending``: the attempt still waits to be admitted to the calibration session
    the run joins; no flow run may carry it out. ``admitted``: the attempt was admitted (its
    reservation in the session was finalized, or the run joins no session and needs none).
    Admission is written before the launch and never revoked. A run recorded before admission
    was stored has none; see ``RunDocument.admission``.
    """

    PENDING = "pending"
    ADMITTED = "admitted"


class RunAssociation(StrEnum):
    """How a run came to belong to its calibration session, or that it belongs to none.

    ``explicit``: the request named the session. ``automatic``: QDash created or chose an
    automatic session for it because automatic grouping was on. ``agent_session``: an agent
    action's run, in the calibration session its agent session was admitted to. ``none``: the
    run joins no session (automatic grouping was off and the request named none, or the
    agent session it serves has no calibration session).
    """

    EXPLICIT = "explicit"
    AUTOMATIC = "automatic"
    AGENT_SESSION = "agent_session"
    NONE = "none"


class CalibrationSessionGrouping(StrEnum):
    """Deployment setting: whether QDash groups runs that name no calibration session.

    ``automatic`` (the default): a run started without a calibration session ID, and an agent
    session started without one, gets an automatic session of its own. ``explicit``: they
    join no session; only a run or agent session that names a session joins one. Either way a
    named session is checked and reserved before anything starts, and a refusal is returned,
    never turned into an ungrouped run.
    """

    AUTOMATIC = "automatic"
    EXPLICIT = "explicit"


class RunIdentity(BaseModel):
    """The run a flow run carries out, and its calibration session if it has one.

    Handed to the worker in the flow-run context (``RUN_CONTEXT_KEY``). ``dispatch_token``
    is the opaque token of the launch attempt QDash recorded for the run, generated by the
    API and stored only on the run's record. The API hands it to the flow run it creates, so
    the worker can prove that the flow run is the one QDash dispatched for the run: IDs alone
    are not a claim. It is never part of an API response, an execution note, or a log line;
    identities the worker records itself carry none.
    """

    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(min_length=1)
    calibration_session_id: str | None = Field(default=None, min_length=1)
    dispatch_token: str | None = Field(default=None, repr=False)
