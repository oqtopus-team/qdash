"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { validateCalibrationPipeline } from "@/client/calibration-pipeline/calibration-pipeline";
import type { ResolvedPipelineStep } from "@/schemas";
import type { PipelinePlanApprovalPreview } from "@/types/agentChat";

/** A step's task call as written in a spec; QDash fills in a missing call_id. */
interface SpecTaskCall {
  name?: unknown;
  call_id?: unknown;
  [key: string]: unknown;
}

/** The parts of a CalibrationPipelineSpec the card reads before validation answers. */
export interface PipelineSpecLike {
  name?: string;
  targets?: { qids?: string[]; mux_ids?: number[]; exclude_qids?: string[] };
  steps: Array<{
    type: string;
    step_name?: string;
    step_id?: string;
    tasks?: Array<SpecTaskCall | string>;
    [key: string]: unknown;
  }>;
  [key: string]: unknown;
}

/** One chip: the task name, and the call id when it differs from the name. */
interface CallChip {
  name: string;
  callId: string;
}

/** True for an approval argument that is a pipeline spec (a `steps` list of typed steps). */
export function isPipelineSpec(value: unknown): value is PipelineSpecLike {
  if (!value || typeof value !== "object") return false;
  const steps = (value as { steps?: unknown }).steps;
  return (
    Array.isArray(steps) &&
    steps.length > 0 &&
    steps.every(
      (s) => s && typeof s === "object" && typeof (s as { type?: unknown }).type === "string",
    )
  );
}

const TASK_PREVIEW_LIMIT = 8;

function describeTargets(targets: PipelineSpecLike["targets"]): string {
  if (!targets) return "No targets";
  if (targets.qids?.length) return `Qubits ${targets.qids.join(", ")}`;
  if (targets.mux_ids?.length) {
    const base = `MUX ${targets.mux_ids.join(", ")}`;
    return targets.exclude_qids?.length
      ? `${base} (excluding ${targets.exclude_qids.join(", ")})`
      : base;
  }
  return "No targets";
}

function specCall(task: SpecTaskCall | string): CallChip {
  // A version 1 spec lists names; QDash rejects it, but show what was written.
  if (typeof task === "string") return { name: task, callId: task };
  const name = typeof task.name === "string" ? task.name : "?";
  return { name, callId: typeof task.call_id === "string" ? task.call_id : name };
}

/** Steps as the spec describes them, before the server fills in default task lists. */
function stepsFromSpec(
  spec: PipelineSpecLike,
): Array<ResolvedPipelineStep & { chips: CallChip[] }> {
  return spec.steps.map((step, i) => {
    const chips = (step.tasks ?? []).map(specCall);
    return {
      index: i + 1,
      type: step.type,
      name: step.step_name ?? step.step_id ?? step.type,
      kind:
        step.type.startsWith("Filter") || step.type === "GenerateCRSchedule"
          ? "transform"
          : "calibration",
      tasks: chips.map((chip) => chip.name),
      chips,
    };
  });
}

/** The step (and call) a filter reads, when the spec names one. */
function referenceLabel(step: ResolvedPipelineStep): string | null {
  const reference = step.reference as { step?: unknown; call_id?: unknown } | null | undefined;
  if (!reference || typeof reference.step !== "string") return null;
  return typeof reference.call_id === "string"
    ? `${reference.step}.${reference.call_id}`
    : reference.step;
}

function resolvedChips(step: ResolvedPipelineStep): CallChip[] {
  if (step.calls?.length) {
    return step.calls.map((call) => ({ name: call.name, callId: call.call_id }));
  }
  return step.tasks.map((name) => ({ name, callId: name }));
}

