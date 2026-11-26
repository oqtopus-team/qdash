"use client";

import Link from "next/link";

import { useEffect, useId, useState } from "react";
import { twMerge } from "tailwind-merge";
import { Ban, Brain, ChevronRight, CircleX, History, Wrench } from "lucide-react";
import { useChatFollowing } from "@/contexts/ChatFollowContext";
import type {
  ChatTrace as ChatTraceData,
  ToolClassification,
  ToolEvaluation,
  TraceStep,
  TurnConnection,
} from "@/types/agentChat";
import { ChatMarkdown } from "@/components/features/chat/ChatMarkdown";
import { FigureStrip, figuresInSteps } from "@/components/features/chat/ChatFigures";
import {
  ToolDetails,
  hasDetails,
  stepPreview,
  stepTitle,
  toolIcon,
} from "@/components/features/chat/ToolStepDetails";
import {
  ExecutionProgress,
  executionIdFromArgs,
  executionPagePath,
} from "@/components/features/chat/ExecutionProgress";
import { ChatLink } from "@/components/features/chat/ChatPreviewLink";
import {
  ChainOfThoughtContent,
  ChainOfThoughtStep,
  ChainOfThoughtTrigger,
} from "@/components/ui/ChainOfThought";
import { Loader } from "@/components/ui/Loader";

export function formatDuration(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

/** Re-render once per second while something is running, for live timers. */
export function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);
  return now;
}

/** Which model judged a plot and, on request, exactly what it was sent. */
function EvaluationPanel({ evaluation }: { evaluation: ToolEvaluation }) {
  return (
    <div className="mt-1.5 text-xs text-base-content/60">
      <div>
        Judged by{" "}
        <span className="font-mono text-base-content/75">
          {evaluation.model ?? "the conversation model"}
        </span>
        {evaluation.fallback && (
          <span className="text-warning/80"> · fallback, no calibration VLM configured</span>
        )}
        {evaluation.runId && (
          <>
            {" · "}
            <Link href={`/evaluations/${evaluation.runId}`} className="link link-hover">
              recorded as an evaluation
            </Link>
          </>
        )}
      </div>
      <details className="mt-1">
        <summary className="cursor-pointer select-none text-base-content/50 hover:text-base-content/80">
          What the model saw
        </summary>
        <pre className="mt-1 max-h-80 overflow-auto whitespace-pre-wrap rounded-md bg-base-200/60 p-2 font-mono text-xs leading-relaxed text-base-content/70">
          {evaluation.prompt}
        </pre>
      </details>
    </div>
  );
}

const OUTCOME_BADGE: Record<ToolClassification["outcome"], { label: string; className: string }> = {
  classified: { label: "Classified", className: "badge-success" },
  ambiguous: { label: "Unclear", className: "badge-warning" },
  failed: { label: "No answer", className: "badge-error" },
};

const percent = (value: number) => `${Math.round(value * 100)}%`;

