"use client";

import { useEffect, useId, useState } from "react";

import { Pause, Play } from "lucide-react";

import type { FlowExecutionPlanState } from "@/hooks/useFlowExecutionPlan";
import type {
  ExecutionPlanIssue,
  ExecutionPlanRound,
  ExecutionPlanRunTargets,
  ExecutionPlanStep,
  FlowExecutionPlanResponse,
} from "@/schemas";

import {
  HelpAnimation,
  ONE_QUBIT_MEDIA,
  TWO_QUBIT_MEDIA,
} from "@/components/features/flow/WorkflowExecutionHelpDialog";

const ROUND_STEP_MS = 1200;

const SCHEDULE_LABEL: Record<ExecutionPlanStep["schedule"], string | null> = {
  manual: "Manual rounds · user-defined",
  automatic: "Automatic · formed at run time",
  none: null,
};

const SCHEDULE_BADGE: Record<ExecutionPlanStep["schedule"], string> = {
  manual: "badge-primary",
  automatic: "badge-ghost",
  none: "badge-ghost",
};

function formatTargets(targets: ExecutionPlanRunTargets | undefined): string {
  if (!targets) return "Computed at run time; the source does not state them literally.";
  if (targets.coupling_pairs) {
    return `Coupling pairs ${targets.coupling_pairs.map((pair) => pair.join("-")).join(", ")}`;
  }
  if (targets.qids) return `Qubits ${targets.qids.join(", ")}`;
  const excluded = targets.exclude_qids?.length
    ? ` (excluding ${targets.exclude_qids.join(", ")})`
    : "";
  return `MUX ${(targets.mux_ids ?? []).join(", ")}${excluded}`;
}

function formatIssue(issue: ExecutionPlanIssue): string {
  if (issue.round == null) return issue.message;
  const targets = issue.targets?.length ? ` (${issue.targets.join(", ")})` : "";
  return `Round ${issue.round}${targets}: ${issue.message}`;
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const update = () => setReduced(query.matches);
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  return reduced;
}

/**
 * The rounds of one step as written in the source. "Play round order" highlights the rounds
 * one after another; it shows order only, never durations, and starts only on request.
 */
