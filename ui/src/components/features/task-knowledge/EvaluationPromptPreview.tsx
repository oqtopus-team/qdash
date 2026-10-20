"use client";

import { useState } from "react";
import { Eye, RefreshCw } from "lucide-react";
import { useGetTaskEvaluationPrompts } from "@/client/task/task";
import { questionLabel } from "@/components/features/evaluations/evaluationDisplay";
import { getApiErrorMessage } from "@/lib/utils/apiError";

type Props = {
  taskName: string;
  /** How many labeled examples the task has; in-context needs at least one. */
  exampleCount: number;
};

/**
 * The prompts the evaluation model would receive for this task, built by the
 * Agent Runtime from the task's reference (and its labeled examples, in
 * context) without a figure or a model call. Fetched on demand, so editing
 * the knowledge and pressing the button shows what the edit turns into.
 */
export function EvaluationPromptPreview({ taskName, exampleCount }: Props) {
  const [withExamples, setWithExamples] = useState(false);
  const [requested, setRequested] = useState(false);
  const {
    data: response,
    isFetching,
    error,
    refetch,
  } = useGetTaskEvaluationPrompts(
    taskName,
    { with_examples: withExamples },
    { query: { enabled: requested, retry: false, staleTime: 0 } },
  );
  const data = response?.data;
  const inContextDisabled = exampleCount === 0;

  const choose = (next: boolean) => {
    if (next === withExamples) return;
    setWithExamples(next);
  };

  return (
    <section className="mt-10" aria-labelledby="evaluation-prompts-heading">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <div>
          <h2 id="evaluation-prompts-heading" className="text-lg font-semibold">
            Evaluation prompts
          </h2>
          <p className="text-sm text-base-content/60">
            What the evaluation model is sent for this task, one question at a time, built from the
            reference above. <code className="font-mono">[figure]</code> marks where a plot goes.
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div className="join" role="group" aria-label="Examples">
            <button
              type="button"
              className={`btn btn-sm join-item ${withExamples ? "btn-ghost" : "btn-active"}`}
              onClick={() => choose(false)}
              aria-pressed={!withExamples}
            >
              Zero-shot
            </button>
            <button
              type="button"
              className={`btn btn-sm join-item ${withExamples ? "btn-active" : "btn-ghost"}`}
              onClick={() => choose(true)}
              aria-pressed={withExamples}
              disabled={inContextDisabled}
              title={
                inContextDisabled
                  ? "This task has no labeled examples; add one under examples/ to preview in-context prompts"
                  : "Lay out the task's labeled examples before the figure"
              }
            >
              In-context
            </button>
          </div>
          <button
            type="button"
            className="btn btn-sm btn-outline gap-1"
            onClick={() => {
              if (requested) void refetch();
              else setRequested(true);
            }}
            disabled={isFetching}
          >
            {requested ? (
              <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
            ) : (
              <Eye className="h-4 w-4" />
            )}
            {requested ? "Refresh" : "Preview"}
          </button>
        </div>
      </div>

      {!requested && (
        <p className="text-sm text-base-content/50">
          Press <strong>Preview</strong> to build the prompts. Nothing is sent to the model.
        </p>
      )}
      {requested && error && (
        <div className="alert alert-error text-sm">
          {getApiErrorMessage(error, "Could not build the prompts")}
        </div>
      )}
      {requested && !error && !data && isFetching && (
        <div className="flex items-center gap-2 text-sm text-base-content/60">
          <span className="loading loading-spinner loading-sm" />
          Building prompts…
        </div>
      )}
      {data && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-base-content/60">
            <span>
              {data.model ? (
                <span className="font-mono">{data.model}</span>
              ) : (
                "no evaluation model configured"
              )}
            </span>
            <span>
              {data.knowledge_chars
                ? `reference ${data.knowledge_chars} chars`
                : "no reference (generic templates)"}
            </span>
            <span>
              {data.with_examples
                ? `${data.examples_used ?? 0} of ${data.examples?.length ?? 0} examples shown`
                : "zero-shot"}
            </span>
          </div>
          {(data.questions ?? []).map((question, index) => (
            <details
              key={question.key}
              className="collapse collapse-arrow rounded-lg border border-base-300 bg-base-100"
              open={index === 0}
            >
              <summary className="collapse-title min-h-0 py-3 text-sm font-medium">
                {questionLabel(question.key)}{" "}
                <span className="font-mono text-xs text-base-content/50">{question.key}</span>
              </summary>
              <div className="collapse-content">
                <pre className="whitespace-pre-wrap break-words rounded bg-base-200/60 p-3 text-xs">
                  {question.prompt}
                </pre>
              </div>
            </details>
          ))}
        </div>
      )}
    </section>
  );
}
