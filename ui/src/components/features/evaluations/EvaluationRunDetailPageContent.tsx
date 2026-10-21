"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, RotateCcw, Square, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { type ReactNode, useState } from "react";

import {
  getGetEvaluationRunQueryKey,
  useCancelEvaluationRun,
  useGetEvaluationRun,
  useRetryEvaluationRun,
} from "@/client/evaluation/evaluation";
import { PageContainer } from "@/components/ui/PageContainer";
import { formatDateTime } from "@/lib/utils/datetime";
import type { EvaluationItem, EvaluationRunSummary } from "@/schemas";

import { EvaluationCard } from "./EvaluationCard";
import { KnowledgeDraftDownloadButton } from "./KnowledgeDraftDownloadButton";
import { compareHref } from "./evaluationCompare";
import { promptProfile, rangeLabel, referenceLabel, systemPromptLabel } from "./evaluationPrompt";
import { RunPicker } from "./RunPicker";
import {
  agreementRate,
  evaluatorLabel,
  knowledgeLabel,
  modeLabel,
  runDone,
  runIsActive,
  runTimingLabel,
  tokenPeak,
  tokenPeakLabel,
  triggerLabel,
} from "./evaluationDisplay";

/** A labeled value in the run summary. */
function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase text-base-content/50">{label}</div>
      <div className="mt-1 text-sm">{value}</div>
    </div>
  );
}

/**
 * What the evaluation model was given in this run, read off the records: the
 * system prompt, the reference (task knowledge), labeled examples, figures and
 * question, and whether they were the same for every evaluation. With Copilot
 * in the loop they can differ per evaluation, which this makes visible; the
 * exact prompt of each evaluation is under its own "Prompt sent to the model".
 */
function RunPromptPanel({
  run,
  evaluations,
}: {
  run: EvaluationRunSummary;
  evaluations: EvaluationItem[];
}) {
  const profile = promptProfile(evaluations);
  const peak = tokenPeak(evaluations.map((item) => item.output));
  const [showSystemPrompt, setShowSystemPrompt] = useState(false);
  if (profile.recorded === 0) return null;
  const consistent =
    profile.systemPromptVariants <= 1 &&
    profile.referenceVariants <= 1 &&
    profile.questionVariants <= 1 &&
    profile.examples.min === profile.examples.max &&
    profile.figures.min === profile.figures.max;
  return (
    <div
      className="mb-4 rounded-lg border border-base-300 bg-base-100 p-4"
      data-testid="run-prompt"
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">Prompt</span>
        <span className="text-xs text-base-content/60">
          {consistent
            ? `the same ingredients for all ${profile.recorded} evaluation${profile.recorded === 1 ? "" : "s"}`
            : `varies across the ${profile.recorded} evaluations${run.mode === "planner" ? " (Copilot wrote the context and may pass its own reference)" : ""}`}
        </span>
      </div>
      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="System prompt" value={systemPromptLabel(profile)} />
        <Stat label="Reference" value={referenceLabel(profile)} />
        <Stat label="Labeled examples" value={rangeLabel(profile.examples)} />
        <Stat label="Figures" value={rangeLabel(profile.figures)} />
        <Stat
          label="Tokens"
          value={
            peak ? (
              <span className={peak.nearLimit ? "font-medium text-warning" : undefined}>
                {tokenPeakLabel(peak)}
              </span>
            ) : (
              "not recorded"
            )
          }
        />
        <Stat
          label="Question"
          value={
            profile.questionVariants > 1
              ? "varies"
              : profile.question || (run.question ? "varies" : "none")
          }
        />
      </div>
      {profile.systemPrompt && (
        <details
          className="mt-3 text-sm"
          onToggle={(event) => setShowSystemPrompt((event.target as HTMLDetailsElement).open)}
        >
          <summary className="cursor-pointer font-medium text-primary">System prompt text</summary>
          {showSystemPrompt && (
            <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap rounded bg-base-200/40 p-2 text-xs">
              {profile.systemPrompt}
            </pre>
          )}
        </details>
      )}
      <p className="mt-2 text-xs text-base-content/50">
        The reference is the task&apos;s knowledge as it was when the run was made; its hash tells
        two versions apart. Each evaluation below shows the exact prompt it was sent.
      </p>
    </div>
  );
}

