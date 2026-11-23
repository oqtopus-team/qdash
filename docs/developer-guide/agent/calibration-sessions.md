# Calibration Sessions

A calibration session groups runs toward one objective on one chip. It grants no authority and
holds no hardware; an agent session retains its own policy and each run its own lifecycle.

## Runs stand alone; sessions group them

A session holds runs; each run holds its step executions. Launching a workflow, pipeline, or task
without an explicit objective creates an automatic session. Older records are not backfilled.

Membership is explicit: a run or agent session names `calibration_session_id`, and step executions
carry `note.calibration_run_id`. Never infer membership from timestamps, names, tags, or chat text.

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

Only the creator closes a session. Closing blocks new admission, but cancels no admitted child,
grants no success verdict, and may leave already admitted work in progress. Pending reservations
and unknown dispatches are handled explicitly before closing.

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
| `src/qdash/api/services/run_ledger.py` | Idempotent dispatch |
| `src/qdash/api/services/calibration_session_links.py` | Execution relationships |
| `src/qdash/api/services/calibration_session_groups.py` | Grouped projections |
| `src/qdash/datamodel/run.py` | Run identity and lifecycle |

## Testing

Run `uv run pytest tests/qdash/workflow/test_calibration_run_grouping_fake_e2e.py` for whole-run
association. API tests must cover admission/close races, duplicate requests, unknown dispatches,
legacy records, and project isolation when these boundaries change.
