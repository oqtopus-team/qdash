"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Bot, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import {
  getListEvaluationRunsQueryKey,
  getListEvaluationsQueryKey,
  useCreateEvaluationRun,
} from "@/client/evaluation/evaluation";
import { useGetCopilotConfig } from "@/client/copilot/copilot";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import { buildEvaluationModelOptions, type ModelOverride } from "@/lib/copilotModels";
import type { CreateEvaluationRunRequest, KnowledgeDraftResponse, Task } from "@/schemas";

import { examplesLabel, modeLabel } from "./evaluationDisplay";
import { KnowledgeDraftPicker } from "./KnowledgeDraftPicker";

export type EvaluationMode = "direct" | "planner";

/** One entity a chip-wide request could cover, with why its result cannot be judged when it cannot. */
export interface EvaluationTarget {
  qid: string;
  /** "not finished" or "no figure"; absent when the latest result can be evaluated. */
  blocked?: string;
}

/** What one evaluation request covers: a whole chip view, or named task results. */
export interface EvaluationRequestScope {
  chipId: string;
  taskName: string;
  entityType: "qubit" | "coupling";
  /** YYYYMMDD to evaluate that day's results instead of the latest ones. */
  date?: string | null;
  /** Restrict the run to these task results (a single result's review). */
  taskIds?: string[];
  /**
   * The entities the chip page shows results for, in natural order, so the
   * person can narrow a chip-wide run to some of them. Absent on a single
   * result's request.
   */
  targets?: EvaluationTarget[];
  trigger: "bulk" | "single";
}

/** Natural order of entity ids (Q2 before Q10, 0-1 before 0-10). */
function compareQids(left: string, right: string): number {
  return left.localeCompare(right, undefined, { numeric: true });
}

/**
 * The targets of a chip view from its per-entity results, as the API will
 * judge them: a result still running, or without a figure, cannot be
 * evaluated and is offered only as information.
 */
export function evaluationTargets(results: Record<string, Task> | undefined): EvaluationTarget[] {
  return Object.entries(results ?? {})
    .map(([qid, task]) => {
      const finished = task.status === "completed" || task.status === "failed";
      const figures = task.figure_path?.length ?? 0;
      const blocked = !finished ? "not finished" : figures === 0 ? "no figure" : undefined;
      return { qid, ...(blocked ? { blocked } : {}) };
    })
    .sort((a, b) => compareQids(a.qid, b.qid));
}

