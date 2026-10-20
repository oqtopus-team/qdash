# Dashboard

Use **Dashboard** to scan every configured metric for one chip, then open a target when a value
needs investigation or context.

## Select the Data Scope

1. Open **Dashboard** and select a chip.
2. Select a relative or absolute time range, or choose a cool-down.
3. Set **Value selection** to latest, best, or average.

The selected time range and value mode apply to the summary and every metric section. Include
them when sharing an observation because another scope can show a different record.

## Scan Chip Health

Start with the collapsed all-metrics summary. It shows coverage, median, minimum, and maximum for
each metric in the selected scope.

Continue to **Qubit Metrics** and **Coupling Metrics** for topology and distribution views. Each
metric shows its own coverage. Metrics without data stay grouped separately so missing data does
not obscure the populated metrics.

## Investigate a Target

Select a qubit or coupling in a metric to open its history. Use the history and selected task
result to decide whether the value is an isolated measurement, part of a trend, or related to
another target.

Open **Metrics** when the investigation starts from one metric across many targets. Open
**Task Results** when it starts from a specific measurement or failure.

## Record Context

Use a pinned summary for context that should remain visible with a chip, qubit, or coupling in
the selected cool-down or time range. Use a task-result note for context about one measurement,
such as an anomaly or the reason for a parameter choice.

1. Edit the chip note above the target summaries for chip-wide context.
2. Select a qubit or coupling to edit its pinned summary.
3. Select a task result in the history view to add a note about that measurement.

The notes summary gathers the notes visible in the current scope. Select a target summary to
return to its dashboard view, or select a task-result note to open the result. Notes are shared
with the project, and QDash records the last editor.

Existing per-metric notes remain visible as read-only context. Add new context as a pinned summary
or a forum discussion. How this works: [Notes architecture](../developer-guide/architecture/notes.md).
