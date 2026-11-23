# Calibration Session Audit

A calibration session audit joins recorded intent, launches, results, and decisions into one
reviewable history. It describes evidence; it neither approves work nor proves hardware state.

## One audit mechanism

Calibration and agent-session audits share `audit_timeline.py`: chronological events, frozen
evidence snapshots, snapshot-bound cursors, idempotent decisions, and complete exports.
Late evidence invalidates an old snapshot instead of silently disappearing from later pages.

## Decisions

Only the session creator, with editor rights, can append a decision. Decisions remain append-only
even after the session closes and change no session state. Evidence must belong to the session;
the record freezes what QDash knew when the decision was made.

## Intent before execution

A pipeline request links to intent through `decision_id` plus `calibration_session_id`.
The decision must describe an experiment with matching scope. Never correlate intent and work
by time or name. Dispatch failures and unknown outcomes remain part of the history.

## Projections

The detail view derives experiment comparisons, the latest unsuperseded recommendation, and the
latest requested run. Requested settings and measured outputs remain separate. A recommendation
is the recorder's judgment; execution outcomes come from QDash records.

The latest requested run is not necessarily the last to finish. QDash has no authoritative
hardware-write history, so neither a recommendation nor a completed run proves which values are
currently on hardware.

## Endpoints

All routes are under `/calibration-sessions/{id}` and enforce project access.

| Route | Purpose |
| --- | --- |
| `POST /decisions` | Append a creator's decision |
| `GET /decisions` | Read decisions and linked run IDs |
| `GET /audit` | Read a snapshot page; default 100, maximum 500 events |
| `GET /audit/export` | Download the complete snapshot |

## Implementation Files

| File | Responsibility |
| --- | --- |
| `src/qdash/api/services/audit_timeline.py` | Shared snapshot and decision rules |
| `src/qdash/api/services/calibration_session_audit.py` | Timeline, export, and search projection |
| `src/qdash/api/services/calibration_audit_records.py` | Records loaded for an audit |
| `ui/src/components/features/audit/AuditTimeline.tsx` | Shared timeline UI |

## Testing

Run both router suites from the repository root:

```bash
uv run pytest tests/qdash/api/routers/test_calibration_session_audit.py tests/qdash/api/routers/test_calibration_session_two_qubit.py
```

Preserve coverage of
scope, evidence mismatches, idempotency, pagination, unknown dispatch, and request/finish order.
