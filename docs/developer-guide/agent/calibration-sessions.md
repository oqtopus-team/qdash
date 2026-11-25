# Calibration Sessions

A calibration session groups runs toward one objective on one chip. It grants no authority and
holds no hardware; an agent session retains its own policy and each run its own lifecycle.

## Runs stand alone; sessions group them

A session holds runs; each run holds its step executions. Launching a workflow, pipeline, or task
without an explicit objective creates an automatic session. Older records are not backfilled.

Membership is explicit: a run or agent session names `calibration_session_id`, and step executions
carry `note.calibration_run_id`. Never infer membership from timestamps, names, tags, or chat text.

## Authoring API and group names

SDK callers create or open `qdash.sdk.CalibrationSession`, then pass shared targets and steps
to `run()` or `submit()`. Workflow authors use `qdash.workflow.CalibrationSession.from_context()`;
it participates in the enclosing flow run rather than creating a remote launch per call.
The persisted group, public operation handle, and internal `ExecutionRuntime` have separate
responsibilities: only the runtime manages hardware reservations.

Templates declare `@calibration_flow(session_name="Coherence check")`. The API reads this
literal from the saved entrypoint before creating an automatic session. Scheduled/direct flow
runs use the decorator's metadata when the worker first records their run. Explicit existing
session membership takes precedence and its objective is never renamed by a template.
Without the metadata, the existing automatic naming behavior applies.

A name is trimmed and limited to 500 characters. Saving rejects empty, oversized, non-string
or expression-based `session_name` values with HTTP 400; omitted names and literal `None`
keep the default. The API never evaluates source expressions. Previously saved invalid
metadata is still read defensively, so resave with a valid literal to align launch paths. SDK `create(..., name=...)` stores the name as the session
objective. See the [SDK example](../../reference/clients/python.md#run-a-calibration) and
[workflow authoring](../workflow/quickstart.md#define-a-flow).

## Step Execution History

All reached steps now have an Execution, including filters and schedules. This adds records
inside each run without changing its admission, identity or Session membership. Unreached
steps create no records; historical unrecorded transforms remain unrecorded. No data migration
or backfill is required. [Pipeline progress](../workflow/calibration-pipeline.md#following-a-run)
distinguishes pending, skipped and historically unrecorded steps.

## Agent session admission

A child must belong to the same project and chip, and its creator must own the open session.
Admission reserves a place in the session, writes the child, then finalizes the reservation.
A pending or rejected agent session cannot operate. Recovery reads the admission outcome from
the parent rather than guessing after a crash.

## Dispatch is recorded before launch

`RunLedger.launch` records `dispatching` before creating a Prefect flow run. Unique idempotency
scope and conditional updates prevent duplicate launches. Uncertain dispatch stays uncertain;
it must not be retried as if no operation existed.

Every step execution carries the run ID. Detail and grouped-list reads use that recorded relation,
so a multi-step workflow appears as one run without losing its individual executions.

## Closing

The creator can close a session explicitly. QDash also closes automatic sessions once all their
work has ended. Manual objective sessions remain open for further trials. Closing blocks new
admission; it neither cancels admitted work nor declares success.

`CalibrationSessionLifecycle` checks automatic sessions every 60 seconds in each API process
and on detail reads. It checks all children, independently of display pagination. Every dispatched
run must have a recorded flow ID and a current Prefect state of COMPLETED, FAILED, CANCELLED,
or CRASHED. Agent sessions must have ended with no in-flight measurements, commits, or backend
applies, or have been rejected before operating. Pending reservations, unknown dispatches,
missing flow records, and retries still waiting to run prevent automatic close.

Workflow, pipeline, Workbench, and task-result re-execution API launches check existing
hardware claims after validation and idempotent replay, before recording a new run or session.
An existing conflict returns 409 without those records. The atomic claim at dispatch still
handles races; a conflict acquired after the check can leave a rejected run.
A recorded rejected non-agent run keeps its session open so the same key can retry. Existing stale
pipeline-reservation recovery can reject an unlaunched attempt; it does not make that session
eligible to close. Automatic close never acknowledges unknown work.

A sweep visits 50 sessions, least recently checked first, and reads at most 1,000 flow IDs in
five batched Prefect requests. Deferred sessions retain their place for a later sweep. A single
session with more than 1,000 flow IDs requires explicit close. There is no configuration step;
backlogs and Prefect outages can delay closure beyond one interval. List requests do not query
Prefect. Existing automatic sessions use the same evidence checks without inventing old outcomes.

The close update compares the child count and requires no pending reservations. A concurrent
child admission makes it fail. Prefect reads and MongoDB updates are not atomic: an external
restart after the final read can race with close. Closed sessions are not reopened or monitored;
start a new QDash run for new work.

`close_origin=automatic` and `closed_by=system:auto-close` identify a system close. The note
records observed outcomes. `flow_end_state` is display evidence from lifecycle checks, not a
live status or authorization: it clears when a check observes a resumed flow, but can remain
stale when Prefect is unavailable or the session is no longer checked.

## Reported launch origin

QDash authenticates the user, not the software using their token. `reported_origin` records a
client's claim that an agent tool launched a pipeline. Present it as reported, never verified.
Belonging to a calibration objective does not itself make a run an agent run.

## The Execution list links back

Execution responses expose the recorded session relationship. Grouped views deduplicate runs and
nested agent sessions before paging. Chats discover links from successful tool calls rather than
assistant prose. [Calibration Session Audit](./calibration-session-audit.md) describes decisions
and search progression.

## Deployment compatibility

Upgrade the API atomically before deploying associated SDKs and tools. A mixed fleet can ignore
new association fields and dispatch without the expected ledger; a preflight against one new
process does not make it safe.

## Implementation Files

| File | Responsibility |
| --- | --- |
| `src/qdash/api/services/calibration_session_service.py` | Creation, admission, closing |
| `src/qdash/api/services/calibration_session_lifecycle.py` | Automatic close and reconciliation |
| `src/qdash/api/services/run_ledger.py` | Idempotent dispatch |
| `src/qdash/api/services/calibration_session_links.py` | Execution relationships |
| `src/qdash/api/services/calibration_session_groups.py` | Grouped projections |
| `src/qdash/datamodel/run.py` | Run identity and lifecycle |

## Testing

Run `uv run pytest tests/qdash/workflow/test_calibration_run_grouping_fake_e2e.py` for whole-run
association. API tests must cover admission/close races, duplicate requests, unknown dispatches,
legacy records, and project isolation when these boundaries change.

Run `uv run pytest tests/qdash/api/services/test_calibration_session_lifecycle.py` for terminal
state checks, retry blockers, admission races, resumed flows, and bounded sweep recovery.
