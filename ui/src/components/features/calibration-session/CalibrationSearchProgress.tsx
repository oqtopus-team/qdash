"use client";

import type { ReactNode } from "react";

import type {
  CalibrationDecisionResponse,
  CalibrationExperimentRow,
  CalibrationLatestRequestedRun,
  CalibrationMeasuredValue,
} from "@/schemas";

import { getStatusBadgeClass } from "@/components/features/execution/ExecutionListCard";
import { QubitTile } from "@/components/ui/QubitTile";
import { formatDateTime } from "@/lib/utils/datetime";

const STAGE_LABELS: Record<string, string> = {
  baseline: "Baseline",
  screening: "Screening",
  confirmation: "Confirmation",
};

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
  recommend_candidate: "Recommend candidate",
  keep_baseline: "Keep baseline",
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

/** The recorded execution outcome of a run, with the badge color of its execution status. */
const RUN_OUTCOMES: Record<string, { label: string; badge: string }> = {
  refused: { label: "Refused, never ran", badge: "badge-warning" },
  unknown: { label: "Launch outcome unknown", badge: "badge-warning" },
  no_execution: { label: "No execution recorded", badge: "badge-ghost" },
  running: { label: "Running", badge: getStatusBadgeClass("running") },
  failed: { label: "Failed", badge: getStatusBadgeClass("failed") },
  partial: { label: "Partly completed", badge: "badge-warning" },
  completed: { label: "Completed", badge: getStatusBadgeClass("completed") },
};

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-base-content/60">{label}</dt>
      <dd className="mt-0.5 text-sm">{children}</dd>
    </div>
  );
}

function ConclusionPanel({ recommendation }: { recommendation: CalibrationDecisionResponse }) {
  const conclusion = recommendation.conclusion;
  if (!conclusion) return null;
  return (
    <div
      role="group"
      aria-labelledby="conclusion-heading"
      className="flex flex-col gap-2 rounded-box border border-base-300 p-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 id="conclusion-heading" className="text-sm font-medium">
          Conclusion
        </h3>
        <span className="badge badge-ghost badge-sm">
          {recommendation.model ? "Agent statement" : "Client statement"}
        </span>
      </div>
      <dl className="grid gap-2 sm:grid-cols-3">
        <Meta label="Outcome">{OUTCOME_LABELS[conclusion.outcome] ?? conclusion.outcome}</Meta>
        <Meta label="Recommended candidate">
          {conclusion.recommended_candidate_id ?? "No candidate"}
        </Meta>
        <Meta label="Recorded">
          {recommendation.recorded_by} · {formatDateTime(recommendation.recorded_at)}
        </Meta>
      </dl>
      {recommendation.interpretation ? (
        <div>
          <div className="text-xs text-base-content/60">Interpretation</div>
          <p className="mt-0.5 text-sm whitespace-pre-wrap wrap-anywhere">
            {recommendation.interpretation}
          </p>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The latest requested run as labeled facts. Latest is request order, not finish order, and
 * QDash records no hardware write, so nothing here states what is on the hardware.
 */
function LatestRequestedRunPanel({
  latestRun,
  recommendation,
}: {
  latestRun: CalibrationLatestRequestedRun;
  recommendation: CalibrationDecisionResponse | null | undefined;
}) {
  const outcome = RUN_OUTCOMES[latestRun.execution_outcome] ?? {
    label: latestRun.execution_outcome,
    badge: "badge-ghost",
  };
  const recommended = recommendation?.conclusion?.recommended_candidate_id;
  return (
    <div
      role="group"
      aria-labelledby="latest-run-heading"
      className="flex flex-col gap-2 rounded-box border border-base-300 p-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 id="latest-run-heading" className="text-sm font-medium">
          Latest requested run
        </h3>
        <span className={`badge badge-sm ${outcome.badge}`}>{outcome.label}</span>
      </div>
      <dl className="grid gap-2 sm:grid-cols-3">
        <Meta label="Candidate">
          {latestRun.candidate_id ?? "No candidate"}
          {latestRun.candidate_is_recommended === false ? (
            <span className="block text-xs text-warning">
              {recommended
                ? `Not the recommended candidate ${recommended}`
                : "Not the recommended candidate"}
            </span>
          ) : null}
        </Meta>
        <Meta label="Requested">{formatDateTime(latestRun.requested_at)}</Meta>
        <Meta label="Finished">
          {latestRun.finished_at
            ? formatDateTime(latestRun.finished_at)
            : latestRun.execution_outcome === "running"
              ? "Not finished"
              : latestRun.execution_outcome === "unknown"
                ? "Unknown"
                : "—"}
        </Meta>
      </dl>
      <p className="text-xs text-base-content/60">Hardware state is not tracked</p>
    </div>
  );
}

/**
 * The experiments a calibration session's decisions record: the recorded conclusion, the latest
 * requested run with its recorded execution outcome (never a hardware state), and each
 * experiment's candidate, requested change, rationale, and measured values. Measured values
 * come from task results; rationales and the interpretation are the recorder's statements.
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
  return (
    <section className="card card-border bg-base-100" aria-labelledby="experiments-heading">
      <div className="card-body gap-3 p-4">
        <h2 id="experiments-heading" className="text-sm font-medium">
          Experiments
        </h2>
        {recommendation?.conclusion || latestRun ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {recommendation?.conclusion ? (
              <ConclusionPanel recommendation={recommendation} />
            ) : null}
            {latestRun ? (
              <LatestRequestedRunPanel latestRun={latestRun} recommendation={recommendation} />
            ) : null}
          </div>
        ) : null}
        {!recommendation?.conclusion && experiments.length > 0 ? (
          <p className="text-xs text-base-content/60">No conclusion recorded</p>
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
                  <th>Rationale</th>
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
                      <td>{STAGE_LABELS[row.stage] ?? row.stage}</td>
                      <td>
                        <span className="block font-medium">{row.candidate_id}</span>
                        {row.target ? <QubitTile qid={row.target} className="mt-1" /> : null}
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
                      </td>
                      <td className="max-w-56">
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