function TaskChips({ calls }: { calls: CallChip[] }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? calls : calls.slice(0, TASK_PREVIEW_LIMIT);
  const hidden = calls.length - shown.length;
  return (
    <span className="flex flex-wrap gap-1">
      {shown.map((call) => (
        <span
          key={call.callId}
          className="chat-pipeline-task"
          title={call.callId === call.name ? undefined : `call ${call.callId}`}
        >
          {call.name}
          {call.callId !== call.name && (
            <span className="text-base-content/50"> · {call.callId}</span>
          )}
        </span>
      ))}
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="chat-pipeline-task chat-pipeline-task-more"
        >
          +{hidden} more
        </button>
      )}
    </span>
  );
}

/**
 * What a `qdash_run_pipeline` approval will run: targets, steps, and tasks.
 *
 * Asks the API to validate the spec so the card shows the task lists the
 * worker will actually use (defaults filled in) and any problems before the
 * user approves. Until the answer arrives, or if the call fails, it shows the
 * spec as written.
 */
export function PipelinePreview({
  chipId,
  spec,
}: {
  chipId: string | null;
  spec: PipelineSpecLike;
}) {
  const [open, setOpen] = useState(true);
  const specKey = JSON.stringify(spec);
  const validation = useQuery({
    queryKey: ["calibration-pipeline-validate", chipId, specKey],
    queryFn: () => validateCalibrationPipeline({ chip_id: chipId as string, spec }),
    enabled: Boolean(chipId),
    staleTime: Infinity,
    retry: false,
  });
  const result = validation.data?.data;
  const steps = result?.steps?.length
    ? result.steps.map((step) => ({ ...step, chips: resolvedChips(step) }))
    : stepsFromSpec(spec);
  const problems = result?.problems ?? [];
  const warnings = result?.warnings ?? [];
  const taskRuns = result?.task_run_count ?? steps.reduce((n, s) => n + s.chips.length, 0);

  let status: React.ReactNode;
  if (!chipId) {
    status = <span className="text-base-content/50">No chip given; not checked</span>;
  } else if (validation.isPending) {
    status = (
      <span className="inline-flex items-center gap-1 text-base-content/60">
        <Loader2 className="w-3 h-3 animate-spin" /> Checking…
      </span>
    );
  } else if (validation.isError) {
    status = <span className="text-base-content/50">Could not check with QDash</span>;
  } else if (result?.valid) {
    status = (
      <span className="inline-flex items-center gap-1 text-success">
        <CheckCircle2 className="w-3.5 h-3.5" /> Ready · {taskRuns} task calls per target
      </span>
    );
  } else {
    status = (
      <span className="inline-flex items-center gap-1 text-error">
        <AlertTriangle className="w-3.5 h-3.5" /> {problems.length} problem
        {problems.length === 1 ? "" : "s"}
      </span>
    );
  }

  return (
    <div className="chat-pipeline-preview" data-testid="pipeline-preview">
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="font-medium truncate">
          {spec.name ? `Pipeline · ${spec.name}` : "Pipeline"}
          <span className="text-base-content/50 font-normal">
            {" "}
            · {describeTargets(spec.targets)}
          </span>
        </span>
        <span className="shrink-0">{status}</span>
      </div>

      {problems.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs text-error">
          {problems.map((p) => (
            <li key={`${p.path}:${p.message}`}>
              <span className="font-mono">{p.path}</span>: {p.message}
            </li>
          ))}
        </ul>
      )}
      {result?.migrated_spec && (
        <p className="mt-1 text-xs text-base-content/60">
          This spec uses the version 1 format; QDash returned a converted version 2 spec to submit
          instead.
        </p>
      )}
      {warnings.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs text-warning" aria-label="Warnings">
          {warnings.map((w) => (
            <li key={`${w.path}:${w.message}`}>
              <span className="font-mono">{w.path}</span>: {w.message}
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="mt-2 inline-flex items-center gap-1 text-xs text-base-content/55 hover:text-base-content"
        aria-expanded={open}
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        {steps.length} step{steps.length === 1 ? "" : "s"}
      </button>
      {open && (
        <ol className="mt-1.5 space-y-1.5">
          {steps.map((step) => (
            <li key={step.index} className="flex gap-2 text-xs">
              <span className="chat-option-key shrink-0">{step.index}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-1.5">
                  <span className="font-medium">{step.name}</span>
                  {step.name !== step.type && (
                    <span className="text-base-content/45">{step.type}</span>
                  )}
                  {step.kind === "transform" && (
                    <span className="text-base-content/45">
                      · {step.type === "GenerateCRSchedule" ? "schedule" : "filter"}
                      {referenceLabel(step) && <> · reads {referenceLabel(step)}</>}
                    </span>
                  )}
                </div>
                {step.chips.length > 0 ? (
                  <div className="mt-1">
                    <TaskChips calls={step.chips} />
                  </div>
                ) : (
                  step.kind === "calibration" &&
                  !result && <div className="mt-0.5 text-base-content/45">default task list</div>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** True for an approval preview of a stored pipeline plan, as the agent runtime freezes it. */
export function isPlanApprovalPreview(value: unknown): value is PipelinePlanApprovalPreview {
  if (!value || typeof value !== "object") return false;
  const preview = value as Partial<PipelinePlanApprovalPreview>;
  return (
    preview.kind === "calibration_pipeline_plan" &&
    typeof preview.planId === "string" &&
    typeof preview.reviewDigest === "string" &&
    Array.isArray(preview.targetQids) &&
    Boolean(preview.plan) &&
    typeof preview.plan === "object"
  );
}

interface StoredPlanFields {
  spec?: { name?: unknown; steps?: unknown };
  steps?: ResolvedPipelineStep[];
  warnings?: Array<{ path: string; message: string }>;
  task_run_count?: number;
  default_run_parameters?: Record<string, unknown>;
}

/** A call's effective settings, compactly, or null when it has none of its own. */
function settingsText(settings: unknown): string | null {
  if (!settings || typeof settings !== "object") return null;
  const entries = Object.entries(settings as Record<string, unknown>).filter(
    ([, value]) =>
      value !== null &&
      value !== undefined &&
      !(typeof value === "object" && Object.keys(value as object).length === 0),
  );
  return entries.length ? JSON.stringify(Object.fromEntries(entries)) : null;
}

/**
 * A spec step's own settings: every field the normalized spec gives it besides its type and
 * its task list (shown as resolved calls), such as `execution_mode` with manual `rounds`, or a
 * filter's `metric`, `threshold` and `inverse`. The review digest binds them all.
 */
function stepSpecSettings(spec: unknown, index: number): Record<string, unknown> {
  const steps = spec && typeof spec === "object" ? (spec as { steps?: unknown }).steps : undefined;
  const step = Array.isArray(steps) ? steps[index - 1] : undefined;
  if (!step || typeof step !== "object" || Array.isArray(step)) return {};
  const { type: _type, tasks: _tasks, ...settings } = step as Record<string, unknown>;
  return settings;
}

/**
 * What a `qdash_run_pipeline` approval of a stored plan runs: the plan exactly as the
 * runtime fetched it before asking, with its review digest, the qubits it starts from
 * (MUXes expanded), every step's calls and settings, and the warnings. It is a record of
 * what was shown, so it never asks QDash again and stays the same after the plan expires.
 */
export function StoredPlanPreview({ preview }: { preview: PipelinePlanApprovalPreview }) {
  const [open, setOpen] = useState(true);
  const plan = preview.plan as StoredPlanFields;
  const name = typeof plan.spec?.name === "string" ? plan.spec.name : null;
  const steps = plan.steps ?? [];
  const warnings = plan.warnings ?? [];
  const defaults = settingsText(plan.default_run_parameters);
  return (
    <div className="chat-pipeline-preview" data-testid="stored-plan-preview">
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="font-medium truncate">
          {name ? `Stored plan · ${name}` : "Stored plan"}
          <span className="text-base-content/50 font-normal">
            {" "}
            · {preview.chipId} · {preview.backendName}
          </span>
        </span>
        <span className="shrink-0 text-base-content/60">
          {plan.task_run_count ?? 0} task calls per target
        </span>
      </div>
      <dl className="mt-2 grid grid-cols-[fit-content(40%)_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
        <dt className="text-base-content/60">Starting qubits</dt>
        <dd className="m-0 font-mono wrap-anywhere">{preview.targetQids.join(", ") || "none"}</dd>
        <dt className="text-base-content/60">Review digest</dt>
        <dd className="m-0 font-mono wrap-anywhere">{preview.reviewDigest}</dd>
        <dt className="text-base-content/60">Expires</dt>
        <dd className="m-0 font-mono">{preview.expiresAt}</dd>
        {defaults && (
          <>
            <dt className="text-base-content/60">Run defaults</dt>
            <dd className="m-0 font-mono wrap-anywhere">{defaults}</dd>
          </>
        )}
      </dl>
      <p className="mt-1.5 text-xs text-base-content/55">
        As fetched when approval was requested. Filters and CR schedules choose later qubits and
        couplings from results.
      </p>
      {warnings.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs text-warning" aria-label="Warnings">
          {warnings.map((w) => (
            <li key={`${w.path}:${w.message}`}>
              <span className="font-mono">{w.path}</span>: {w.message}
            </li>
          ))}
        </ul>
      )}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="mt-2 inline-flex items-center gap-1 text-xs text-base-content/55 hover:text-base-content"
        aria-expanded={open}
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        {steps.length} step{steps.length === 1 ? "" : "s"}
      </button>
      {open && (
        <ol className="mt-1.5 space-y-1.5">
          {steps.map((step) => (
            <li key={step.index} className="flex gap-2 text-xs">
              <span className="chat-option-key shrink-0">{step.index}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-1.5">
                  <span className="font-medium">{step.name}</span>
                  {step.name !== step.type && (
                    <span className="text-base-content/45">{step.type}</span>
                  )}
                  {step.kind === "transform" && (
                    <span className="text-base-content/45">
                      · {step.type === "GenerateCRSchedule" ? "schedule" : "filter"}
                      {referenceLabel(step) && <> · reads {referenceLabel(step)}</>}
                    </span>
                  )}
                </div>
                {Object.keys(stepSpecSettings(plan.spec, step.index)).length > 0 && (
                  <div
                    className="mt-0.5 font-mono wrap-anywhere text-base-content/60"
                    data-testid="stored-plan-step-settings"
                  >
                    {JSON.stringify(stepSpecSettings(plan.spec, step.index))}
                  </div>
                )}
                {(step.calls ?? []).length > 0 && (
                  <ul className="mt-1 space-y-0.5">
                    {(step.calls ?? []).map((call) => (
                      <li key={call.call_id} className="font-mono wrap-anywhere">
                        <span className="chat-pipeline-task">
                          {call.name}
                          {call.call_id !== call.name && (
                            <span className="text-base-content/50"> · {call.call_id}</span>
                          )}
                        </span>
                        {call.on_failure !== "stop" && (
                          <span className="text-base-content/50">
                            {" "}
                            on_failure={call.on_failure}
                          </span>
                        )}
                        {settingsText(call.settings) && (
                          <span className="text-base-content/60">
                            {" "}
                            {settingsText(call.settings)}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
      <details className="collapse collapse-arrow mt-2 rounded-box border border-base-300">
        <summary className="collapse-title min-h-0 px-3 py-2 text-xs text-base-content/70">
          Approved spec (normalized, as stored)
        </summary>
        <div className="collapse-content px-3">
          <pre
            className="max-h-80 overflow-auto whitespace-pre-wrap wrap-anywhere font-mono text-xs"
            data-testid="stored-plan-spec"
          >
            {JSON.stringify(plan.spec ?? {}, null, 2)}
          </pre>
        </div>
      </details>
    </div>
  );
}
