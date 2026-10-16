"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { validateCalibrationPipeline } from "@/client/calibration-pipeline/calibration-pipeline";
import type { ResolvedPipelineStep } from "@/schemas";

/** The parts of a CalibrationPipelineSpec the card reads before validation answers. */
export interface PipelineSpecLike {
  name?: string;
  targets?: { qids?: string[]; mux_ids?: number[]; exclude_qids?: string[] };
  steps: Array<{ type: string; step_name?: string; tasks?: string[]; [key: string]: unknown }>;
  [key: string]: unknown;
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

/** Steps as the spec describes them, before the server fills in default task lists. */
function stepsFromSpec(spec: PipelineSpecLike): ResolvedPipelineStep[] {
  return spec.steps.map((step, i) => ({
    index: i + 1,
    type: step.type,
    name: step.step_name ?? step.type,
    kind:
      step.type.startsWith("Filter") || step.type === "GenerateCRSchedule"
        ? "transform"
        : "calibration",
    tasks: step.tasks ?? [],
  }));
}

function TaskChips({ tasks }: { tasks: string[] }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? tasks : tasks.slice(0, TASK_PREVIEW_LIMIT);
  const hidden = tasks.length - shown.length;
  return (
    <span className="flex flex-wrap gap-1">
      {shown.map((task, i) => (
        <span key={`${task}-${i}`} className="chat-pipeline-task">
          {task}
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
  const steps = result?.steps?.length ? result.steps : stepsFromSpec(spec);
  const problems = result?.problems ?? [];
  const taskRuns = result?.task_run_count ?? steps.reduce((n, s) => n + s.tasks.length, 0);

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
        <CheckCircle2 className="w-3.5 h-3.5" /> Ready · {taskRuns} task runs per target
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

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="mt-2 inline-flex items-center gap-1 text-[11px] text-base-content/55 hover:text-base-content"
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
                    <span className="text-base-content/45">· filter</span>
                  )}
                </div>
                {step.tasks.length > 0 ? (
                  <div className="mt-1">
                    <TaskChips tasks={step.tasks} />
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
