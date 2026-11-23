"use client";

import type {
  CalibrationDecisionResponse,
  CalibrationExperimentRow,
  CalibrationLatestRequestedRun,
  CalibrationMeasuredValue,
} from "@/schemas";

import { getStatusBadgeClass } from "@/components/features/execution/ExecutionListCard";
import { formatDateTime } from "@/lib/utils/datetime";

const STAGES = [
  { stage: "baseline", label: "Baseline" },
  { stage: "screening", label: "Screening" },
  { stage: "confirmation", label: "Confirmation" },
] as const;

const EVIDENCE_LABELS: Record<string, string> = {
  complete: "All tasks completed",
  partial: "Partly completed",
  running: "Running",
  failed: "Failed",
  unavailable: "No task result found",
  not_run: "No run carried it out",
};

const EVIDENCE_BADGES: Record<string, string> = {
  complete: "badge-success",
  partial: "badge-warning",
  running: "badge-info",
  failed: "badge-error",
  unavailable: "badge-ghost",
  not_run: "badge-ghost",
};

const OUTCOME_LABELS: Record<string, string> = {
  recommend_candidate: "Recommends a new candidate",
  keep_baseline: "Keeps the baseline",
  inconclusive: "Inconclusive",
};

/** A measured value with its error and unit, or a dash when the task results hold none. */
function measuredText(value: CalibrationMeasuredValue | null | undefined): string {
  if (!value) return "—";
  const digits = Math.abs(value.value) < 1 ? 4 : 1;
  const error = value.error ? ` ± ${value.error.toPrecision(2)}` : "";
  return `${value.value.toFixed(digits)}${error}${value.unit ? ` ${value.unit}` : ""}`;
}

function seconds(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value < 120) return `${Math.round(value)} s`;
  return `${(value / 60).toFixed(1)} min`;
}

function changesText(row: CalibrationExperimentRow): string {
  const changes = row.requested_changes ?? [];
  if (changes.length === 0) return "No change";
  return changes
    .map(
      (change) =>
        `${change.parameter} ${change.previous != null ? `${String(change.previous)} → ` : ""}${String(change.value)}`,
    )
    .join(", ");
}

const RUN_OUTCOME_TEXT: Record<string, string> = {
  refused: "QDash refused its launch, so it never ran",
  unknown: "has a launch outcome QDash does not know yet",
  no_execution: "was launched, and QDash holds no execution record for it",
  running: "is still running",
  failed: "failed: no execution completed",
  partial: "partly completed: some executions failed or were cancelled",
  completed: "completed every execution",
};

function LatestRequestedRunNotice({
  latestRun,
  recommendation,
}: {
  latestRun: CalibrationLatestRequestedRun;
  recommendation: CalibrationDecisionResponse | null | undefined;
}) {
  const candidate = latestRun.candidate_id
    ? `candidate ${latestRun.candidate_id}`
    : "names no decision";
  const outcome = RUN_OUTCOME_TEXT[latestRun.execution_outcome] ?? latestRun.execution_outcome;
  const recommended = recommendation?.conclusion?.recommended_candidate_id;
  const differs = latestRun.candidate_is_recommended === false;
  return (
    <div
      role="status"
      className={`alert alert-soft ${differs || latestRun.execution_outcome !== "completed" ? "alert-warning" : "alert-info"}`}
    >
      <span>
        The latest requested run ({candidate}, requested {formatDateTime(latestRun.requested_at)}){" "}
        {outcome}
        {latestRun.finished_at ? ` at ${formatDateTime(latestRun.finished_at)}` : ""}.
        {differs && recommended
          ? ` Its requested candidate is not the recommended candidate ${recommended}.`
          : ""}
        {latestRun.candidate_is_recommended === true
          ? " Its requested candidate is the recommended candidate."
          : ""}{" "}
        QDash records no authoritative hardware write, and a run requested earlier can finish later,
        so this does not show which state is on the hardware.
      </span>
    </div>
  );
}

/**
 * The search a calibration session's audit records: the stages it reached, each experiment's
 * candidate, requested change, and measured values, the recorded conclusion, and the latest
 * requested run with its recorded execution outcome (never a hardware state). Measured values
 * come from task results; rationales are statements.
 */
