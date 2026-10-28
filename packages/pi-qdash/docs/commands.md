# Commands

pi-qdash provides the following slash commands in interactive pi:

```text
/qdash-setup [profile] [chip_id]
/qdash-use-profile <profile>
/qdash-use-chip [chip_id]
/qdash-use-agent-session <session_id>
/qdash-investigation-setup [json]
/qdash-clear-investigation
/qdash-context
/qdash-dashboard [limit]
/qdash-target-report qid <qid> | coupling <coupling_id>
/qdash-plan-calibration
/qdash-degradation-report
/qdash-wiring-insights
/qdash-refresh [limit]
/qdash-clear-context
/qdash-config [profile]
```

For the common path, run `/qdash-setup <profile> <chip_id>` first. The setup
command stores the session-local profile/chip context, refreshes the footer
status line, and opens the dashboard widget.

`/qdash-investigation-setup` opens a JSON editor (or accepts JSON directly) for
a reusable, schema-validated session timeseries investigation context. It is
stored in the pi session but excluded from the global profile/chip context so
local CSV paths do not silently carry into unrelated projects. It can hold
arbitrary QDash series, local CSV mappings, time window/timezone, and transform
settings. `qdash_compare_timeseries` fills only omitted arguments from this
context; pass `useInvestigationContext: false` for a one-off comparison.
`/qdash-clear-investigation` clears the investigation preset without changing
the active profile or chip.

These commands manage session-local QDash context, update the pi
status/widget, show or refresh a themed compact QDash dashboard, and show
non-secret QDash configuration details. Tools use the current profile/chip
context when their parameters are omitted. In interactive mode, the
highlighted footer status line shows the active QDash profile, chip, and agent
session.

## Skills

The package also provides skills:

- `/skill:qdash`: guides pi to choose the right QDash tools, avoid exposing secrets, and prefer read-only operations
- `/skill:qdash-calibration-agent`: guides pi through confirmation-gated calibration execution workflows
- `/skill:qdash-two-qubit-calibration-diagnosis`: diagnoses two-qubit calibration quality from read-only evidence
- `/skill:qdash-timeseries-diagnosis`: investigates generic multi-metric drift, shared periodicity, phase, and environmental sensor coupling without hard-coded metrics or CSV schemas