/** The entity word of a scope, plural. */
function entityNoun(scope: Pick<EvaluationRequestScope, "entityType">): string {
  return scope.entityType === "coupling" ? "couplings" : "qubits";
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

/**
 * The request body for one scope, mode and example setting. `qids` narrows a
 * chip-wide run to chosen entities; left out, the run covers every entity of
 * the chip view. `knowledgeDraftId` evaluates against an uploaded draft
 * instead of the task's shared knowledge.
 */
export function buildEvaluationRunRequest(
  scope: EvaluationRequestScope,
  mode: EvaluationMode,
  withExamples = false,
  qids?: string[],
  knowledgeDraftId?: string,
  evaluationModel?: Pick<ModelOverride, "provider" | "name">,
): CreateEvaluationRunRequest {
  return {
    chip_id: scope.chipId,
    task: scope.taskName,
    entity_type: scope.entityType,
    trigger: scope.trigger,
    mode,
    ...(withExamples ? { with_examples: true } : {}),
    ...(scope.date ? { date: scope.date } : {}),
    ...(scope.taskIds?.length ? { task_ids: scope.taskIds } : {}),
    ...(qids?.length ? { qids } : {}),
    ...(knowledgeDraftId ? { knowledge_draft_id: knowledgeDraftId } : {}),
    ...(evaluationModel
      ? {
          evaluation_model: {
            provider: evaluationModel.provider,
            name: evaluationModel.name,
          },
        }
      : {}),
  };
}

/** The chosen targets of a chip-wide request: which, and whether that is all of them. */
function TargetPicker({
  targets,
  excluded,
  onChange,
  disabled,
}: {
  targets: EvaluationTarget[];
  excluded: ReadonlySet<string>;
  onChange: (excluded: Set<string>) => void;
  disabled: boolean;
}) {
  const evaluable = targets.filter((target) => !target.blocked);
  const chosen = evaluable.filter((target) => !excluded.has(target.qid)).length;
  const toggle = (qid: string) => {
    const next = new Set(excluded);
    if (next.has(qid)) next.delete(qid);
    else next.add(qid);
    onChange(next);
  };
  return (
    <fieldset className="space-y-2" data-testid="target-picker">
      <div className="flex items-center justify-between gap-2">
        <legend className="label-text font-medium">
          Targets{" "}
          <span className="font-normal text-base-content/60">
            {chosen} of {evaluable.length} selected
          </span>
        </legend>
        <span className="flex gap-1">
          <button
            type="button"
            className="btn btn-ghost btn-xs"
            onClick={() => onChange(new Set())}
            disabled={disabled || excluded.size === 0}
          >
            All
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-xs"
            onClick={() => onChange(new Set(evaluable.map((target) => target.qid)))}
            disabled={disabled || chosen === 0}
          >
            None
          </button>
        </span>
      </div>
      <div className="flex max-h-40 flex-wrap gap-1 overflow-y-auto rounded-md border border-base-300 p-2">
        {targets.map((target) => {
          const selected = !target.blocked && !excluded.has(target.qid);
          return (
            <label
              key={target.qid}
              className={`flex cursor-pointer items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-xs ${
                target.blocked
                  ? "cursor-not-allowed border-base-300 text-base-content/40"
                  : selected
                    ? "border-primary bg-primary/10"
                    : "border-base-300"
              }`}
              title={target.blocked ? `${target.qid}: ${target.blocked}` : undefined}
            >
              <input
                type="checkbox"
                className="checkbox checkbox-xs"
                checked={selected}
                onChange={() => toggle(target.qid)}
                disabled={disabled || !!target.blocked}
                aria-label={target.qid}
              />
              {target.qid}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
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
  const [draft, setDraft] = useState<KnowledgeDraftResponse | null>(null);
  const [evaluationModelKey, setEvaluationModelKey] = useState("");
  // Targets the person unticked; empty means the whole chip view, as before.
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const create = useCreateEvaluationRun();
  const { data: copilotConfigResponse, isLoading: modelsLoading } = useGetCopilotConfig();
  const evaluationModelOptions = useMemo(
    () => buildEvaluationModelOptions(copilotConfigResponse?.data ?? null),
    [copilotConfigResponse?.data],
  );
  const evaluationModel =
    evaluationModelOptions.find((option) => option.key === evaluationModelKey) ??
    evaluationModelOptions[0] ??
    null;
  const isSubmitting = create.isPending;
  const targets = scope.targets;
  const evaluable = useMemo(
    () => (targets ?? []).filter((target) => !target.blocked).map((target) => target.qid),
    [targets],
  );
  const chosen = evaluable.filter((qid) => !excluded.has(qid));
  const narrowed = targets !== undefined && chosen.length < evaluable.length;
  const nothingChosen = targets !== undefined && evaluable.length > 0 && chosen.length === 0;
  const targetLabel = narrowed
    ? `${chosen.length} of ${evaluable.length} ${entityNoun(scope)} on ${scope.chipId}`
    : scopeLabel;

  const close = () => {
    if (isSubmitting) return;
    setExcluded(new Set());
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
        data: buildEvaluationRunRequest(
          scope,
          mode,
          withExamples,
          narrowed ? chosen : undefined,
          draft?.draft_id,
          evaluationModel?.model ?? undefined,
        ),
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
      setDraft(null);
      setExcluded(new Set());
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
              {targets && targets.length > 0 && (
                <TargetPicker
                  targets={targets}
                  excluded={excluded}
                  onChange={setExcluded}
                  disabled={isSubmitting}
                />
              )}

              <KnowledgeDraftPicker
                taskName={scope.taskName}
                draft={draft}
                onChange={(next) => {
                  setDraft(next);
                  // Copilot's evaluation call reads the shared knowledge.
                  if (next) setMode("direct");
                }}
                disabled={isSubmitting}
              />

              {evaluationModelOptions.length > 0 && (
                <fieldset className="fieldset min-w-0">
                  <legend className="fieldset-legend">Evaluation model</legend>
                  <select
                    className="select w-full min-w-0 max-w-full"
                    value={evaluationModel?.key ?? ""}
                    onChange={(event) => setEvaluationModelKey(event.target.value)}
                    disabled={isSubmitting || modelsLoading}
                    aria-label="Evaluation model"
                  >
                    {evaluationModelOptions.map((option) => (
                      <option key={option.key} value={option.key}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <p className="label">This model judges every selected figure in the run.</p>
                </fieldset>
              )}

              <RadioCards
                name="evaluation-mode"
                legend="Who prepares the prompt"
                options={MODE_OPTIONS}
                value={mode}
                onChange={setMode}
                disabled={isSubmitting || !!draft}
              />
              {draft && (
                <p className="-mt-2 text-xs text-base-content/60">
                  A knowledge draft is evaluated with the fixed prompt.
                </p>
              )}

              <RadioCards
                name="evaluation-examples"
                legend="Examples"
                options={EXAMPLE_OPTIONS}
                value={withExamples}
                onChange={setWithExamples}
                disabled={isSubmitting}
              />
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
                Will evaluate <strong>{targetLabel}</strong> with{" "}
                <strong>{settingsLabel(mode, withExamples)}</strong>
                {evaluationModel ? (
                  <>
                    {" "}
                    using <strong>{evaluationModel.model?.name}</strong>
                  </>
                ) : null}
                {draft ? (
                  <>
                    , against the knowledge draft <strong>{draft.filename || "uploaded"}</strong>
                  </>
                ) : (
                  ""
                )}
                . Recorded as one run.
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
            disabled={isSubmitting || (!chatting && nothingChosen)}
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
