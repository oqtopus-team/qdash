"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  ExternalLink,
  Image as ImageIcon,
  LoaderCircle,
  ThumbsDown,
  ThumbsUp,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
  getGetEvaluationRunQueryKey,
  getListEvaluationsQueryKey,
  useSetEvaluationVerdict,
} from "@/client/evaluation/evaluation";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { ModelInputView } from "./ModelInputView";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { formatDateTime } from "@/lib/utils/datetime";
import type { EvaluationItem, SetEvaluationVerdictRequestIssuesItem } from "@/schemas";

import {
  DIAGNOSIS_SECTIONS,
  answerShortfall,
  callLabel,
  diagnosisOf,
  diagnosisOutcome,
  diagnosisSuccess,
  diagnosisText,
  evaluatorLabel,
  fitAssessment,
  fitBadgeClass,
  fitLabel,
  formatDuration,
  outcomeBadgeClass,
  questionLabel,
  statusLabel,
  tokenPeak,
  tokenPeakLabel,
} from "./evaluationDisplay";
import { promptSummary } from "./evaluationPrompt";

interface EvaluationCardProps {
  item: EvaluationItem;
  /** Show the task result's figure next to the record (off where the page shows it already). */
  showFigure?: boolean;
  /** Show the target and task name in the header (off on a single task result's page). */
  showTarget?: boolean;
  /** Link to the run the evaluation belongs to. */
  showRunLink?: boolean;
}

const VERDICT_ISSUES: Array<{
  value: SetEvaluationVerdictRequestIssuesItem;
  label: string;
}> = [
  { value: "parameter_extraction", label: "Parameters" },
  { value: "diagnosis", label: "Diagnosis" },
  { value: "recommendation", label: "Recommendation" },
  { value: "insufficient_evidence", label: "Insufficient evidence" },
  { value: "other", label: "Other" },
];

function StatusIcon({ item }: { item: EvaluationItem }) {
  if (item.status === "failed" || item.status === "interrupted")
    return <XCircle className="h-4 w-4 text-error" aria-hidden="true" />;
  if (item.status === "cancelled")
    return <XCircle className="h-4 w-4 text-base-content/40" aria-hidden="true" />;
  if (item.status !== "completed") {
    return <LoaderCircle className="h-4 w-4 animate-spin text-info" aria-hidden="true" />;
  }
  const success = diagnosisSuccess(diagnosisOf(item));
  if (success === null || item.output?.complete !== true)
    return <CircleHelp className="h-4 w-4 text-warning" aria-label="incomplete evaluation" />;
  if (success === false)
    return <AlertTriangle className="h-4 w-4 text-warning" aria-hidden="true" />;
  return <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />;
}

