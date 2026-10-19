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

import { examplesLabel, modeLabel } from "./evaluationDisplay";

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
  /**
   * Opens a chat about the result instead of an evaluation. When given, the
   * modal is the one "Ask AI" entry for a single result: a recorded evaluation
   * (model only or via Copilot) or a conversation, chosen the same way.
   */
  onChat?: () => void;
}

/** What the modal can do for one result: a recorded evaluation, or a chat about it. */
type AskAction = "evaluate" | "chat";

interface Option<T> {
  value: T;
  title: string;
  description: string;
}

const ACTION_OPTIONS: ReadonlyArray<Option<AskAction>> = [
  {
    value: "evaluate",
    title: "Evaluate the figure",
    description:
      "The calibration evaluation model judges the figure; the evaluation is recorded with what the model saw.",
  },
  {
    value: "chat",
    title: "Chat with Copilot",
    description:
      "Open a conversation about this result with Copilot, its context and figures loaded. Nothing is recorded unless Copilot evaluates the figure on its own.",
  },
];

/** Who prepares the prompt: QDash the same way every time, or Copilot. */
const MODE_OPTIONS: ReadonlyArray<Option<EvaluationMode>> = [
  {
    value: "direct",
    title: "Fixed prompt",
    description:
      "QDash builds the prompt: the result's summary and the task's reference from Knowledge, the same way every time. Fast and reproducible.",
  },
  {
    value: "planner",
    title: "Via Copilot",
    description:
      "Copilot (the chat planner) summarises the result and calls the evaluation itself, as AI Chat does. Slower; what Copilot did and answered is recorded too.",
  },
];

/** A radio group of cards, one per option. */
function RadioCards<T extends string | boolean>({
  name,
  legend,
  options,
  value,
  onChange,
  disabled,
}: {
  name: string;
  legend: string;
  options: ReadonlyArray<Option<T>>;
  value: T;
  onChange: (value: T) => void;
  disabled: boolean;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="label-text mb-1 font-medium">{legend}</legend>
      {options.map((option) => (
        <label
          key={String(option.value)}
          className={`flex cursor-pointer gap-3 rounded-lg border p-3 ${
            value === option.value ? "border-primary bg-primary/5" : "border-base-300"
          }`}
        >
          <input
            type="radio"
            name={name}
            className="radio radio-primary radio-sm mt-0.5"
            checked={value === option.value}
            onChange={() => onChange(option.value)}
            disabled={disabled}
          />
          <span>
            <span className="font-medium">{option.title}</span>
            <span className="block text-xs text-base-content/60">{option.description}</span>
          </span>
        </label>
      ))}
    </fieldset>
  );
}

/** The chosen settings in the words the run will be labeled with everywhere else. */
function settingsLabel(mode: EvaluationMode, withExamples: boolean): string {
  return `${modeLabel(mode)} · ${examplesLabel(withExamples)}`;
}

/** Whether the figure is judged alone or after labeled examples, in QCalEval's terms. */
const EXAMPLE_OPTIONS: ReadonlyArray<Option<boolean>> = [
  {
    value: false,
    title: "Zero-shot",
    description: "The figure is judged against the task's reference alone.",
  },
  {
    value: true,
    title: "In-context (labeled examples)",
    description:
      "The task's expert-labeled example plots from Knowledge are shown before the figure, each followed by its diagnosis, the way QCalEval evaluates in context.",
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
  onChat,
}: EvaluationRequestModalProps) {
  const router = useRouter();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [action, setAction] = useState<AskAction>("evaluate");
  const chatting = !!onChat && action === "chat";
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
    if (chatting) {
      onChat?.();
      onClose();
      return;
    }
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
      toast.success(
        `Evaluation started (${settingsLabel(mode, withExamples)}): ${queued} task result${queued === 1 ? "" : "s"} queued`,
        {
          description: skipped ? `${skipped} skipped (no evaluable result)` : undefined,
          action: { label: "Open run", onClick: () => router.push(`/evaluations/${runId}`) },
        },
      );
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
            <DialogTitle className="font-semibold">
              {onChat ? "Ask AI" : "Request AI evaluation"}
            </DialogTitle>
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
          {onChat
            ? `Have the figure of ${scopeLabel} judged, or talk about it. An evaluation is recorded with what the model saw, so runs can be compared and judged afterwards.`
            : `The calibration evaluation model judges the figure of ${scopeLabel}. Each evaluation is recorded with what the model saw, so runs can be compared and judged afterwards.`}
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

          {onChat && (
            <RadioCards
              name="ask-action"
              legend="What to do"
              options={ACTION_OPTIONS}
              value={action}
              onChange={setAction}
              disabled={isSubmitting}
            />
          )}

          {chatting ? (
            <p className="text-xs text-base-content/60">
              You will type your question in the chat. Copilot can call the evaluation model from
              there; such a judgement is recorded too.
            </p>
          ) : (
            <>
              <RadioCards
                name="evaluation-mode"
                legend="Who prepares the prompt"
                options={MODE_OPTIONS}
                value={mode}
                onChange={setMode}
                disabled={isSubmitting}
              />

              <RadioCards
                name="evaluation-examples"
                legend="Examples"
                options={EXAMPLE_OPTIONS}
                value={withExamples}
                onChange={setWithExamples}
                disabled={isSubmitting}
              />

              <label className="form-control w-full">
                <span className="label-text mb-1">
                  Question for the evaluation model (optional)
                </span>
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
            </>
          )}

          <div
            className="rounded-md border border-primary/40 bg-primary/5 px-3 py-2 text-sm"
            data-testid="request-summary"
          >
            {chatting ? (
              <>
                Will open a chat about <strong>{scopeLabel}</strong>.
              </>
            ) : (
              <>
                Will evaluate <strong>{scopeLabel}</strong> with{" "}
                <strong>{settingsLabel(mode, withExamples)}</strong>
                {question.trim() ? ", with your question" : ""}. Recorded as one run.
              </>
            )}
          </div>
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
            {chatting ? "Open chat" : "Evaluate"}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
