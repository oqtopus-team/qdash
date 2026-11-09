"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { validateCalibrationPipeline } from "@/client/calibration-pipeline/calibration-pipeline";
import type { ResolvedPipelineStep } from "@/schemas";

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
                      · filter
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
