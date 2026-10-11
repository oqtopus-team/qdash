"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Bot, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  getListEvaluationRunsQueryKey,
  getListEvaluationsQueryKey,
  useCreateEvaluationRun,
} from "@/client/evaluation/evaluation";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import type { CreateEvaluationRunRequest } from "@/schemas";

export type EvaluationMode = "direct" | "planner";

/** What one evaluation request covers: a whole chip view, or named task results. */
export interface EvaluationRequestScope {
  chipId: string;
  taskName: string;
  entityType: "qubit" | "coupling";
  /** YYYYMMDD to evaluate that day's results instead of the latest ones. */
  date?: string | null;
  /** Restrict the run to these task results (a single result's review). */
  taskIds?: string[];
  trigger: "bulk" | "single";
}

interface EvaluationRequestModalProps {
  isOpen: boolean;
  onClose: () => void;
  scope: EvaluationRequestScope;
  /** Human description of the scope, e.g. "all qubits on 64Qv3" or "CheckRabi · Q05". */
  scopeLabel: string;
}

const MODE_OPTIONS: ReadonlyArray<{ mode: EvaluationMode; title: string; description: string }> = [
  {
    mode: "direct",
    title: "Direct",
    description:
      "Runs the evidence and evaluation tools as such. Fast and reproducible: the same reference reaches the evaluation model every time.",
  },
  {
    mode: "planner",
    title: "Planner",
    description:
      "Lets the chat planner summarise the result and call the evaluation itself, as Ask AI does. Slower, and records what the planner did and answered.",
  },
];

/** The request body for one scope, mode, example setting and optional question. */
export function buildEvaluationRunRequest(
  scope: EvaluationRequestScope,
  mode: EvaluationMode,
  question: string,
  withExamples = false,
): CreateEvaluationRunRequest {
  const trimmed = question.trim();
  return {
    chip_id: scope.chipId,
    task: scope.taskName,
    entity_type: scope.entityType,
    trigger: scope.trigger,
    mode,
    ...(withExamples ? { with_examples: true } : {}),
    ...(scope.date ? { date: scope.date } : {}),
    ...(scope.taskIds?.length ? { task_ids: scope.taskIds } : {}),
    ...(trimmed ? { question: trimmed } : {}),
  };
}

function errorDetail(error: unknown): string {
  if (error && typeof error === "object") {
    const response = (error as { response?: { data?: unknown } }).response;
    const data = response?.data;
    if (data && typeof data === "object") {
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string" && message) return message;
  }
  return "The evaluation could not be started.";
}

export function EvaluationRequestModal({
  isOpen,
  onClose,
  scope,
  scopeLabel,
}: EvaluationRequestModalProps) {
  const router = useRouter();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<EvaluationMode>("direct");
  const [withExamples, setWithExamples] = useState(false);
  const [question, setQuestion] = useState("");
  const create = useCreateEvaluationRun();
  const isSubmitting = create.isPending;

  const close = () => {
    if (isSubmitting) return;
    onClose();
  };

  const submit = async () => {
    try {
      const response = await create.mutateAsync({
        data: buildEvaluationRunRequest(scope, mode, question, withExamples),
      });
      const created = response.data;
      const runId = created.run.run_id;
      const queued = created.task_ids.length;
      const skipped = Object.keys(created.skipped ?? {}).length;
      queryClient.invalidateQueries({ queryKey: getListEvaluationRunsQueryKey() });
      for (const taskId of created.task_ids) {
        queryClient.invalidateQueries({
          queryKey: getListEvaluationsQueryKey({ task_id: taskId }),
        });
      }
      toast.success(`Evaluation started: ${queued} task result${queued === 1 ? "" : "s"} queued`, {
        description: skipped ? `${skipped} skipped (no evaluable result)` : undefined,
        action: { label: "Open run", onClick: () => router.push(`/evaluations/${runId}`) },
      });
      setQuestion("");
      onClose();
    } catch (error) {
      toast.error(errorDetail(error));
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && close()}>
      <DialogContent className="max-w-lg">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-primary" />
            <DialogTitle className="font-semibold">Request AI evaluation</DialogTitle>
          </div>
          <button
            type="button"
            className="btn btn-sm btn-ghost btn-circle"
            onClick={close}
            disabled={isSubmitting}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <DialogDescription className="text-sm text-base-content/70 mt-1">
          The calibration evaluation model judges the figure of {scopeLabel}. Each evaluation is
          recorded with what the model saw, so runs can be compared and judged afterwards.
        </DialogDescription>

        <div className="mt-4 space-y-4 text-sm">
          <div className="rounded-md bg-base-200 px-3 py-2">
            <div className="flex justify-between gap-3">
              <span className="text-base-content/60">Task</span>
              <span className="font-mono text-right">{scope.taskName}</span>
            </div>
            <div className="flex justify-between gap-3 mt-1">
              <span className="text-base-content/60">Scope</span>
              <span className="text-right">{scopeLabel}</span>
            </div>
            {scope.date && (
              <div className="flex justify-between gap-3 mt-1">
                <span className="text-base-content/60">Date</span>
                <span className="font-mono text-right">{scope.date}</span>
              </div>
            )}
          </div>

          <fieldset className="space-y-2">
            <legend className="label-text mb-1">How to evaluate</legend>
            {MODE_OPTIONS.map((option) => (
              <label
                key={option.mode}
                className={`flex cursor-pointer gap-3 rounded-lg border p-3 ${
                  mode === option.mode ? "border-primary bg-primary/5" : "border-base-300"
                }`}
              >
                <input
                  type="radio"
                  name="evaluation-mode"
                  className="radio radio-primary radio-sm mt-0.5"
                  checked={mode === option.mode}
                  onChange={() => setMode(option.mode)}
                  disabled={isSubmitting}
                />
                <span>
                  <span className="font-medium">{option.title}</span>
                  <span className="block text-xs text-base-content/60">{option.description}</span>
                </span>
              </label>
            ))}
          </fieldset>

          <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-base-300 p-3">
            <input
              type="checkbox"
              className="checkbox checkbox-primary checkbox-sm mt-0.5"
              checked={withExamples}
              onChange={(event) => setWithExamples(event.target.checked)}
              disabled={isSubmitting}
            />
            <span>
              <span className="font-medium">Show labeled examples</span>
              <span className="block text-xs text-base-content/60">
                The task&apos;s expert-labeled example plots are shown before each figure, each
                followed by its diagnosis (in-context examples). Off: zero-shot, as before.
              </span>
            </span>
          </label>

          <label className="form-control w-full">
            <span className="label-text mb-1">Question for the evaluation model (optional)</span>
            <textarea
              className="textarea textarea-bordered textarea-sm w-full"
              rows={2}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="e.g. Is the decay fit trustworthy beyond 50 Cliffords?"
              maxLength={2000}
              disabled={isSubmitting}
            />
          </label>
        </div>

        <div className="modal-action">
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={close}
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-sm btn-primary gap-2"
            onClick={submit}
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <span className="loading loading-spinner loading-xs" />
            ) : (
              <Bot className="h-4 w-4" />
            )}
            Evaluate
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
