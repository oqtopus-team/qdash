"use client";

import { useEffect, useRef, useState } from "react";
import {
  Code2,
  Database,
  FileCode,
  FileDiff,
  FilePenLine,
  LineChart,
  Terminal,
  Wrench,
} from "lucide-react";
import type { TraceStep } from "@/types/copilotChat";
import { CodeBlock } from "@/components/features/chat/CodeBlock";

/**
 * What a tool step shows under its row: the workspace tools (bash, read,
 * write, edit) as the command or file they touched and what came back, a tool
 * call still being written as live code, and every other tool as its
 * arguments.
 */

type ToolStep = Extract<TraceStep, { kind: "tool" }>;

const WORKSPACE_TOOLS = new Set(["bash", "read", "write", "edit"]);

export function isWorkspaceTool(tool: string): boolean {
  return WORKSPACE_TOOLS.has(tool);
}

export function toolIcon(tool: string) {
  if (tool === "bash") return Terminal;
  if (tool === "read") return FileCode;
  if (tool === "write") return FilePenLine;
  if (tool === "edit") return FileDiff;
  if (tool.includes("python") || tool.endsWith("_flow")) return Code2;
  if (tool.includes("chart") || tool.includes("timeseries") || tool.includes("plot")) {
    return LineChart;
  }
  if (tool.startsWith("qdash_")) return Database;
  return Wrench;
}

const LANGUAGE_BY_EXTENSION: Record<string, string> = {
  py: "python",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  sh: "bash",
  bash: "bash",
  ts: "typescript",
  tsx: "typescript",
  js: "javascript",
  mjs: "javascript",
  sql: "sql",
};

/** The highlighter language for a file path, or undefined for plain text. */
function languageForPath(path: string | undefined): string | undefined {
  if (!path) return undefined;
  const extension = path.split(".").pop()?.toLowerCase();
  return extension ? LANGUAGE_BY_EXTENSION[extension] : undefined;
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function firstLine(value: string): string {
  const line = value.split("\n").find((l) => l.trim()) ?? "";
  return line.length > 90 ? `${line.slice(0, 90)}…` : line;
}

/** A short one-line hint of what the tool was asked, e.g. `qid: 0, parameter: t1`. */
function argsPreview(args: unknown): string | null {
  const entries = Object.entries(record(args) ?? {}).filter(
    ([, v]) => v !== null && v !== undefined && v !== "",
  );
  if (entries.length === 0) return null;
  const line = entries
    .map(([k, v]) => `${k}: ${typeof v === "string" ? v.split("\n")[0] : JSON.stringify(v)}`)
    .join(", ");
  return line.length > 90 ? `${line.slice(0, 90)}…` : line;
}

/** The one-line hint next to a step's label: the command, the file, or the arguments. */
export function stepPreview(step: ToolStep): string | null {
  const args = record(step.status === "drafting" ? step.draft : step.args);
  if (!args) return step.status === "drafting" ? "writing…" : null;
  if (step.tool === "bash") {
    const command = text(args.command);
    return command ? `$ ${firstLine(command)}` : null;
  }
  if (isWorkspaceTool(step.tool)) {
    // The path is in the title; only an edit count adds anything.
    const edits = Array.isArray(args.edits) ? args.edits.length : 0;
    return edits > 0 ? `${edits} edit${edits === 1 ? "" : "s"}` : null;
  }
  if (step.tool === "qdash_save_flow" || step.tool === "qdash_execute_flow") {
    const name = text(args.name);
    return name ? `flow ${name}` : null;
  }
  return argsPreview(args);
}

/** How long the shown text may trail the streamed text while catching up. */
const CATCH_UP_MS = 300;
const FRAME_MS = 16;

/**
 * Reveal streamed text at a steady pace. Argument deltas arrive in clumps and
 * a fast model lands a short script in well under a second, so shown as it
 * arrives the typing is a flash; paced, every frame adds a slice of what is
 * still unseen and the display never trails the stream by more than
 * `CATCH_UP_MS`. A text that is not a continuation (a new draft) shows at once.
 */
export function usePacedText(target: string): string {
  const [shown, setShown] = useState(target);
  const shownRef = useRef(target);
  useEffect(() => {
    if (!target.startsWith(shownRef.current)) {
      shownRef.current = target;
      setShown(target);
      return;
    }
    if (shownRef.current.length >= target.length) return;
    // A fixed slice per frame, sized when the text grows, so the backlog drains
    // linearly within CATCH_UP_MS instead of tailing off a character at a time.
    const step = Math.max(
      1,
      Math.ceil(((target.length - shownRef.current.length) * FRAME_MS) / CATCH_UP_MS),
    );
    const timer = setInterval(() => {
      if (shownRef.current.length >= target.length) {
        clearInterval(timer);
        return;
      }
      shownRef.current = target.slice(0, shownRef.current.length + step);
      setShown(shownRef.current);
    }, FRAME_MS);
    return () => clearInterval(timer);
  }, [target]);
  return shown;
}

/** Code the model is typing into a tool call, paced and following the newest line. */
function LiveCode({
  language,
  title,
  children,
}: {
  language?: string;
  title?: string;
  children: string;
}) {
  const shown = usePacedText(children);
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [shown]);
  return (
    <div ref={scroller} className="max-h-80 overflow-auto" data-testid="live-code">
      <CodeBlock compact caret language={language} title={title}>
        {shown}
      </CodeBlock>
    </div>
  );
}