function Verdict({ item }: { item: EvaluationItem }) {
  const queryClient = useQueryClient();
  const setVerdict = useSetEvaluationVerdict();
  const current = item.verdict?.agree ?? null;
  const [note, setNote] = useState(item.verdict?.note ?? "");
  const [issues, setIssues] = useState<SetEvaluationVerdictRequestIssuesItem[]>(
    item.verdict?.issues ?? [],
  );
  const [editingNote, setEditingNote] = useState(false);

  const save = (
    agree: boolean | null,
    nextNote: string | null,
    nextIssues: SetEvaluationVerdictRequestIssuesItem[],
  ) => {
    setVerdict.mutate(
      { evaluationId: item.evaluation_id, data: { agree, note: nextNote, issues: nextIssues } },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getGetEvaluationRunQueryKey(item.run_id) });
          queryClient.invalidateQueries({
            queryKey: getListEvaluationsQueryKey({ task_id: item.task_id }),
          });
          setEditingNote(false);
        },
      },
    );
  };
  const toggle = (agree: boolean) => {
    // Clicking the active verdict clears it; the note goes with it.
    if (current === agree) {
      setNote("");
      setIssues([]);
      save(null, null, []);
    } else {
      save(agree, note.trim() || null, issues);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="evaluation-verdict">
      <span className="text-xs text-base-content/60">Do you agree?</span>
      <button
        type="button"
        className={`btn btn-xs gap-1 ${current === true ? "btn-success" : "btn-ghost"}`}
        onClick={() => toggle(true)}
        disabled={setVerdict.isPending}
        aria-pressed={current === true}
      >
        <ThumbsUp className="h-3.5 w-3.5" />
        Agree
      </button>
      <button
        type="button"
        className={`btn btn-xs gap-1 ${current === false ? "btn-error" : "btn-ghost"}`}
        onClick={() => toggle(false)}
        disabled={setVerdict.isPending}
        aria-pressed={current === false}
      >
        <ThumbsDown className="h-3.5 w-3.5" />
        Disagree
      </button>
      {current !== null && !editingNote && (
        <button type="button" className="btn btn-xs btn-ghost" onClick={() => setEditingNote(true)}>
          {item.verdict?.note ? "Edit note" : "Add note"}
        </button>
      )}
      {editingNote && (
        <span className="flex w-full flex-wrap items-center gap-2">
          {current === false && (
            <span className="flex w-full flex-wrap gap-2">
              {VERDICT_ISSUES.map((issue) => (
                <label key={issue.value} className="label cursor-pointer gap-1 py-0 text-xs">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-xs"
                    checked={issues.includes(issue.value)}
                    onChange={(event) =>
                      setIssues((currentIssues) =>
                        event.target.checked
                          ? [...currentIssues, issue.value]
                          : currentIssues.filter((value) => value !== issue.value),
                      )
                    }
                  />
                  {issue.label}
                </label>
              ))}
            </span>
          )}
          <input
            type="text"
            className="input input-bordered input-xs flex-1"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Why?"
            maxLength={2000}
          />
          <button
            type="button"
            className="btn btn-xs btn-primary"
            onClick={() => save(current, note.trim() || null, issues)}
            disabled={setVerdict.isPending}
          >
            Save
          </button>
        </span>
      )}
      {item.verdict && !editingNote && (
        <span className="w-full text-xs text-base-content/60">
          <span>
            {item.verdict.note ? `“${item.verdict.note}” — ` : ""}
            {item.verdict.username}, {formatDateTime(item.verdict.updated_at)}
          </span>
          {(item.verdict.issues?.length ?? 0) > 0 && (
            <span className="mt-1 flex flex-wrap gap-1">
              {item.verdict.issues?.map((issue) => (
                <span key={issue} className="badge badge-warning badge-xs badge-outline">
                  {VERDICT_ISSUES.find((candidate) => candidate.value === issue)?.label ?? issue}
                </span>
              ))}
            </span>
          )}
        </span>
      )}
      {(item.verdict_history?.length ?? 0) > 1 && (
        <details className="w-full text-xs text-base-content/60">
          <summary className="cursor-pointer">
            Review history ({item.verdict_history?.length})
          </summary>
          <ul className="mt-1 space-y-1 pl-4">
            {item.verdict_history?.map((verdict, index) => (
              <li key={`${verdict.username}-${verdict.updated_at}-${index}`}>
                {verdict.username}:{" "}
                {verdict.agree === null ? "cleared" : verdict.agree ? "agree" : "disagree"}
                {verdict.note ? ` — ${verdict.note}` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

/** One evaluation record: its verdict, diagnosis, figure and prompt. */
export function EvaluationCard({
  item,
  showFigure = true,
  showTarget = true,
  showRunLink = false,
}: EvaluationCardProps) {
  const diagnosis = diagnosisOf(item);
  const outcome = diagnosisOutcome(diagnosis);
  const fit = fitAssessment(diagnosis);
  const success = diagnosisSuccess(diagnosis);
  const status = statusLabel(diagnosis);
  const output = item.output;
  const answers = Object.entries(output?.answers ?? {}).filter(([, text]) => text);
  const input = item.input;
  const inputExamples = input?.examples ?? [];
  const figurePath = item.figure_path?.[0];
  const jsonFigurePath = item.json_figure_path?.[0];
  const evaluator = evaluatorLabel(item.evaluator);
  const duration = formatDuration(output?.duration_ms);
  const shortfall = answerShortfall(output);
  const calls = output?.calls ?? [];
  const peak = tokenPeak([output]);
  // The full input loads its figures, so only once someone opens it.
  const [showInput, setShowInput] = useState(false);

  return (
    <article className="rounded-lg border border-base-300 bg-base-100 p-4">
      <div
        className={`grid gap-4 ${showFigure ? "xl:grid-cols-[minmax(0,420px)_minmax(0,1fr)]" : ""}`}
      >
        {showFigure && (
          <div className="rounded-lg border border-base-300 bg-base-200/40 p-3">
            {figurePath ? (
              // White backdrop keeps matplotlib figures legible across themes.
              <div className="flex h-[320px] min-w-0 items-center justify-center overflow-hidden rounded-lg bg-white p-2">
                <TaskFigure path={figurePath} jsonFigurePath={jsonFigurePath} qid={item.qid} fit />
              </div>
            ) : (
              <div className="flex h-[320px] flex-col items-center justify-center gap-2 text-sm text-base-content/50">
                <ImageIcon className="h-8 w-8" />
                No figure
              </div>
            )}
          </div>
        )}

        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusIcon item={item} />
            {showTarget && <span className="font-medium">{item.qid}</span>}
            {showTarget && <span className="text-xs text-base-content/60">{item.task_name}</span>}
            {item.status !== "completed" && (
              <span className="badge badge-ghost badge-sm">{item.status}</span>
            )}
            {outcome && (
              <span
                className={`badge badge-sm ${outcomeBadgeClass(outcome)}`}
                title="Outcome the model classified"
              >
                {outcome}
              </span>
            )}
            {fit && <span className={`badge badge-sm ${fitBadgeClass(fit)}`}>{fitLabel(fit)}</span>}
            {status && (
              <span
                className={`badge badge-sm ${success ? "badge-success" : "badge-warning"}`}
                title="Calibration status the model determined"
              >
                {status}
              </span>
            )}
            {shortfall && (
              <span className="badge badge-sm badge-outline badge-warning" title={shortfall.title}>
                {shortfall.label}
              </span>
            )}
            {output?.fallback && (
              <span className="badge badge-sm badge-warning badge-outline">fallback model</span>
            )}
            {item.planner && <span className="badge badge-sm badge-outline">via Copilot</span>}
            <span className="ml-auto flex items-center gap-1">
              {showRunLink && (
                <Link href={`/evaluations/${item.run_id}`} className="btn btn-ghost btn-xs gap-1">
                  Run
                </Link>
              )}
              <Link href={`/task-results/${item.task_id}`} className="btn btn-ghost btn-xs gap-1">
                <ExternalLink className="h-3.5 w-3.5" />
                Result
              </Link>
            </span>
          </div>

          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-base-content/60">
            {output?.model && <span className="font-mono">{output.model}</span>}
            {duration && <span>{duration}</span>}
            {calls.length > 1 ? (
              <span title="Each model call: how long it took (why it stopped)">
                {calls.length} calls: {calls.map(callLabel).join(" + ")}
              </span>
            ) : (
              output?.attempts !== undefined &&
              output.attempts !== null &&
              output.attempts > 1 && (
                <span title="The first answer was incomplete, so the model was asked once more">
                  {output.attempts} attempts
                </span>
              )
            )}
            {peak && (
              <span
                className={peak.nearLimit ? "font-medium text-warning" : undefined}
                title="Tokens the model counted for its largest call, images included; with the answer, against the judging model's context window"
                data-testid="token-peak"
              >
                {tokenPeakLabel(peak)}
                {peak.nearLimit && " — close to the context limit"}
              </span>
            )}
            {evaluator && <span className="font-mono">{evaluator}</span>}
            {item.completed_at && <span>{formatDateTime(item.completed_at)}</span>}
            {input && (
              <span>
                {input.knowledge_chars
                  ? `reference ${input.knowledge_chars} chars`
                  : input.reference_requested
                    ? "reference requested · none used"
                    : "no reference requested"}
              </span>
            )}
            {input?.examples_requested && (input.examples_used ?? 0) === 0 && (
              <span className="text-warning">examples requested · none used</span>
            )}
            {(input?.examples_used ?? input?.examples?.length ?? 0) > 0 && (
              <span title={inputExamples.map((e) => `${e.title} (${e.outcome})`).join("\n")}>
                {input?.examples_used ?? inputExamples.length} labeled example
                {(input?.examples_used ?? inputExamples.length) === 1 ? "" : "s"} used
              </span>
            )}
          </div>

          {["failed", "interrupted", "cancelled"].includes(item.status) && (
            <div className="alert alert-error py-2 text-sm">
              <XCircle className="h-4 w-4" />
              <span>{item.error || `The evaluation was ${item.status}.`}</span>
            </div>
          )}

          {item.status === "completed" && diagnosis && (
            <div className="grid gap-3 text-sm md:grid-cols-2">
              {DIAGNOSIS_SECTIONS.map(({ key, label }) => {
                const text = diagnosisText(diagnosis, key);
                if (!text) return null;
                return (
                  <div key={key}>
                    <div className="text-xs text-base-content/50">{label}</div>
                    <p className="mt-1 whitespace-pre-wrap text-base-content/80">{text}</p>
                  </div>
                );
              })}
            </div>
          )}

          {item.status === "completed" && output?.raw && (!diagnosis || !output.complete) && (
            <div>
              <div className="text-xs text-base-content/50">
                {diagnosis ? "Answer as returned" : "Answer (not JSON)"}
              </div>
              <p className="mt-1 whitespace-pre-wrap text-sm text-base-content/80">{output.raw}</p>
            </div>
          )}

          {item.status === "completed" && answers.length > 0 && (
            <details className="text-sm">
              <summary className="cursor-pointer font-medium text-primary">
                Answers as returned
                <span className="ml-2 text-xs font-normal text-base-content/60">
                  {answers.length} question{answers.length === 1 ? "" : "s"}
                </span>
              </summary>
              <div className="mt-2 space-y-3 rounded-lg border border-base-300 bg-base-200/40 p-3">
                {answers.map(([key, text]) => (
                  <div key={key}>
                    <div className="text-xs text-base-content/50">
                      {questionLabel(key)}
                      <span className="ml-2 font-mono normal-case text-base-content/40">{key}</span>
                    </div>
                    <p className="mt-1 whitespace-pre-wrap text-base-content/80">{text}</p>
                  </div>
                ))}
              </div>
            </details>
          )}

          {input?.prompt && (
            <details
              className="text-sm"
              onToggle={(event) => setShowInput((event.target as HTMLDetailsElement).open)}
            >
              <summary className="cursor-pointer font-medium text-primary">
                Prompt sent to the model
                <span className="ml-2 text-xs font-normal text-base-content/60">
                  {promptSummary(input)}
                </span>
              </summary>
              {showInput && (
                <ModelInputView
                  input={input}
                  taskName={item.task_name}
                  figurePaths={item.figure_path ?? []}
                  evaluationId={item.evaluation_id}
                />
              )}
            </details>
          )}

          {item.planner && (
            <details className="text-sm">
              <summary className="cursor-pointer font-medium text-primary">
                What Copilot did
              </summary>
              <div className="mt-2 space-y-2 rounded-lg border border-base-300 bg-base-200/40 p-3">
                <div className="flex flex-wrap gap-1 text-xs">
                  <span className="font-mono text-base-content/60">{item.planner.model}</span>
                  {formatDuration(item.planner.duration_ms) && (
                    <span className="text-base-content/60">
                      · {formatDuration(item.planner.duration_ms)}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-1">
                  {(item.planner.tool_calls ?? []).map((name, index) => (
                    <span key={`${name}-${index}`} className="badge badge-ghost badge-sm font-mono">
                      {name}
                    </span>
                  ))}
                </div>
                {item.planner.answer && <MarkdownContent content={item.planner.answer} />}
              </div>
            </details>
          )}

          {item.status === "completed" && <Verdict item={item} />}
        </div>
      </div>
    </article>
  );
}