/** One evaluation run: its progress, what judged it, and every record with verdict controls. */
export function EvaluationRunDetailPageContent({ runId }: { runId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const cancelRun = useCancelEvaluationRun();
  const retryRun = useRetryEvaluationRun();
  const goBack = () => router.push("/evaluations");
  const {
    data: response,
    isLoading,
    isError,
  } = useGetEvaluationRun(runId, {
    query: {
      refetchInterval: (query) => {
        const run = query.state.data?.data.run;
        return run && runIsActive(run) ? 5_000 : false;
      },
    },
  });
  const data = response?.data;

  if (isLoading) {
    return (
      <PageContainer maxWidth>
        <div className="flex justify-center py-16">
          <span className="loading loading-spinner loading-lg" />
        </div>
      </PageContainer>
    );
  }

  if (isError || !data) {
    return (
      <PageContainer maxWidth>
        <div className="mb-6 flex items-center gap-3">
          <button className="btn btn-square btn-ghost btn-sm shrink-0" onClick={goBack}>
            <ArrowLeft className="h-4 w-4" />
          </button>
          <h1 className="text-xl font-bold">AI Evaluation</h1>
        </div>
        <div className="alert alert-error">
          <XCircle className="h-5 w-5" />
          <span>Failed to load this evaluation run.</span>
        </div>
      </PageContainer>
    );
  }

  const { run, evaluations } = data;
  const agreement = agreementRate(run);
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: getGetEvaluationRunQueryKey(runId) });
  const retryable = evaluations.some((item) =>
    ["failed", "interrupted", "cancelled"].includes(item.status),
  );

  return (
    <PageContainer maxWidth>
      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <button className="btn btn-square btn-ghost btn-sm shrink-0" onClick={goBack}>
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="min-w-0">
            <h1 className="truncate text-xl font-bold">
              {run.task_name} · {run.chip_id}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-base-content/50">
              <span className="badge badge-neutral badge-sm">{run.entity_type}</span>
              <span className="badge badge-outline badge-sm">{triggerLabel(run.trigger)}</span>
              <span className="badge badge-outline badge-sm">{modeLabel(run.mode)}</span>
              {run.date && <span>{run.date}</span>}
              <span>requested {formatDateTime(run.requested_at)}</span>
              <span>by {run.requested_by}</span>
              <span className="font-mono">{run.run_id}</span>
            </div>
          </div>
        </div>
        <div className="flex flex-shrink-0 flex-wrap items-center gap-2">
          <RunPicker
            chipId={run.chip_id}
            taskName={run.task_name}
            excludeRunId={run.run_id}
            onPick={(other) => router.push(compareHref(run.run_id, other))}
            className="max-w-xs"
          />
          {runIsActive(run) && (
            <button
              type="button"
              className="btn btn-ghost btn-sm gap-1"
              disabled={cancelRun.isPending}
              onClick={() => cancelRun.mutate({ runId }, { onSuccess: refresh })}
            >
              <Square className="h-3.5 w-3.5" />
              Cancel
            </button>
          )}
          {!runIsActive(run) && retryable && (
            <button
              type="button"
              className="btn btn-ghost btn-sm gap-1"
              disabled={retryRun.isPending}
              onClick={() => retryRun.mutate({ runId }, { onSuccess: refresh })}
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Retry unfinished
            </button>
          )}
          {runIsActive(run) && <span className="badge badge-info">running</span>}
          <span className="badge badge-neutral">
            {runDone(run)}/{run.total} done
          </span>
          {run.failed_count > 0 && (
            <span className="badge badge-error">{run.failed_count} failed</span>
          )}
          {(run.interrupted_count ?? 0) > 0 && (
            <span className="badge badge-warning">{run.interrupted_count} interrupted</span>
          )}
          {(run.cancelled_count ?? 0) > 0 && (
            <span className="badge badge-ghost">{run.cancelled_count} cancelled</span>
          )}
        </div>
      </div>

      <div className="mb-4 rounded-lg border border-base-300 bg-base-100 p-4">
        <div className="grid gap-3 md:grid-cols-6">
          <Stat label="Success" value={`${run.success_count}/${run.completed_count}`} />
          <Stat label="Complete" value={`${run.complete_count}/${run.completed_count}`} />
          <Stat label="Time" value={runTimingLabel(run) ?? "-"} />
          <Stat
            label="Agreement"
            value={
              agreement === null
                ? "not judged yet"
                : `${Math.round(agreement * 100)}% of ${run.agree_count + run.disagree_count}`
            }
          />
          <Stat
            label="Evaluation model"
            value={
              run.evaluation_model ||
              ((run.models?.length ?? 0) > 1 ? `mixed (${run.models?.length})` : run.model || "-")
            }
          />
          <Stat
            label="Evaluator"
            value={
              (run.evaluators?.length ?? 0) > 1
                ? `mixed (${run.evaluators?.length})`
                : evaluatorLabel(run.evaluator) || "-"
            }
          />
          <Stat
            label={run.mode === "planner" ? "Copilot model" : "Mode"}
            value={run.mode === "planner" ? run.planner_model || "-" : modeLabel(run.mode)}
          />
        </div>
        {run.knowledge_draft_id && (
          <div className="mt-3 text-sm" data-testid="run-knowledge">
            <span className="text-xs uppercase text-base-content/50">Knowledge</span>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-base-content/80">
              {knowledgeLabel(run)}
              <span className="font-mono text-xs text-base-content/50">
                {run.knowledge_draft_id.slice(0, 12)}
              </span>
              <KnowledgeDraftDownloadButton
                draftId={run.knowledge_draft_id}
                filename={run.knowledge_draft_name || `${run.task_name}.zip`}
              />
              <span className="block w-full text-xs text-base-content/60">
                Evaluated against an uploaded knowledge draft instead of the shared knowledge.
              </span>
            </p>
          </div>
        )}
        {run.question && (
          <div className="mt-3 text-sm">
            <span className="text-xs uppercase text-base-content/50">Question</span>
            <p className="mt-1 text-base-content/80">{run.question}</p>
          </div>
        )}
      </div>

      <RunPromptPanel run={run} evaluations={evaluations} />

      <div className="space-y-4">
        {evaluations.map((item) => (
          <EvaluationCard key={item.evaluation_id} item={item} />
        ))}
      </div>
    </PageContainer>
  );
}