/** The row's title: what the step is doing to what, in the user's terms. */
export function stepTitle(step: ToolStep): string {
  const args = record(step.status === "drafting" ? step.draft : step.args);
  const path = text(args?.path);
  const name = text(args?.name);
  const drafting = step.status === "drafting";
  if (step.status === "cancelled") {
    // The turn ended while the call was being written; nothing was made or run.
    switch (step.tool) {
      case "bash":
        return "Command not run";
      case "write":
        return `Not written${path ? ` ${path}` : ""}`;
      case "edit":
        return `Not edited${path ? ` ${path}` : ""}`;
      case "read":
        return `Not read${path ? ` ${path}` : ""}`;
      default:
        return `${step.label} (not called)`;
    }
  }
  switch (step.tool) {
    case "bash":
      return drafting ? "Writing a command" : step.status === "running" ? "Running" : "Ran";
    case "write":
      return `${drafting || step.status === "running" ? "Writing" : "Wrote"}${path ? ` ${path}` : ""}`;
    case "edit":
      return `${drafting || step.status === "running" ? "Editing" : "Edited"}${path ? ` ${path}` : ""}`;
    case "read":
      return `${step.status === "done" || step.status === "error" ? "Read" : "Reading"}${path ? ` ${path}` : ""}`;
    case "qdash_save_flow":
      return drafting ? `Writing flow${name ? ` ${name}` : ""}` : step.label;
    default:
      return drafting ? `Writing a ${step.label.toLowerCase()} call` : step.label;
  }
}

