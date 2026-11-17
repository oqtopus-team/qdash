"use client";

import Link from "next/link";

import { useEffect, useState, type ReactNode } from "react";
import { twMerge } from "tailwind-merge";
import { Ban, Brain, ChevronRight, CircleX } from "lucide-react";
import type {
  ChatTrace as ChatTraceData,
  ToolClassification,
  ToolEvaluation,
  TraceStep,
} from "@/types/copilotChat";
import { ChatMarkdown } from "@/components/features/chat/ChatMarkdown";
import { FigureStrip } from "@/components/features/chat/ChatFigures";
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
} from "@/components/features/chat/ExecutionProgress";
import {
  ChainOfThought,
  ChainOfThoughtContent,
  ChainOfThoughtStep,
  ChainOfThoughtTrigger,
} from "@/components/ui/ChainOfThought";
import { Loader } from "@/components/ui/Loader";
import { Reasoning, ReasoningContent, ReasoningTrigger } from "@/components/ui/Reasoning";

function formatDuration(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

/** Re-render once per second while something is running, for live timers. */
function useNow(active: boolean): number {
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

function ToolStepRow({ step, now }: { step: ToolStep; now: number }) {
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
  const failure = open ? null : failureLine(step);
  // While the assistant waits on an execution, show its tasks and figures as they land.
  const waitingOn = executionIdFromArgs(step.args);
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
        {preview && (
          <span className="min-w-0 flex-[1_1_0%] truncate text-xs text-base-content/40">
            {preview}
          </span>
        )}
        {details && <RowChevron open={open} />}
        <span className="ml-auto flex shrink-0 items-center gap-1.5 text-xs tabular-nums text-base-content/40">
          {failed ? (
            <span className="text-error">Failed</span>
          ) : cancelled ? (
            <span>Not run</span>
          ) : (
            <span className="sr-only">{TOOL_STATUS_LABEL[step.status]}</span>
          )}
          {!drafting && !cancelled && <span>{formatDuration(elapsed)}</span>}
        </span>
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
      {running && step.tool === "qdash_wait_execution" && waitingOn && (
        <div className={ROW_INDENT}>
          <ExecutionProgress executionId={waitingOn} />
        </div>
      )}
      {step.figures && step.figures.length > 0 && (
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

function TraceSteps({ steps, live }: { steps: TraceStep[]; live: boolean }) {
  const running = live && steps.some((s) => s.kind === "thinking" || s.kind === "tool");
  const now = useNow(running);
  return (
    <ChainOfThought variant="plain">
      {steps.map((step, i) => {
        if (step.kind === "tool") {
          // Steps are append-only within a turn; a draft ID can change when execution starts.
          return <ToolStepRow key={`tool-${i}`} step={step} now={now} />;
        }
        if (step.kind === "thinking") {
          return <ThinkingStepRow key={`thinking-${i}`} step={step} now={now} live={live} />;
        }
        return (
          <ChainOfThoughtStep key={`text-${i}`} defaultOpen>
            <ChatMarkdown
              className="text-sm text-base-content/70"
              streaming={live && i === steps.length - 1}
            >
              {step.text}
            </ChatMarkdown>
          </ChainOfThoughtStep>
        );
      })}
    </ChainOfThought>
  );
}

function summarize(steps: TraceStep[]): string {
  const tools = steps.filter((s) => s.kind === "tool").length;
  const thought = steps.some((s) => s.kind === "thinking");
  const parts: string[] = [];
  if (thought) parts.push("Thought");
  if (tools > 0) parts.push(`used ${tools} tool${tools === 1 ? "" : "s"}`);
  const text = parts.join(", ") || "Worked";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Collapsed "Used 3 tools · 12s" summary for a finished answer. */
export function ChatTraceSummary({ trace }: { trace: ChatTraceData }) {
  const tools = trace.steps.filter((s): s is ToolStep => s.kind === "tool");
  // Failures stay visible on the folded summary, so they are found without opening it.
  const failed = tools.filter((s) => s.status === "error").length;
  const notRun = tools.filter((s) => s.status === "cancelled").length;
  return (
    <Reasoning className="mb-2">
      <ReasoningTrigger className="chat-trace-toggle max-w-full flex-wrap">
        <span>{summarize(trace.steps)}</span>
        <span className="text-base-content/50">· {formatDuration(trace.durationMs)}</span>
        {failed > 0 && (
          <span className="inline-flex items-center gap-1 text-error">
            · <CircleX className="w-3 h-3" aria-hidden="true" />
            {failed} failed
          </span>
        )}
        {notRun > 0 && <span className="text-base-content/50">· {notRun} not run</span>}
      </ReasoningTrigger>
      <ReasoningContent>
        <div className="mt-2">
          <TraceSteps steps={trace.steps} live={false} />
        </div>
      </ReasoningContent>
    </Reasoning>
  );
}

/** Steps of the turn that is still streaming, always expanded. */
export function LiveTrace({ steps }: { steps: TraceStep[] }) {
  if (steps.length === 0) return null;
  return (
    <div className="mb-3">
      <TraceSteps steps={steps} live />
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
  leading,
  className,
}: {
  steps: TraceStep[];
  startedAt: number;
  statusMessage: string | null;
  /** Drawn before the activity when the footer is visible, e.g. the assistant's avatar. */
  leading?: ReactNode;
  className?: string;
}) {
  const now = useNow(true);
  const activity = currentActivity(steps, statusMessage);
  const inTrace = activityShownInTrace(steps);
  return (
    <div
      className={
        inTrace
          ? "sr-only"
          : twMerge("flex min-w-0 items-center gap-2 text-xs text-base-content/50", className)
      }
      data-testid="turn-activity"
      data-in-trace={inTrace}
    >
      {!inTrace && leading}
      <div role="status" className="flex min-w-0 items-center">
        {inTrace ? (
          activity
        ) : activity ? (
          <Loader variant="text-shimmer" size="sm" text={activity} className="truncate" />
        ) : (
          <Loader variant="typing" size="sm" />
        )}
      </div>
      {!inTrace && (
        <span className="shrink-0 tabular-nums" aria-hidden="true">
          {formatDuration(now - startedAt)}
        </span>
      )}
    </div>
  );
}
