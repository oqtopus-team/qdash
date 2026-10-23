"use client";

import Link from "next/link";

import { useEffect, useState } from "react";
import { Brain, Check, Loader2, PenLine, X } from "lucide-react";
import type { ChatTrace as ChatTraceData, ToolEvaluation, TraceStep } from "@/types/copilotChat";
import { ChatMarkdown } from "@/components/features/chat/ChatMarkdown";
import { FigureStrip } from "@/components/features/chat/ChatFigures";
import {
  ToolDetails,
  hasDetails,
  isWorkspaceTool,
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
    <div className="mt-1.5 text-[11px] text-base-content/60">
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
        <pre className="mt-1 max-h-80 overflow-auto whitespace-pre-wrap rounded-md bg-base-200/60 p-2 font-mono text-[11px] leading-relaxed text-base-content/70">
          {evaluation.prompt}
        </pre>
      </details>
    </div>
  );
}

function ToolStepRow({
  step,
  now,
  live,
  isLast,
}: {
  step: Extract<TraceStep, { kind: "tool" }>;
  now: number;
  /** The turn is still streaming; code and output stay in view instead of folding. */
  live: boolean;
  isLast?: boolean;
}) {
  const Icon = toolIcon(step.tool);
  const preview = stepPreview(step);
  // Code written live stays open while it runs and when its output lands;
  // folding it the moment the call starts would hide what the user just watched.
  const stayOpen = live && (isWorkspaceTool(step.tool) || step.tool === "qdash_save_flow");
  const elapsed = (step.endedAt ?? now) - step.startedAt;
  const details = hasDetails(step);
  const drafting = step.status === "drafting";
  // While the assistant waits on an execution, show its tasks and figures as they land.
  const waitingOn = executionIdFromArgs(step.args);

  return (
    <ChainOfThoughtStep
      isLast={isLast}
      status={
        step.status === "drafting" ? "running" : step.status === "cancelled" ? "idle" : step.status
      }
      // A call being written opens its row; a workspace step stays open for the whole live turn.
      isStreaming={drafting && !stayOpen}
      defaultOpen={stayOpen}
      marker={
        drafting ? (
          <PenLine className="w-3 h-3" />
        ) : step.status === "running" ? (
          <Loader2 className="w-3 h-3 animate-spin" />
        ) : step.status === "error" || step.status === "cancelled" ? (
          <X className="w-3 h-3" />
        ) : (
          <Check className="w-3 h-3" />
        )
      }
    >
      <ChainOfThoughtTrigger
        hideChevron={!details || drafting}
        disabled={!details}
        className={details ? "" : "cursor-default"}
      >
        <Icon className="w-3.5 h-3.5 shrink-0 text-base-content/50" />
        <span
          className={`font-medium shrink-0 ${
            step.status === "running" || drafting ? "loader-text-shimmer" : "text-base-content/80"
          }`}
        >
          {stepTitle(step)}
        </span>
        {preview && (
          <span className="truncate font-mono text-[11px] text-base-content/40">{preview}</span>
        )}
        <span className="ml-auto shrink-0 tabular-nums text-[11px] text-base-content/35">
          {step.status === "error" ? "failed · " : step.status === "cancelled" ? "not run · " : ""}
          {formatDuration(elapsed)}
        </span>
      </ChainOfThoughtTrigger>
      {step.status === "running" && step.tool === "qdash_wait_execution" && waitingOn && (
        <ExecutionProgress executionId={waitingOn} />
      )}
      {step.figures && step.figures.length > 0 && (
        <FigureStrip paths={step.figures} compact className="mt-1.5" />
      )}
      {step.evaluation && <EvaluationPanel evaluation={step.evaluation} />}
      {details && (
        <ChainOfThoughtContent>
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
  isLast,
}: {
  step: Extract<TraceStep, { kind: "thinking" }>;
  now: number;
  live: boolean;
  isLast?: boolean;
}) {
  const active = live && step.endedAt === undefined;
  const elapsed = (step.endedAt ?? now) - step.startedAt;

  return (
    // Open while the thought streams, folds up on its own when it ends.
    <ChainOfThoughtStep
      isLast={isLast}
      status={active ? "running" : "idle"}
      marker={<Brain className="w-3 h-3" />}
      isStreaming={active}
    >
      <ChainOfThoughtTrigger hideChevron={active}>
        {active ? (
          <Loader variant="text-shimmer" size="sm" text="Thinking" />
        ) : (
          <span className="font-medium text-base-content/80">
            Thought for {formatDuration(elapsed)}
          </span>
        )}
      </ChainOfThoughtTrigger>
      {step.text && (
        <ChainOfThoughtContent>
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
    <ChainOfThought>
      {steps.map((step, i) => {
        if (step.kind === "tool") {
          return <ToolStepRow key={step.id} step={step} now={now} live={live} />;
        }
        if (step.kind === "thinking") {
          return <ThinkingStepRow key={`thinking-${i}`} step={step} now={now} live={live} />;
        }
        return (
          <ChainOfThoughtStep key={`text-${i}`} marker={null} defaultOpen>
            <ChatMarkdown className="text-[13px] text-base-content/70">{step.text}</ChatMarkdown>
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
  const failed = trace.steps.some((s) => s.kind === "tool" && s.status === "error");
  return (
    <Reasoning className="mb-2">
      <ReasoningTrigger className="chat-trace-toggle">
        <span>{summarize(trace.steps)}</span>
        <span className="text-base-content/35">· {formatDuration(trace.durationMs)}</span>
        {failed && <span className="text-error/70">· some steps failed</span>}
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