/** What the classifier answered, which model it was, and on request every category's share. */
function ClassificationPanel({ classification }: { classification: ToolClassification }) {
  const badge = OUTCOME_BADGE[classification.outcome];
  const { category, probability, margin, probabilities, reason } = classification;
  return (
    <div className="mt-1.5 text-xs text-base-content/60" data-testid="classification-panel">
      <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
        <span className={`badge badge-soft badge-xs ${badge.className}`}>{badge.label}</span>
        {/* A clear answer names its category in the row title; an unclear one only here. */}
        {category && classification.outcome === "ambiguous" && (
          <span>
            leaning <span className="font-mono text-base-content/80">{category}</span>
          </span>
        )}
        {probability !== undefined && (
          <span className="tabular-nums">
            {percent(probability)}
            {margin !== undefined && <>, lead {percent(margin)}</>}
          </span>
        )}
        <span>
          · by <span className="font-mono text-base-content/75">{classification.classifier}</span>
        </span>
      </div>
      {classification.outcome === "failed" && reason && (
        <p className="mt-0.5 text-base-content/55">The classifier gave no answer: {reason}.</p>
      )}
      {probabilities && probabilities.length > 1 && (
        <details className="mt-1">
          <summary className="cursor-pointer select-none text-base-content/50 hover:text-base-content/80">
            All categories
          </summary>
          <ul className="mt-1 space-y-0.5">
            {probabilities.map((entry) => (
              <li
                key={entry.category}
                className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)_3rem] items-center gap-2"
              >
                <span className="truncate font-mono text-base-content/70">{entry.category}</span>
                <progress
                  className="progress progress-neutral h-1.5"
                  value={Math.round(entry.probability * 100)}
                  max={100}
                  aria-label={`${entry.category} probability`}
                />
                <span className="text-right tabular-nums">{percent(entry.probability)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

type ToolStep = Extract<TraceStep, { kind: "tool" }>;

/** A tool call's state in words, so it never rests on the marker's color alone. */
const TOOL_STATUS_LABEL: Record<ToolStep["status"], string> = {
  drafting: "Preparing",
  running: "Running",
  done: "Done",
  error: "Failed",
  cancelled: "Not run",
};

/** The last line a failed call printed, to keep the failure readable while its row is folded. */
function failureLine(step: ToolStep): string | null {
  const failed = step.status === "error" || (step.exitCode !== undefined && step.exitCode !== 0);
  if (!failed || !step.output) return null;
  const lines = step.output.split("\n").filter((line) => line.trim());
  const last = lines[lines.length - 1]?.trim();
  if (!last) return null;
  return last.length > 160 ? `${last.slice(0, 160)}…` : last;
}

/** The execution a wait call is about, or null for any other tool. */
function waitedExecution(step: ToolStep): string | null {
  return step.tool === "qdash_wait_execution" ? executionIdFromArgs(step.args) : null;
}

/** Lines up content under a row's title, past its inline icon. */
const ROW_INDENT = "pl-5.5";

/** A row's chevron: shown on hover or focus, and kept while the row is open. */
function RowChevron({ open }: { open: boolean }) {
  return (
    <ChevronRight
      className={`w-3 h-3 shrink-0 text-base-content/40 transition-[transform,opacity] ${
        open
          ? "rotate-90 opacity-100"
          : "opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100"
      }`}
      aria-hidden="true"
    />
  );
}

function ToolStepRow({
  step,
  now,
  extrasOutside = false,
}: {
  step: ToolStep;
  now: number;
  /** The row sits in a folded group, which shows its failure, execution and figures instead. */
  extrasOutside?: boolean;
}) {
  const title = stepTitle(step);
  const preview = stepPreview(step);
  const elapsed = (step.endedAt ?? now) - step.startedAt;
  const details = hasDetails(step);
  const drafting = step.status === "drafting";
  const running = step.status === "running";
  const failed = step.status === "error";
  const cancelled = step.status === "cancelled";
  // Every row starts folded, live or not; code and output open only on request.
  // The row's key is its position, so the user's choice survives the draft
  // becoming a running call and that call finishing.
  const [userOpen, setUserOpen] = useState(false);
  const open = details && userOpen;
  const failure = open || extrasOutside ? null : failureLine(step);
  // While the assistant waits on an execution, show its tasks and figures as they land.
  const waitingOn = extrasOutside ? null : waitedExecution(step);
  // One icon per row: what the tool is, or that it failed or never ran.
  const Icon = failed ? CircleX : cancelled ? Ban : toolIcon(step.tool);

  return (
    <ChainOfThoughtStep variant="plain" open={open} onOpenChange={setUserOpen}>
      <ChainOfThoughtTrigger
        hideChevron
        disabled={!details}
        className={`group min-w-0 gap-2 text-sm ${details ? "" : "cursor-default"}`}
        title={title}
        data-status={step.status}
      >
        <Icon
          className={`w-3.5 h-3.5 shrink-0 ${failed ? "text-error" : "text-base-content/45"}`}
          strokeWidth={1.75}
          aria-hidden="true"
        />
        <span
          className={`min-w-0 truncate ${
            running || drafting
              ? "loader-text-shimmer"
              : cancelled
                ? "text-base-content/45"
                : "text-base-content/65 group-hover:text-base-content/85"
          }`}
        >
          {title}
        </span>
        {/* Status and time sit beside the title, not at the far edge of the row. */}
        <span
          className="flex shrink-0 items-center gap-1.5 text-xs tabular-nums text-base-content/40"
          data-testid="tool-step-meta"
        >
          {failed ? (
            <span className="text-error">Failed</span>
          ) : cancelled ? (
            <span>Not run</span>
          ) : (
            <span className="sr-only">{TOOL_STATUS_LABEL[step.status]}</span>
          )}
          {!drafting && !cancelled && <span>{formatDuration(elapsed)}</span>}
        </span>
        {preview && (
          <span className="min-w-0 flex-[1_1_0%] truncate text-xs text-base-content/40">
            {preview}
          </span>
        )}
        {details && <RowChevron open={open} />}
      </ChainOfThoughtTrigger>
      {failure && (
        <p
          className={`${ROW_INDENT} mt-0.5 truncate font-mono text-xs text-error`}
          title={failure}
          data-testid="tool-failure-line"
        >
          {failure}
        </p>
      )}
      {waitingOn && running && (
        <div className={ROW_INDENT}>
          <ExecutionProgress executionId={waitingOn} />
        </div>
      )}
      {waitingOn && (failed || step.status === "done") && (
        // Once the wait ends the live card goes; the execution stays one click away.
        <p className={`${ROW_INDENT} mt-0.5 text-xs`}>
          <ChatLink
            href={executionPagePath(waitingOn)}
            className="link link-hover text-base-content/60 hover:text-base-content"
          >
            View execution {waitingOn}
          </ChatLink>
        </p>
      )}
      {!extrasOutside && step.figures && step.figures.length > 0 && (
        <FigureStrip paths={step.figures} compact className={`${ROW_INDENT} mt-1.5`} />
      )}
      {(step.evaluation || step.classification) && (
        <div className={ROW_INDENT}>
          {step.evaluation && <EvaluationPanel evaluation={step.evaluation} />}
          {step.classification && <ClassificationPanel classification={step.classification} />}
        </div>
      )}
      {details && (
        <ChainOfThoughtContent className={ROW_INDENT} contentClassName="pt-0.5 pb-1">
          <ToolDetails step={step} />
        </ChainOfThoughtContent>
      )}
    </ChainOfThoughtStep>
  );
}

function ThinkingStepRow({
  step,
  now,
  live,
}: {
  step: Extract<TraceStep, { kind: "thinking" }>;
  now: number;
  live: boolean;
}) {
  const active = live && step.endedAt === undefined;
  const elapsed = (step.endedAt ?? now) - step.startedAt;
  const [open, setOpen] = useState(false);
  const hasText = Boolean(step.text);

  return (
    // Folded like a tool row; the thought itself is one click away.
    <ChainOfThoughtStep variant="plain" open={hasText && open} onOpenChange={setOpen}>
      <ChainOfThoughtTrigger
        hideChevron
        disabled={!hasText}
        className={`group min-w-0 gap-2 text-sm ${hasText ? "" : "cursor-default"}`}
      >
        <Brain
          className="w-3.5 h-3.5 shrink-0 text-base-content/45"
          strokeWidth={1.75}
          aria-hidden="true"
        />
        {active ? (
          <span className="loader-text-shimmer">Thinking</span>
        ) : (
          <span className="text-base-content/65 group-hover:text-base-content/85">
            Thought for {formatDuration(elapsed)}
          </span>
        )}
        {hasText && <RowChevron open={open} />}
      </ChainOfThoughtTrigger>
      {hasText && (
        <ChainOfThoughtContent className={ROW_INDENT}>
          <div className="chat-thinking-text">{active ? step.text.slice(-1200) : step.text}</div>
        </ChainOfThoughtContent>
      )}
    </ChainOfThoughtStep>
  );
}

function isTool(step: TraceStep): step is ToolStep {
  return step.kind === "tool";
}

type WorkStep = Exclude<TraceStep, { kind: "text" }>;

/** A run of work steps between two pieces of prose, or one piece of prose. */
type TraceSegment =
  | { kind: "text"; index: number; step: Extract<TraceStep, { kind: "text" }> }
  | { kind: "work"; start: number; steps: WorkStep[] };

/**
 * Splits a trace at its prose: each maximal run of tool and thinking steps
 * becomes one work segment, keyed by where it starts. Steps are append-only
 * within a turn, so a segment keeps its key as new calls join it.
 */
export function groupTraceSteps(steps: TraceStep[]): TraceSegment[] {
  const segments: TraceSegment[] = [];
  let run: Extract<TraceSegment, { kind: "work" }> | null = null;
  for (let index = 0; index < steps.length; index++) {
    const step = steps[index];
    if (step.kind === "text") {
      run = null;
      segments.push({ kind: "text", index, step });
    } else if (run) {
      run.steps.push(step);
    } else {
      run = { kind: "work", start: index, steps: [step] };
      segments.push(run);
    }
  }
  return segments;
}

/** A run with this many tool calls folds into one summary row. */
const GROUP_MIN_TOOLS = 2;

function isStepActive(step: TraceStep): boolean {
  if (step.kind === "tool") return step.status === "drafting" || step.status === "running";
  return step.kind === "thinking" && step.endedAt === undefined;
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** What a folded group would hide but must not: failures, executions and, live, figures. */
function FoldedGroupNotes({ steps, showFigures }: { steps: ToolStep[]; showFigures: boolean }) {
  const failures = steps.filter((s) => s.status === "error");
  const waits = steps
    .map((step) => ({ step, executionId: waitedExecution(step) }))
    .filter((w): w is { step: ToolStep; executionId: string } => w.executionId !== null);
  const figures = showFigures ? figuresInSteps(steps) : [];
  if (failures.length === 0 && waits.length === 0 && figures.length === 0) return null;
  return (
    <div className={`${ROW_INDENT} flex min-w-0 flex-col gap-1`}>
      {failures.map((step, i) => {
        const line = failureLine(step);
        return (
          <p
            key={`failure-${i}`}
            className="flex min-w-0 items-center gap-1.5 text-xs"
            data-testid="tool-group-failure"
          >
            <CircleX className="w-3 h-3 shrink-0 text-error" aria-hidden="true" />
            <span className="shrink-0 text-base-content/70">{stepTitle(step)}</span>
            <span className="sr-only">failed</span>
            {line && (
              <span className="min-w-0 truncate font-mono text-error" title={line}>
                {line}
              </span>
            )}
          </p>
        );
      })}
      {waits.map(({ step, executionId }, i) =>
        step.status === "running" ? (
          <ExecutionProgress key={`wait-${i}`} executionId={executionId} />
        ) : step.status === "done" || step.status === "error" ? (
          <p key={`wait-${i}`} className="text-xs">
            <ChatLink
              href={executionPagePath(executionId)}
              className="link link-hover text-base-content/60 hover:text-base-content"
            >
              View execution {executionId}
            </ChatLink>
          </p>
        ) : null,
      )}
      {figures.length > 0 && <FigureStrip paths={figures} compact />}
    </div>
  );
}

/**
 * One run of work steps. Fewer than two tool calls show as their own rows;
 * from the second call on, the run folds into a summary that names what it is
 * doing and how many calls it made, and opens to the same rows. The rows stay
 * mounted at the same place in the tree either way, so a row the user opened
 * keeps its state as the run grows into a group.
 */
function WorkGroup({
  steps,
  start,
  now,
  live,
  figuresOutside,
}: {
  steps: WorkStep[];
  start: number;
  now: number;
  live: boolean;
  /** The message already shows the turn's figures, so a folded group need not. */
  figuresOutside: boolean;
}) {
  const contentId = useId();
  const [userOpen, setUserOpen] = useState(false);
  const tools = steps.filter(isTool);
  const grouped = tools.length >= GROUP_MIN_TOOLS;
  const folded = grouped && !userOpen;
  const active = live && steps.some(isStepActive);
  const failed = tools.filter((s) => s.status === "error").length;
  const notRun = tools.filter((s) => s.status === "cancelled").length;
  const startedAt = Math.min(...steps.map((s) => s.startedAt));
  const endedAt = active ? now : Math.max(...steps.map((s) => s.endedAt ?? now));
  const label = active
    ? (currentActivity(steps, null) ?? "Working")
    : `Used ${plural(tools.length, "tool")}`;

  return (
    <div className="min-w-0" data-testid="trace-work" data-grouped={grouped}>
      {grouped && (
        <button
          type="button"
          onClick={() => setUserOpen(!userOpen)}
          aria-expanded={!folded}
          aria-controls={contentId}
          className="group flex w-full min-w-0 cursor-pointer items-center gap-2 text-left text-sm"
          data-testid="tool-group-summary"
          data-active={active}
        >
          <Wrench
            className="w-3.5 h-3.5 shrink-0 text-base-content/45"
            strokeWidth={1.75}
            aria-hidden="true"
          />
          <span
            className={`min-w-0 truncate ${
              active
                ? "loader-text-shimmer"
                : "text-base-content/65 group-hover:text-base-content/85"
            }`}
          >
            {label}
          </span>
          <span
            className="shrink-0 text-xs tabular-nums text-base-content/40"
            aria-hidden="true"
            data-testid="tool-group-duration"
          >
            {formatDuration(endedAt - startedAt)}
          </span>
          {active && (
            <span className="shrink-0 text-xs text-base-content/40">
              · {plural(tools.length, "tool")}
            </span>
          )}
          {failed > 0 && (
            <span className="inline-flex shrink-0 items-center gap-1 text-xs text-error">
              · <CircleX className="w-3 h-3" aria-hidden="true" />
              {failed} failed
            </span>
          )}
          {notRun > 0 && (
            <span className="shrink-0 text-xs text-base-content/40">· {notRun} not run</span>
          )}
          <RowChevron open={!folded} />
        </button>
      )}
      {folded && <FoldedGroupNotes steps={tools} showFigures={live && !figuresOutside} />}
      {/* Hidden, not unmounted, while folded: rows keep what the user opened. */}
      <ol
        id={contentId}
        hidden={folded}
        className={`flex flex-col gap-2 ${grouped ? `${ROW_INDENT} mt-2` : ""}`}
      >
        {steps.map((step, j) => (
          <li key={`${step.kind}-${start + j}`} className="min-w-0">
            {step.kind === "tool" ? (
              // A draft's ID can change when execution starts; the position cannot.
              <ToolStepRow step={step} now={now} extrasOutside={folded} />
            ) : (
              <ThinkingStepRow step={step} now={now} live={live} />
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function TraceSteps({
  steps,
  live,
  figuresOutside,
}: {
  steps: TraceStep[];
  live: boolean;
  figuresOutside: boolean;
}) {
  const running = live && steps.some((s) => s.kind === "thinking" || s.kind === "tool");
  const now = useNow(running);
  return (
    <ol className="flex flex-col gap-2">
      {groupTraceSteps(steps).map((segment) =>
        segment.kind === "work" ? (
          <li key={`work-${segment.start}`} className="min-w-0">
            <WorkGroup
              steps={segment.steps}
              start={segment.start}
              now={now}
              live={live}
              figuresOutside={figuresOutside}
            />
          </li>
        ) : (
          // Prose between calls stays outside every group.
          <li key={`text-${segment.index}`} className="min-w-0">
            <ChatMarkdown
              className="text-sm text-base-content/70"
              streaming={live && segment.index === steps.length - 1}
            >
              {segment.step.text}
            </ChatMarkdown>
          </li>
        ),
      )}
    </ol>
  );
}

/** The one-line summary of a finished answer's work: how long it took and what it did. */
function workHistoryLabel(trace: ChatTraceData): { title: string; details: string[] } {
  const updates = trace.steps.filter((s) => s.kind === "text" && s.text.trim()).length;
  const tools = trace.steps.filter(isTool);
  const failed = tools.filter((s) => s.status === "error").length;
  const details = [
    ...(updates ? [plural(updates, "update")] : []),
    ...(tools.length ? [plural(tools.length, "tool")] : []),
    ...(failed ? [`${failed} failed`] : []),
  ];
  const title =
    trace.durationMs > 0 ? `Worked for ${formatDuration(trace.durationMs)}` : "Work history";
  return { title, details };
}

/**
 * The work before a finished answer: its progress updates, and its calls folded
 * into the same groups the live turn showed.
 *
 * `foldable`: the answer has its own text, so the work is history behind it. It
 * folds into one row (folded at first) that names how long the work took and
 * what it did, and opens to the same steps. Failures and executions stay
 * visible while it is folded. Without it (an answer that is only a question, an
 * approval, a partial answer that never ended, or nothing yet), the work is
 * shown as it streamed, since its updates may be all the text there is.
 *
 * `finishedHere`: the answer of a turn this view streamed, now ended. If it ends
 * while the user reads away from the bottom, the work stays as it streamed, so
 * what they read neither moves nor hides; it folds once the thread follows the
 * bottom again.
 */
export function ChatTraceSummary({
  trace,
  foldable = false,
  finishedHere = false,
}: {
  trace: ChatTraceData;
  foldable?: boolean;
  finishedHere?: boolean;
}) {
  const contentId = useId();
  const [open, setOpen] = useState(false);
  const following = useChatFollowing();
  const [held, setHeld] = useState(() => finishedHere && !following);
  useEffect(() => {
    if (held && following) setHeld(false);
  }, [held, following]);
  if (trace.steps.length === 0) return null;
  if (!foldable || held) {
    return (
      <div className="mb-3">
        <TraceSteps steps={trace.steps} live={false} figuresOutside />
      </div>
    );
  }
  const { title, details } = workHistoryLabel(trace);
  return (
    <div className="mb-3 min-w-0" data-testid="work-history">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={contentId}
        className="group flex w-full min-w-0 cursor-pointer items-center gap-2 text-left text-sm"
        data-testid="work-history-summary"
      >
        <History
          className="w-3.5 h-3.5 shrink-0 text-base-content/45"
          strokeWidth={1.75}
          aria-hidden="true"
        />
        <span className="min-w-0 truncate text-base-content/65 group-hover:text-base-content/85">
          {title}
        </span>
        {details.length > 0 && (
          <span className="shrink-0 text-xs tabular-nums text-base-content/40">
            · {details.join(" · ")}
          </span>
        )}
        <ChevronRight
          className={`w-3 h-3 shrink-0 text-base-content/40 transition-transform ${
            open ? "rotate-90" : ""
          }`}
          aria-hidden="true"
        />
      </button>
      {!open && <FoldedGroupNotes steps={trace.steps.filter(isTool)} showFigures={false} />}
      {/* Hidden, not unmounted, while folded: rows keep what the user opened. */}
      <div id={contentId} hidden={!open} className={`${ROW_INDENT} mt-2`}>
        <TraceSteps steps={trace.steps} live={false} figuresOutside />
      </div>
    </div>
  );
}

/** Steps of the turn that is still streaming. */
export function LiveTrace({
  steps,
  figuresOutside = false,
}: {
  steps: TraceStep[];
  /** The message already shows the turn's figures above its answer. */
  figuresOutside?: boolean;
}) {
  if (steps.length === 0) return null;
  return (
    <div className="mb-3">
      <TraceSteps steps={steps} live figuresOutside={figuresOutside} />
    </div>
  );
}

/** What an active tool call is doing, phrased as an ongoing activity. */
function toolActivity(step: ToolStep): string {
  const title = stepTitle(step);
  // Tools without a phrased title fall back to their label, which names no action.
  return title === step.label ? `Running ${step.label}` : title;
}

function activeTools(steps: TraceStep[]): ToolStep[] {
  return steps.filter(
    (s): s is ToolStep => s.kind === "tool" && (s.status === "drafting" || s.status === "running"),
  );
}

function isThinking(steps: TraceStep[]): boolean {
  return steps.some((s) => s.kind === "thinking" && s.endedAt === undefined);
}

/**
 * The one thing the streaming turn is doing now, read from its steps: a call
 * being written or run, a thought, or the answer. Between events it is what the
 * server last said it was doing, or null when it has said nothing.
 */
export function currentActivity(steps: TraceStep[], statusMessage: string | null): string | null {
  const active = activeTools(steps);
  if (active.length > 1) {
    const running = active.filter((s) => s.status === "running").length;
    return running > 1 ? `Running ${running} tools` : toolActivity(active[active.length - 1]);
  }
  if (active.length === 1) return toolActivity(active[0]);
  if (isThinking(steps)) return "Thinking";
  const last = steps[steps.length - 1];
  if (last?.kind === "text" && last.text) return "Writing the answer";
  return statusMessage;
}

/** How long a turn may send nothing before the footer says when it last did. */
export const QUIET_AFTER_MS = 30_000;

/**
 * What the footer says about the turn's connection, apart from what the turn
 * does: that it is reconnecting, or, once the turn has sent nothing for a while,
 * that the connection is fine and when the last update came. Null while updates
 * arrive, so a busy turn shows nothing extra. Silence is never shown as progress.
 */
export function connectionNote(
  connection: TurnConnection | null | undefined,
  now: number,
): { lost: boolean; text: string } | null {
  if (!connection) return null;
  const silent = now - connection.lastUpdateAt;
  const last = `last update ${formatDuration(silent)} ago`;
  if (connection.state === "reconnecting") {
    return { lost: true, text: `Connection lost, reconnecting · ${last}` };
  }
  return silent >= QUIET_AFTER_MS ? { lost: false, text: `Connected · ${last}` } : null;
}

/** Whether a row of the live trace already shows what the turn is doing. */
function activityShownInTrace(steps: TraceStep[]): boolean {
  return activeTools(steps).length > 0 || isThinking(steps);
}

/**
 * The streaming turn's footer: what it is doing now and for how long. When a
 * trace row already shows the activity, the footer is not drawn again but its
 * status region stays mounted and screen-reader only, so the change is still
 * announced. The ticking timer stays out of the live region.
 */
export function TurnActivity({
  steps,
  startedAt,
  statusMessage,
  connection,
  className,
}: {
  steps: TraceStep[];
  startedAt: number;
  statusMessage: string | null;
  /** The stream's health; its note shows even when a trace row shows the activity. */
  connection?: TurnConnection | null;
  className?: string;
}) {
  const now = useNow(true);
  const note = connectionNote(connection, now);
  // While reconnecting, what the turn does is unknown: the last activity is not repeated.
  const activity = note?.lost ? null : currentActivity(steps, statusMessage);
  const inTrace = activityShownInTrace(steps);
  return (
    <div
      className={
        inTrace && !note
          ? "sr-only"
          : twMerge("flex min-w-0 items-center gap-2 text-xs text-base-content/50", className)
      }
      data-testid="turn-activity"
      data-in-trace={inTrace}
    >
      {!inTrace && !note?.lost && (
        <div role="status" className="flex min-w-0 items-center">
          {activity ? (
            <Loader variant="text-shimmer" size="sm" text={activity} className="truncate" />
          ) : (
            <Loader variant="typing" size="sm" />
          )}
        </div>
      )}
      {inTrace && !note?.lost && (
        <div role="status" className="sr-only">
          {activity}
        </div>
      )}
      {!inTrace && !note && (
        <span className="shrink-0 tabular-nums" aria-hidden="true">
          {formatDuration(now - startedAt)}
        </span>
      )}
      {/* Announced once when the connection drops; the ticking time is not. */}
      {note?.lost && (
        <div role="status" className="sr-only">
          Connection lost, reconnecting
        </div>
      )}
      {note && (
        <span
          className={`flex min-w-0 items-center gap-1.5 ${note.lost ? "text-warning" : ""}`}
          data-testid="turn-connection"
          data-state={connection?.state}
          aria-hidden="true"
        >
          <span
            className={`status status-xs shrink-0 ${note.lost ? "status-warning" : "status-neutral"}`}
            aria-hidden="true"
          />
          <span className="truncate tabular-nums">{note.text}</span>
        </span>
      )}
    </div>
  );
}
