"use client";

import { transformRecordOf, transformSummary } from "@/lib/transformStep";

interface TransformStepOutcomeProps {
  /** The execution's note: `step_type` and `transform_result` are read from it. */
  note: unknown;
  /** The execution's status; an unfinished or failed step may have no recorded outcome. */
  status?: string | null;
  className?: string;
}

function noteString(note: unknown, key: string): string | null {
  if (!note || typeof note !== "object") return null;
  const value = (note as Record<string, unknown>)[key];
  return typeof value === "string" && value ? value : null;
}

/**
 * What a transform step (a filter or a CR schedule) decided, as its execution recorded it. The
 * step runs no task and no hardware, so it has no task list, figures or parameter changes: its
 * record is the result. A failed or unfinished step without a record says so instead of showing
 * an empty result.
 */
export function TransformStepOutcome({ note, status, className = "" }: TransformStepOutcomeProps) {
  const record = transformRecordOf(note);
  const stepType = noteString(note, "step_type") ?? noteString(note, "step_name") ?? "Transform";

  if (!record) {
    const reason =
      status === "running" || status === "scheduled"
        ? "The step is still running."
        : status === "completed"
          ? "No outcome was recorded for this step."
          : "The step ended before recording an outcome.";
    return (
      <section className={className} aria-label="Step outcome">
        <p className="text-sm text-base-content/60">
          <span className="font-medium text-base-content">{stepType}</span> selects or plans without
          running tasks. {reason}
        </p>
      </section>
    );
  }

  const excluded = record.excluded ?? [];
  const groups = record.groups ?? [];
  return (
    <section className={`space-y-3 text-sm ${className}`} aria-label="Step outcome">
      <div className="flex flex-wrap items-center gap-2">
        <span className="badge badge-ghost badge-sm">{stepType}</span>
        <span className="font-medium">{transformSummary(record)}</span>
      </div>
      <p className="text-xs text-base-content/60">
        This step selects or plans without running tasks or hardware; this is its recorded result.
      </p>
      {record.criteria && (
        <p className="text-base-content/70">
          <span className="text-base-content/50">Criteria: </span>
          <code className="text-xs">{record.criteria}</code>
        </p>
      )}
      {record.kind !== "cr_schedule" && (record.output_qids ?? []).length > 0 && (
        <p className="break-words text-base-content/70">
          <span className="text-base-content/50">Kept: </span>
          {(record.output_qids ?? []).join(", ")}
        </p>
      )}
      {excluded.length > 0 && (
        <div className="overflow-x-auto">
          <table className="table table-xs">
            <caption className="text-left text-xs text-base-content/50">
              Excluded ({excluded.length})
            </caption>
            <thead>
              <tr>
                <th>Qubit</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {excluded.map((entry) => (
                <tr key={entry.target}>
                  <td className="font-mono">{entry.target}</td>
                  <td>{entry.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {record.kind === "cr_schedule" && groups.length > 0 && (
        <ol className="space-y-1" aria-label="CR groups">
          {groups.map((group, index) => (
            <li key={index} className="break-words text-base-content/70">
              <span className="text-base-content/50">Group {index + 1}: </span>
              <span className="font-mono text-xs">{group.join(", ")}</span>
            </li>
          ))}
        </ol>
      )}
      {record.kind === "cr_schedule" && record.direction && (
        <p className="text-xs text-base-content/50">
          Direction: {record.direction}
          {record.max_parallel_ops != null ? ` · at most ${record.max_parallel_ops} per group` : ""}
        </p>
      )}
    </section>
  );
}
