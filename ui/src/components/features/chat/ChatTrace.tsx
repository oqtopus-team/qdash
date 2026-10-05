"use client";

import { useEffect, useState } from "react";
import {
  Brain,
  Check,
  ChevronRight,
  Loader2,
  Wrench,
  X,
  Code2,
  LineChart,
  Database,
} from "lucide-react";
import type { ChatTrace as ChatTraceData, TraceStep } from "@/hooks/useCopilotChat";
import { CodeBlock } from "@/components/features/chat/CodeBlock";
import { ChatMarkdown } from "@/components/features/chat/ChatMarkdown";

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

function toolIcon(tool: string) {
  if (tool.includes("python")) return Code2;
  if (tool.includes("chart") || tool.includes("timeseries") || tool.includes("plot")) {
    return LineChart;
  }
  if (tool.startsWith("qdash_")) return Database;
  return Wrench;
}

/** A short one-line hint of what the tool was asked, e.g. `qid: 0, parameter: t1`. */
function argsPreview(args: unknown): string | null {
  if (!args || typeof args !== "object") return null;
  const entries = Object.entries(args as Record<string, unknown>).filter(
    ([, v]) => v !== null && v !== undefined && v !== "",
  );
  if (entries.length === 0) return null;
  const text = entries
    .map(([k, v]) => {
      const value = typeof v === "string" ? v.split("\n")[0] : JSON.stringify(v);
      return `${k}: ${value}`;
    })
    .join(", ");
  return text.length > 90 ? `${text.slice(0, 90)}…` : text;
}

function ToolArgs({ args }: { args: unknown }) {
  if (args === undefined || args === null) return null;
  if (typeof args === "string") {
    return <CodeBlock language="json">{args}</CodeBlock>;
  }
  const record = args as Record<string, unknown>;
  // run_python and similar tools carry source code; show it as code.
  if (typeof record.code === "string") {
    const { code, ...rest } = record;
    return (
      <>
        <CodeBlock language="python">{code}</CodeBlock>
        {Object.keys(rest).length > 0 && (
          <CodeBlock language="json">{JSON.stringify(rest, null, 2)}</CodeBlock>
        )}
      </>
    );
  }
  return <CodeBlock language="json">{JSON.stringify(args, null, 2)}</CodeBlock>;
}

function ToolStepRow({ step, now }: { step: Extract<TraceStep, { kind: "tool" }>; now: number }) {
  const [open, setOpen] = useState(false);
  const Icon = toolIcon(step.tool);
  const preview = argsPreview(step.args);
  const elapsed = (step.endedAt ?? now) - step.startedAt;
  const hasArgs = step.args !== undefined && step.args !== null;

  return (
    <li className="chat-trace-item">
      <span className="chat-trace-dot" data-status={step.status}>
        {step.status === "running" ? (
          <Loader2 className="w-3 h-3 animate-spin" />
        ) : step.status === "error" ? (
          <X className="w-3 h-3" />
        ) : (
          <Check className="w-3 h-3" />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <button
          type="button"
          onClick={() => hasArgs && setOpen((o) => !o)}
          className={`group flex w-full items-center gap-2 text-left text-xs ${
            hasArgs ? "cursor-pointer" : "cursor-default"
          }`}
          aria-expanded={hasArgs ? open : undefined}
        >
          <Icon className="w-3.5 h-3.5 shrink-0 text-base-content/50" />
          <span
            className={`font-medium shrink-0 ${
              step.status === "running" ? "chat-shimmer-text" : "text-base-content/80"
            }`}
          >
            {step.label}
          </span>
          {preview && (
            <span className="truncate font-mono text-[11px] text-base-content/40">{preview}</span>
          )}
          <span className="ml-auto shrink-0 tabular-nums text-[11px] text-base-content/35">
            {step.status === "error" ? "failed · " : ""}
            {formatDuration(elapsed)}
          </span>
          {hasArgs && (
            <ChevronRight
              className={`w-3 h-3 shrink-0 text-base-content/30 transition-transform ${
                open ? "rotate-90" : ""
              }`}
            />
          )}
        </button>
        {open && (
          <div className="mt-1 animate-fade-in-up">
            <ToolArgs args={step.args} />
          </div>
        )}
      </div>
    </li>
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
  const [open, setOpen] = useState(false);
  const elapsed = (step.endedAt ?? now) - step.startedAt;

  return (
    <li className="chat-trace-item">
      <span className="chat-trace-dot" data-status={active ? "running" : "idle"}>
        <Brain className="w-3 h-3" />
      </span>
      <div className="min-w-0 flex-1">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center gap-2 text-left text-xs"
          aria-expanded={open || active}
        >
          <span className={`font-medium ${active ? "chat-shimmer-text" : "text-base-content/80"}`}>
            {active ? "Thinking" : `Thought for ${formatDuration(elapsed)}`}
          </span>
          <ChevronRight
            className={`w-3 h-3 text-base-content/30 transition-transform ${
              open || active ? "rotate-90" : ""
            }`}
          />
        </button>
        {(open || active) && step.text && (
          <div className="chat-thinking-text mt-1">
            {active ? step.text.slice(-1200) : step.text}
          </div>
        )}
      </div>
    </li>
  );
}

function TraceSteps({ steps, live }: { steps: TraceStep[]; live: boolean }) {
  const running = live && steps.some((s) => s.kind === "thinking" || s.kind === "tool");
  const now = useNow(running);
  return (
    <ol className="chat-trace-list">
      {steps.map((step, i) => {
        if (step.kind === "tool") return <ToolStepRow key={step.id} step={step} now={now} />;
        if (step.kind === "thinking") {
          return <ThinkingStepRow key={`thinking-${i}`} step={step} now={now} live={live} />;
        }
        return (
          <li key={`text-${i}`} className="chat-trace-item">
            <span className="chat-trace-dot" data-status="idle" />
            <ChatMarkdown className="text-[13px] text-base-content/70 min-w-0 flex-1">
              {step.text}
            </ChatMarkdown>
          </li>
        );
      })}
    </ol>
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
  const [open, setOpen] = useState(false);
  const failed = trace.steps.some((s) => s.kind === "tool" && s.status === "error");
  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="chat-trace-toggle"
        aria-expanded={open}
      >
        <span>{summarize(trace.steps)}</span>
        <span className="text-base-content/35">· {formatDuration(trace.durationMs)}</span>
        {failed && <span className="text-error/70">· some steps failed</span>}
        <ChevronRight className={`w-3 h-3 transition-transform ${open ? "rotate-90" : ""}`} />
      </button>
      {open && (
        <div className="mt-2 animate-fade-in-up">
          <TraceSteps steps={trace.steps} live={false} />
        </div>
      )}
    </div>
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