function RoundTable({
  rounds,
  scope,
  caption,
}: {
  rounds: ExecutionPlanRound[];
  scope: ExecutionPlanStep["scope"];
  caption: string;
}) {
  const [active, setActive] = useState<number | null>(null);
  const reducedMotion = usePrefersReducedMotion();
  const playing = active !== null;

  useEffect(() => {
    if (active === null) return;
    const timer = window.setTimeout(
      () => setActive(active + 1 < rounds.length ? active + 1 : null),
      ROUND_STEP_MS,
    );
    return () => window.clearTimeout(timer);
  }, [active, rounds.length]);

  const targetHeader =
    scope === "coupling" ? "Pairs (control-target), in parallel" : "Qubits, in parallel";
  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto rounded-lg border border-base-300">
        <table className="table table-sm">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              <th scope="col" className="w-20">
                Round
              </th>
              <th scope="col">{targetHeader}</th>
            </tr>
          </thead>
          <tbody>
            {rounds.map((round, index) => (
              <tr
                key={round.number}
                aria-current={active === index ? "step" : undefined}
                className={
                  active === index
                    ? "bg-primary/15 motion-safe:transition-colors"
                    : "motion-safe:transition-colors"
                }
              >
                <td>{round.number}</td>
                <td className="font-mono">{round.targets.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rounds.length > 1 && (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn btn-xs"
            onClick={() => setActive(playing ? null : 0)}
            aria-pressed={playing}
          >
            {playing ? (
              <Pause size={14} aria-hidden="true" />
            ) : (
              <Play size={14} aria-hidden="true" />
            )}
            {playing ? "Stop round order" : "Play round order"}
          </button>
          <span className="text-xs text-base-content/60" aria-live="polite">
            {playing
              ? `Round ${rounds[active ?? 0].number} of ${rounds.length}; the next round waits for all of it.`
              : reducedMotion
                ? "Highlights each round in turn without animation; order only, not timing."
                : "Highlights each round in turn; order only, not timing."}
          </span>
        </div>
      )}
    </div>
  );
}

function StepCard({ step }: { step: ExecutionPlanStep }) {
  const scheduleLabel = SCHEDULE_LABEL[step.schedule];
  const issues = step.issues ?? [];
  const unchecked = step.unchecked ?? [];
  const rounds = step.rounds ?? [];
  return (
    <li className="flex flex-col gap-2 rounded-lg border border-base-300 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">
          {step.index}. {step.name}
        </span>
        <span className="badge badge-sm badge-outline font-mono">{step.type}</span>
        {step.execution_mode && (
          <span className="badge badge-sm badge-ghost font-mono">{step.execution_mode}</span>
        )}
        {scheduleLabel && (
          <span className={`badge badge-sm ${SCHEDULE_BADGE[step.schedule]}`}>{scheduleLabel}</span>
        )}
      </div>
      {step.scope !== "none" && (
        <p className="text-sm">
          <span className="text-base-content/60">
            Tasks per {step.scope === "coupling" ? "pair" : "qubit"}:{" "}
          </span>
          {step.tasks ? (
            <span className="font-mono">{step.tasks.join(" → ") || "none"}</span>
          ) : (
            <span className="text-base-content/70">set at run time</span>
          )}
        </p>
      )}
      <p className="text-sm text-base-content/70">{step.summary}</p>
      {rounds.length > 0 && (
        <RoundTable
          rounds={rounds}
          scope={step.scope}
          caption={`Rounds of step ${step.name}, in run order`}
        />
      )}
      {issues.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm text-error">
          {issues.map((issue, index) => (
            <li key={index}>{formatIssue(issue)}</li>
          ))}
        </ul>
      )}
      {unchecked.length > 0 && (
        <p className="text-xs text-base-content/60">
          Checked when the run starts instead: {unchecked.join("; ")}.
        </p>
      )}
    </li>
  );
}

function PlanStatus({ plan }: { plan: FlowExecutionPlanResponse }) {
  if (plan.status === "invalid") {
    return (
      <div className="alert alert-error" role="alert">
        <span>
          Manual rounds in the saved workflow cannot run. Fix the problems below in the source and
          save; execution stays disabled until then.
        </span>
      </div>
    );
  }
  if (plan.status === "unresolved") {
    return (
      <div className="alert alert-warning" role="status">
        <span>
          Cannot resolve the steps before execution: {plan.reason}. The workflow decides its steps
          when it runs, so no plan is shown. QDash still checks manual rounds before any target is
          measured.
        </span>
      </div>
    );
  }
  return (
    <p className="text-sm text-base-content/70">
      These are the planned steps from the saved source, assuming runtime checks pass. A failed
      check can stop execution. Manual rounds preserve the specified targets and order; automatic
      groups are formed by the scheduler when the run starts.
    </p>
  );
}

function Illustrations({ plan }: { plan: FlowExecutionPlanResponse }) {
  const steps = (plan.runs ?? []).flatMap((run) => run.steps);
  const qubit = steps.some((step) => step.scope === "qubit" && step.schedule !== "none");
  const coupling = steps.some((step) => step.scope === "coupling" && step.schedule !== "none");
  if (!qubit && !coupling) return null;
  return (
    <details className="rounded-lg border border-base-300 p-3">
      <summary className="cursor-pointer text-sm font-medium">
        Illustration: how rounds wait for each other
      </summary>
      <div className="mt-3 flex flex-col gap-4">
        <p className="text-xs text-base-content/70">
          Illustrative example — not this run. The sample qubits, pairs, tasks, durations and worker
          lanes differ from this workflow; the run order above is what this workflow states.
        </p>
        {qubit && (
          <HelpAnimation
            media={ONE_QUBIT_MEDIA}
            caption="Illustrative example — not this run. Manual rounds wait like parallel_by_round."
          />
        )}
        {coupling && (
          <HelpAnimation
            media={TWO_QUBIT_MEDIA}
            caption="Illustrative example — not this run. Manual pair rounds wait like these groups; max_parallel_ops does not apply to them."
          />
        )}
      </div>
    </details>
  );
}

interface FlowExecutionPreviewProps {
  state: FlowExecutionPlanState | undefined;
  hasUnsavedChanges?: boolean;
}

/** Read-only preview of what the saved source states about its execution. */
export function FlowExecutionPreview({ state, hasUnsavedChanges }: FlowExecutionPreviewProps) {
  const headingId = useId();
  return (
    <section className="flex flex-col gap-4" aria-labelledby={headingId}>
      <h3 id={headingId} className="sr-only">
        Execution preview
      </h3>
      <p className="text-xs text-base-content/60">
        Preview of the saved workflow source, read without running it. A run always executes the
        saved version.
      </p>
      {hasUnsavedChanges && (
        <div className="alert alert-warning" role="status">
          <span>
            The editor has unsaved changes. They are not part of this preview or this run; save them
            first to run them.
          </span>
        </div>
      )}
      {!state || state.status === "error" ? (
        <div className="alert alert-info" role="status">
          <span>
            Execution preview unavailable
            {state?.status === "error" ? `: ${state.message}` : "."} You can still run the flow;
            QDash checks manual rounds again before any target is measured.
          </span>
        </div>
      ) : state.status === "loading" ? (
        <p role="status" className="flex items-center gap-2 text-sm">
          <span className="loading loading-spinner loading-sm" aria-hidden="true" />
          Reading the saved workflow…
        </p>
      ) : state.status === "stale" ? (
        <div className="alert alert-warning" role="status">
          <span>
            The saved workflow changed after this page loaded. Reload the flow to preview the
            version that will run.
          </span>
        </div>
      ) : (
        <PlanBody plan={state.plan} />
      )}
    </section>
  );
}

function PlanBody({ plan }: { plan: FlowExecutionPlanResponse }) {
  const runs = plan.runs ?? [];
  const issues = plan.issues ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PlanStatus plan={plan} />
      {issues.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm text-error">
          {issues.map((issue, index) => (
            <li key={index}>{formatIssue(issue)}</li>
          ))}
        </ul>
      )}
      {runs.map((run, runIndex) => (
        <div key={runIndex} className="flex flex-col gap-2">
          {runs.length > 1 && (
            <h4 className="text-sm font-medium">CalibService.run {runIndex + 1}</h4>
          )}
          <p className="text-sm">
            <span className="text-base-content/60">Targets: </span>
            {formatTargets(run.targets)}
          </p>
          <ol className="flex flex-col gap-2">
            {run.steps.map((step) => (
              <StepCard key={`${runIndex}-${step.index}`} step={step} />
            ))}
          </ol>
        </div>
      ))}
      {runs.length > 0 && (
        <p className="text-xs text-base-content/60">
          A round lists which targets run in parallel and in what order; it does not promise
          simultaneous measurements or any timing. Each parallel executor has 16 worker slots;
          available resources and deployment settings can reduce actual concurrency. Targets wait
          for a free slot, and the next round waits for the current round to finish.
        </p>
      )}
      <Illustrations plan={plan} />
    </div>
  );
}
