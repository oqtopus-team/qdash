"use client";

import Link from "next/link";

import { useEffect, useId, useState } from "react";
import { twMerge } from "tailwind-merge";
import { Ban, Brain, ChevronRight, CircleX, Wrench } from "lucide-react";
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
import { ActivityLogo, type ActivityLogoMode } from "@/components/features/chat/ActivityLogo";

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

/**
 * Holds a live row's place where its icon goes. The turn's footer is its one live mark,
 * so an active row draws no icon of its own; the gap keeps its title where the icon
 * will stand once the step ends.
 */
function IconSlot() {
  return <span className="w-3.5 h-3.5 shrink-0" aria-hidden="true" data-testid="icon-slot" />;
}

function ToolStepRow({
  step,
  now,
  live,
  named = false,
  extrasOutside = false,
}: {
  step: ToolStep;
  now: number;
  /** The turn is streaming: its footer shows what an active call is doing. */
  live: boolean;
  /** The footer names this call beside the live mark, so the row does not repeat it. */
  named?: boolean;
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
  // A call in flight is plain text: the footer's mark is the one live sign.
  const active = live && (running || drafting);
  // One icon per settled row: what the tool is, or that it failed or never ran.
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
        {active ? (
          <IconSlot />
        ) : (
          <Icon
            className={`w-3.5 h-3.5 shrink-0 ${failed ? "text-error" : "text-base-content/45"}`}
            strokeWidth={1.75}
            aria-hidden="true"
          />
        )}
        {named ? (
          // The footer shows this title and its time; the row only opens what the call
          // is doing. Its name stays for assistive tech, which reads rows out of order.
          <>
            <span className="sr-only">{title}</span>
            {!preview && (
              <span className="text-xs text-base-content/50 group-hover:text-base-content/80">
                Details
              </span>
            )}
          </>
        ) : (
          <span
            className={`min-w-0 truncate ${
              cancelled
                ? "text-base-content/45"
                : "text-base-content/65 group-hover:text-base-content/85"
            }`}
          >
            {title}
          </span>
        )}
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
          {!drafting && !cancelled && !named && <span>{formatDuration(elapsed)}</span>}
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
  // A live thought is announced by the footer ("Thinking" beside the mark); its row
  // only offers the text so far (see `rowless`), with no live heading of its own.

  return (
    // Folded like a tool row; the thought itself is one click away.
    <ChainOfThoughtStep variant="plain" open={hasText && open} onOpenChange={setOpen}>
      <ChainOfThoughtTrigger
        hideChevron
        disabled={!hasText}
        className={`group min-w-0 gap-2 text-sm ${hasText ? "" : "cursor-default"}`}
      >
        {active ? (
          <IconSlot />
        ) : (
          <Brain
            className="w-3.5 h-3.5 shrink-0 text-base-content/45"
            strokeWidth={1.75}
            aria-hidden="true"
          />
        )}
        {active ? (
          <span className="text-base-content/65 group-hover:text-base-content/85">
            Thought so far
          </span>
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

/**
 * Whether a live step has no row: the footer already says what it is doing, and the
 * row would only repeat it. A thought with no text yet, or the call the footer names
 * when it has no details, preview or execution to show.
 */
function rowless(step: TraceStep, live: boolean, named: ToolStep | null): boolean {
  if (!live) return false;
  if (step.kind === "thinking") return step.endedAt === undefined && !step.text;
  // The call the footer names, with nothing more to show than its name.
  return (
    step === named &&
    !hasDetails(step) &&
    !stepPreview(step) &&
    !waitedExecution(step) &&
    !step.figures?.length &&
    !step.evaluation &&
    !step.classification
  );
}

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
 * from the second call on, the run folds into a summary that counts its calls
 * (settled, it says it used them), and opens to the same rows. The rows stay
 * mounted at the same place in the tree either way, so a row the user opened
 * keeps its state as the run grows into a group.
 */
function WorkGroup({
  steps,
  start,
  now,
  live,
  named,
  figuresOutside,
}: {
  steps: WorkStep[];
  start: number;
  now: number;
  live: boolean;
  /** The call the live footer names, if any. */
  named: ToolStep | null;
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
  // Live, the footer says what the run does; the summary only counts its calls.
  const label = active ? plural(tools.length, "tool call") : `Used ${plural(tools.length, "tool")}`;

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
          {active ? (
            <IconSlot />
          ) : (
            <Wrench
              className="w-3.5 h-3.5 shrink-0 text-base-content/45"
              strokeWidth={1.75}
              aria-hidden="true"
            />
          )}
          <span className="min-w-0 truncate text-base-content/65 group-hover:text-base-content/85">
            {label}
          </span>
          <span
            className="shrink-0 text-xs tabular-nums text-base-content/40"
            aria-hidden="true"
            data-testid="tool-group-duration"
          >
            {formatDuration(endedAt - startedAt)}
          </span>
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
        {steps.map((step, j) =>
          rowless(step, live, named) ? null : (
            <li key={`${step.kind}-${start + j}`} className="min-w-0">
              {step.kind === "tool" ? (
                // A draft's ID can change when execution starts; the position cannot.
                <ToolStepRow
                  step={step}
                  now={now}
                  live={live}
                  named={step === named}
                  extrasOutside={folded}
                />
              ) : (
                <ThinkingStepRow step={step} now={now} live={live} />
              )}
            </li>
          ),
        )}
      </ol>
    </div>
  );
}

function TraceSteps({
  steps,
  live,
  named = null,
  figuresOutside,
}: {
  steps: TraceStep[];
  live: boolean;
  named?: ToolStep | null;
  figuresOutside: boolean;
}) {
  const running = live && steps.some((s) => s.kind === "thinking" || s.kind === "tool");
  const now = useNow(running);
  return (
    <ol className="flex flex-col gap-2">
      {groupTraceSteps(steps).map((segment) =>
        segment.kind === "work" ? (
          segment.steps.every((step) => rowless(step, live, named)) ? null : (
            <li key={`work-${segment.start}`} className="min-w-0">
              <WorkGroup
                steps={segment.steps}
                start={segment.start}
                now={now}
                live={live}
                named={named}
                figuresOutside={figuresOutside}
              />
            </li>
          )
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

/**
 * The work before a finished answer: its prose, and its calls folded into the
 * same groups the live turn showed, so nothing jumps when the turn ends.
 */
export function ChatTraceSummary({ trace }: { trace: ChatTraceData }) {
  if (trace.steps.length === 0) return null;
  return (
    <div className="mb-3">
      <TraceSteps steps={trace.steps} live={false} figuresOutside />
    </div>
  );
}

/** Steps of the turn that is still streaming. */
export function LiveTrace({
  steps,
  figuresOutside = false,
  activityInFooter = true,
}: {
  steps: TraceStep[];
  /** The message already shows the turn's figures above its answer. */
  figuresOutside?: boolean;
  /**
   * The footer names what the turn does. False while the connection is lost: the
   * footer then shows only the warning, so the running call keeps its own title.
   */
  activityInFooter?: boolean;
}) {
  const named = activityInFooter ? namedTool(steps) : null;
  if (steps.every((step) => rowless(step, true, named))) return null;
  return (
    <div className="mb-3">
      <TraceSteps steps={steps} live named={named} figuresOutside={figuresOutside} />
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

/**
 * The one call the footer names: the only call in flight, or the last one when the
 * others are still being written. Null when none is, or when several run at once
 * and the footer counts them instead.
 */
function namedTool(steps: TraceStep[]): ToolStep | null {
  const active = activeTools(steps);
  if (active.length === 0) return null;
  if (active.length > 1 && active.filter((s) => s.status === "running").length > 1) return null;
  return active[active.length - 1];
}

function isThinking(steps: TraceStep[]): boolean {
  return steps.some((s) => s.kind === "thinking" && s.endedAt === undefined);
}

/** What the trace calls a thought, and what the turn is shown doing while the model thinks. */
const THINKING_LABEL = "Thinking";

/**
 * The server's generic status while the model works out its next output, for
 * example right after a tool result. It is not a thought event (those arrive
 * as thinking steps), but it means the same to the user, so it reads the same.
 */
const SERVER_THINKING_STATUS = "AI is thinking...";

/** A server status as the chat shows it: its generic thinking note as "Thinking", the rest as sent. */
export function displayStatusMessage(statusMessage: string | null): string | null {
  return statusMessage?.trim() === SERVER_THINKING_STATUS ? THINKING_LABEL : statusMessage;
}

/**
 * The one thing the streaming turn is doing now, read from its steps: a call
 * being written or run, a thought, or the answer. Between events it is what the
 * server last said it was doing, or null when it has said nothing.
 */
export function currentActivity(steps: TraceStep[], statusMessage: string | null): string | null {
  const named = namedTool(steps);
  if (named) return toolActivity(named);
  const running = activeTools(steps).filter((s) => s.status === "running").length;
  if (running > 1) return `Running ${running} tools`;
  if (isThinking(steps)) return THINKING_LABEL;
  const last = steps[steps.length - 1];
  if (last?.kind === "text" && last.text) return "Writing the answer";
  return displayStatusMessage(statusMessage);
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

/** Search tools, by exact name: the searching mark is never guessed from a label. */
const SEARCH_TOOLS: ReadonlySet<string> = new Set(["qdash_search_source"]);

/** Tools that park the turn on a person's answer rather than on work. */
const HUMAN_WAIT_TOOLS: ReadonlySet<string> = new Set(["qdash_wait_agent_intervention"]);

/**
 * The live mark for one call: searching for a search tool, waiting while a
 * person's answer is awaited, working for everything else. A call still being
 * written is working whatever the tool is.
 */
export function toolLogoMode(step: Pick<ToolStep, "tool" | "status">): ActivityLogoMode {
  if (step.status !== "running") return "working";
  if (SEARCH_TOOLS.has(step.tool)) return "searching";
  if (HUMAN_WAIT_TOOLS.has(step.tool)) return "waiting";
  return "working";
}

/** The live mark for calls in flight together: their shared mode, or working for a mix. */
export function activeToolsMode(steps: ToolStep[]): ActivityLogoMode {
  const modes = new Set(steps.map(toolLogoMode));
  return modes.size === 1 ? [...modes][0] : "working";
}

/** The footer's mark for the turn's steps: the mode of its calls in flight, else thinking. */
function liveMode(steps: TraceStep[]): ActivityLogoMode {
  const tools = activeTools(steps);
  return tools.length > 0 ? activeToolsMode(tools) : "thinking";
}

/**
 * How long a new mode, or the generic "Thinking" label, must last before the
 * footer shows it. A turn hops between calls and the server's "thinking" note in
 * well under a second; held this long, those hops do not flash the mark or label.
 */
export const STEADY_PHASE_MS = 600;

/**
 * `next` once it has held `STEADY_PHASE_MS`, dropped if it changes first. An
 * `immediate` value, the first value and null show at once.
 */
function useSteady<T>(next: T | null, key: string, immediate: boolean): T | null {
  const [shown, setShown] = useState<{ key: string; value: T | null }>({ key, value: next });
  const now = immediate || next === null || shown.value === null;
  useEffect(() => {
    if (key === shown.key) return;
    if (now) {
      setShown({ key, value: next });
      return;
    }
    const id = setTimeout(() => setShown({ key, value: next }), STEADY_PHASE_MS);
    return () => clearTimeout(id);
    // `next` is described by its key; a new value with the same key changes nothing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, shown.key, now]);
  return now ? next : shown.value;
}

/**
 * The streaming turn's footer: the turn's one live presentation. In a fixed slot
 * under the turn it shows the animated mark beside what the turn is doing and how
 * long it has run, for the whole turn. Trace rows stay text while active and take
 * their static icons once they end, so no row repeats the live status.
 *
 * The label names the actual call as soon as it starts, a person's wait at once,
 * and a lost connection replaces it at once; the generic "Thinking" between calls
 * and the mark's mode change only once they have held (see `useSteady`), so short
 * hops neither flash nor re-announce. The ticking timer stays out of the live region.
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
  /** The stream's health; its note shows beside the activity. */
  connection?: TurnConnection | null;
  className?: string;
}) {
  const now = useNow(true);
  const note = connectionNote(connection, now);
  // While reconnecting, what the turn does is unknown: neither mark nor activity is repeated.
  const lost = note?.lost ?? false;
  const nextMode = lost ? null : liveMode(steps);
  const mode = useSteady(nextMode, nextMode ?? "none", nextMode === "waiting");
  const nextLabel = lost ? null : (currentActivity(steps, statusMessage) ?? THINKING_LABEL);
  const label = useSteady(nextLabel, nextLabel ?? "none", nextLabel !== THINKING_LABEL);
  return (
    <div
      className={twMerge("flex min-w-0 items-center gap-2 text-xs text-base-content/50", className)}
      data-testid="turn-activity"
      data-mode={mode ?? undefined}
    >
      {mode && <ActivityLogo mode={mode} />}
      {label && (
        <div
          role="status"
          className="min-w-0 truncate text-base-content/70"
          data-testid="turn-activity-label"
        >
          {label}
        </div>
      )}
      {label && !note && (
        <span className="shrink-0 tabular-nums" aria-hidden="true">
          {formatDuration(now - startedAt)}
        </span>
      )}
      {/* Announced once when the connection drops; the ticking time is not. */}
      {lost && (
        <div role="status" className="sr-only">
          Connection lost, reconnecting
        </div>
      )}
      {note && (
        <span
          className={`flex min-w-0 items-center gap-1.5 ${lost ? "text-warning" : ""}`}
          data-testid="turn-connection"
          data-state={connection?.state}
          aria-hidden="true"
        >
          <span
            className={`status status-xs shrink-0 ${lost ? "status-warning" : "status-neutral"}`}
            aria-hidden="true"
          />
          <span className="truncate tabular-nums">{note.text}</span>
        </span>
      )}
    </div>
  );
}