/** The arguments the model has written so far: code as live code, the rest as lines. */
function DraftView({ step }: { step: ToolStep }) {
  const draft = step.draft ?? {};
  const path = draft.path;
  const code = draft.content ?? draft.code ?? draft.command;
  const language =
    draft.command !== undefined
      ? "bash"
      : draft.code !== undefined
        ? "python"
        : languageForPath(path);
  const others = Object.entries(draft).filter(
    ([key]) => !["content", "code", "command"].includes(key),
  );
  return (
    <div>
      {others.length > 0 && (
        <dl className="mb-1 grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-[11px]">
          {others.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="font-mono text-base-content/45">{key}</dt>
              <dd className="m-0 min-w-0 truncate font-mono text-base-content/70">{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {code !== undefined ? (
        <LiveCode language={language} title={path}>
          {code}
        </LiveCode>
      ) : (
        <p className="text-[11px] text-base-content/45">Writing the call…</p>
      )}
    </div>
  );
}

function PathLine({ path, detail }: { path: string | undefined; detail?: string }) {
  if (!path) return null;
  return (
    <div className="mb-1 font-mono text-[11px] text-base-content/60">
      {path}
      {detail && <span className="text-base-content/40"> · {detail}</span>}
    </div>
  );
}

/** What a workspace tool answered: a command's output tail, a file's text, a write's receipt. */
function OutputPanel({ step }: { step: ToolStep }) {
  if (!step.output) return null;
  const failed = step.status === "error" || (step.exitCode !== undefined && step.exitCode !== 0);
  return (
    <div className="mt-1.5">
      <div className="mb-0.5 flex items-center gap-2 text-[11px] text-base-content/50">
        <span>Output</span>
        {step.exitCode !== undefined && step.exitCode !== 0 && (
          <span className="rounded bg-error/10 px-1.5 py-px font-mono text-error/80">
            exit {step.exitCode}
          </span>
        )}
      </div>
      <pre
        className={`m-0 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md p-2 font-mono text-[11px] leading-relaxed ${
          failed ? "bg-error/5 text-base-content/75" : "bg-base-200/60 text-base-content/70"
        }`}
      >
        {step.output}
      </pre>
    </div>
  );
}

function EditsView({ edits }: { edits: unknown[] }) {
  return (
    <div className="space-y-1.5">
      {edits.map((edit, i) => {
        const pair = record(edit);
        return (
          <div key={i} className="overflow-hidden rounded-md border border-base-300/60 text-[11px]">
            <pre className="m-0 whitespace-pre-wrap break-words bg-error/5 px-2 py-1 font-mono text-base-content/70">
              {`- ${text(pair?.oldText) ?? ""}`}
            </pre>
            <pre className="m-0 whitespace-pre-wrap break-words bg-success/5 px-2 py-1 font-mono text-base-content/70">
              {`+ ${text(pair?.newText) ?? ""}`}
            </pre>
          </div>
        );
      })}
    </div>
  );
}

/** Any tool's arguments: source as code, the rest as JSON. */
function ArgsView({ args }: { args: unknown }) {
  if (args === undefined || args === null) return null;
  if (typeof args === "string")
    return (
      <CodeBlock compact language="json">
        {args}
      </CodeBlock>
    );
  const values = record(args) ?? {};
  const source =
    typeof values.command === "string"
      ? { key: "command", language: "bash" }
      : typeof values.code === "string"
        ? { key: "code", language: "python" }
        : undefined;
  if (!source)
    return (
      <CodeBlock compact language="json">
        {JSON.stringify(args, null, 2)}
      </CodeBlock>
    );
  const { [source.key]: code, ...rest } = values;
  return (
    <>
      <CodeBlock compact language={source.language}>
        {String(code)}
      </CodeBlock>
      {Object.keys(rest).length > 0 && (
        <CodeBlock compact language="json">
          {JSON.stringify(rest, null, 2)}
        </CodeBlock>
      )}
    </>
  );
}

/** Whether a step has anything to show under its row. */
export function hasDetails(step: ToolStep): boolean {
  if (step.status === "drafting") return true;
  return (step.args !== undefined && step.args !== null) || Boolean(step.output);
}

export function ToolDetails({ step }: { step: ToolStep }) {
  if (step.status === "drafting") return <DraftView step={step} />;
  const args = record(step.args);
  if (step.tool === "bash") {
    const command = text(args?.command);
    return (
      <div>
        {command && (
          <CodeBlock compact language="bash">
            {command}
          </CodeBlock>
        )}
        <OutputPanel step={step} />
      </div>
    );
  }
  if (step.tool === "write") {
    const path = text(args?.path);
    const content = text(args?.content);
    return (
      <div>
        {content === undefined && <PathLine path={path} />}
        {content !== undefined && (
          <CodeBlock compact language={languageForPath(path)} title={path}>
            {content}
          </CodeBlock>
        )}
        <OutputPanel step={step} />
      </div>
    );
  }
  if (step.tool === "edit") {
    const edits = Array.isArray(args?.edits) ? args.edits : [];
    return (
      <div>
        <PathLine path={text(args?.path)} />
        {edits.length > 0 && <EditsView edits={edits} />}
        <OutputPanel step={step} />
      </div>
    );
  }
  if (step.tool === "read") {
    const offset = args?.offset;
    const limit = args?.limit;
    const range =
      typeof offset === "number" || typeof limit === "number"
        ? `lines ${typeof offset === "number" ? offset : 1}${typeof limit === "number" ? ` +${limit}` : ""}`
        : undefined;
    return (
      <div>
        <PathLine path={text(args?.path)} detail={range} />
        <OutputPanel step={step} />
      </div>
    );
  }
  return (
    <div>
      <ArgsView args={step.args} />
      <OutputPanel step={step} />
    </div>
  );
}