export function CalibrationSearchProgress({
  experiments,
  recommendation,
  latestRun,
  executionHref,
}: {
  experiments: CalibrationExperimentRow[];
  recommendation: CalibrationDecisionResponse | null | undefined;
  latestRun: CalibrationLatestRequestedRun | null | undefined;
  executionHref: (executionId: string) => string;
}) {
  if (experiments.length === 0 && !recommendation && !latestRun) return null;
  const reached = new Set(experiments.map((row) => row.stage));
  return (
    <section className="card card-border bg-base-100" aria-labelledby="search-heading">
      <div className="card-body gap-3 p-4">
        <div>
          <h2 id="search-heading" className="text-sm font-medium">
            Search progression
          </h2>
          <p className="text-xs text-base-content/60">
            Experiments recorded as decisions before their runs. Measured values are QDash task
            results; rationales are the recorder&apos;s statements.
          </p>
        </div>
        <ul className="steps steps-horizontal w-full text-xs" aria-label="Stages reached">
          {STAGES.map(({ stage, label }) => {
            const count = experiments.filter((row) => row.stage === stage).length;
            return (
              <li
                key={stage}
                className={`step ${reached.has(stage) ? "step-primary" : ""}`}
                data-content={count > 0 ? String(count) : "·"}
              >
                {label}
              </li>
            );
          })}
        </ul>
        {recommendation?.conclusion ? (
          <div className="rounded-box border border-base-300 p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">
                {OUTCOME_LABELS[recommendation.conclusion.outcome] ??
                  recommendation.conclusion.outcome}
              </span>
              {recommendation.conclusion.recommended_candidate_id ? (
                <span className="badge badge-outline badge-sm">
                  {recommendation.conclusion.recommended_candidate_id}
                </span>
              ) : null}
              <span className="badge badge-ghost badge-sm">
                {recommendation.model ? "Agent statement" : "Client statement"}
              </span>
              <span className="text-xs text-base-content/60">
                {recommendation.recorded_by} · {formatDateTime(recommendation.recorded_at)}
              </span>
            </div>
            <p className="mt-1 text-xs whitespace-pre-wrap text-base-content/80">
              {recommendation.interpretation}
            </p>
          </div>
        ) : experiments.length > 0 ? (
          <p className="text-xs text-base-content/60">
            No conclusion recorded. Closing the session does not record one.
          </p>
        ) : null}
        {latestRun ? (
          <LatestRequestedRunNotice latestRun={latestRun} recommendation={recommendation} />
        ) : null}
        {experiments.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="table table-sm" aria-label="Candidate comparison">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Stage</th>
                  <th>Candidate</th>
                  <th>Requested change</th>
                  <th>Gate time</th>
                  <th>Fidelity</th>
                  <th>CR duration</th>
                  <th>Hardware time</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {experiments.map((row) => {
                  const measured = row.measured;
                  const mismatched = (row.parameter_checks ?? []).filter(
                    (check) => check.consistent === false,
                  );
                  const firstExecution = measured.execution_ids?.[0];
                  return (
                    <tr key={`${row.decision_id}:${row.pipeline_run_id ?? "none"}`}>
                      <td className="font-mono text-xs">{row.sequence}</td>
                      <td>{row.stage}</td>
                      <td>
                        <span className="font-medium">{row.candidate_id}</span>
                        <span className="block text-xs text-base-content/60">{row.target}</span>
                      </td>
                      <td className="max-w-56">
                        <span className="text-xs">{changesText(row)}</span>
                        {mismatched.length > 0 ? (
                          <span className="block text-xs text-warning">
                            Executed{" "}
                            {mismatched
                              .map((check) => `${check.parameter} ${String(check.executed ?? "?")}`)
                              .join(", ")}
                          </span>
                        ) : null}
                        <span
                          className="block truncate text-xs text-base-content/60"
                          title={row.rationale}
                        >
                          {row.rationale}
                        </span>
                      </td>
                      <td className="text-xs">{measuredText(measured.gate_time_ns)}</td>
                      <td className="text-xs">{measuredText(measured.gate_fidelity)}</td>
                      <td className="text-xs">{measuredText(measured.cr_duration_ns)}</td>
                      <td className="text-xs">{seconds(measured.execution_seconds)}</td>
                      <td>
                        <span
                          className={`badge badge-soft badge-sm ${EVIDENCE_BADGES[measured.evidence_status] ?? "badge-ghost"}`}
                        >
                          {EVIDENCE_LABELS[measured.evidence_status] ?? measured.evidence_status}
                        </span>
                        {firstExecution ? (
                          <a
                            href={executionHref(firstExecution)}
                            className="link link-hover block text-xs"
                          >
                            Execution
                          </a>
                        ) : null}
                        {measured.pipeline_dispatch_status &&
                        measured.pipeline_dispatch_status !== "dispatched" ? (
                          <span
                            className={`badge badge-soft badge-xs ${getStatusBadgeClass(measured.pipeline_dispatch_status)}`}
                          >
                            {measured.pipeline_dispatch_status}
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </section>
  );
}
