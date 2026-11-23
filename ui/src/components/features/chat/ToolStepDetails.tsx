"use client";

import { useEffect, useRef, useState } from "react";
import {
  Code2,
  Database,
  FileCode,
  FileDiff,
  FilePenLine,
  LineChart,
  Tags,
  Terminal,
  Wrench,
} from "lucide-react";
import type { TraceStep } from "@/types/agentChat";
import { CodeBlock } from "@/components/features/chat/CodeBlock";

/**
 * What a tool step shows under its row: the workspace tools (bash, read,
 * write, edit) as the command or file they touched and what came back, a tool
 * call still being written as live code, and every other tool as its
 * arguments.
 */

type ToolStep = Extract<TraceStep, { kind: "tool" }>;

const WORKSPACE_TOOLS = new Set(["bash", "read", "write", "edit"]);

/** The tool that asks the configured classifier model (agent-runtime classify-tool.ts). */
const CLASSIFY_TOOL = "classify";

/** The tool that runs a JavaScript script calling read-only QDash tools (agent-runtime codemode.ts). */
const CODEMODE_TOOL = "codemode";

/** Language of a tool call's `code` argument. */
function codeLanguage(tool: string): string {
  return tool === CODEMODE_TOOL ? "javascript" : "python";
}

function isWorkspaceTool(tool: string): boolean {
  return WORKSPACE_TOOLS.has(tool);
}

export function toolIcon(tool: string) {
  if (tool === "bash") return Terminal;
  if (tool === "read") return FileCode;
  if (tool === "write") return FilePenLine;
  if (tool === "edit") return FileDiff;
  if (tool === CLASSIFY_TOOL) return Tags;
  if (tool === CODEMODE_TOOL) return Code2;
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

/** Words that only set up the command that follows them. */
const COMMAND_PREFIXES = new Set(["sudo", "env", "time", "nohup", "exec", "command"]);

/**
 * The program a shell command runs, for a short row title: `bun` for
 * `cd ui && bun run test`. It reads only the first line and skips a leading
 * `cd`, environment assignments and wrapper words; anything it does not
 * recognise as a plain program name gives null, so the caller falls back to a
 * generic title instead of showing a fragment of the command.
 */
export function commandName(command: string | undefined): string | null {
  if (!command) return null;
  const line = command.split("\n").find((l) => l.trim()) ?? "";
  // This is a display hint, not a shell parser. Quoting, escapes and expansion
  // can hide whitespace or separators inside values; never display their fragments.
  if (/["'`\\$]/.test(line)) return null;
  for (const segment of line.split(/&&|\|\||;|\|/)) {
    const words = segment.trim().split(/\s+/).filter(Boolean);
    while (words.length > 0 && (/^\w+=/.test(words[0]) || COMMAND_PREFIXES.has(words[0]))) {
      words.shift();
    }
    const program = words[0]?.split("/").pop();
    if (!program || program === "cd") continue;
    return /^[\w][\w.+-]{0,31}$/.test(program) ? program : null;
  }
  return null;
}

/**
 * A short, curated hint next to a step's title, such as an edit count or a
 * flow name. Raw commands, code and arguments stay in the details.
 */
export function stepPreview(step: ToolStep): string | null {
  const args = record(step.status === "drafting" ? step.draft : step.args);
  if (!args || step.tool === "bash") return null;
  if (isWorkspaceTool(step.tool)) {
    // The path is in the title; only an edit count adds anything.
    const edits = Array.isArray(args.edits) ? args.edits.length : 0;
    return edits > 0 ? `${edits} edit${edits === 1 ? "" : "s"}` : null;
  }
  if (step.tool === "qdash_save_flow" || step.tool === "qdash_execute_flow") {
    const name = text(args.name);
    return name ? `flow ${name}` : null;
  }
  if (step.tool === CLASSIFY_TOOL) {
    const question = text(args.question);
    return question ? firstLine(question) : null;
  }
  return null;
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
    case "bash": {
      if (drafting) return "Writing a command";
      const program = commandName(text(args?.command));
      const verb = step.status === "running" ? "Running" : "Ran";
      return `${verb} ${program ?? "a command"}`;
    }
    case "write":
      return `${drafting || step.status === "running" ? "Writing" : "Wrote"}${path ? ` ${path}` : ""}`;
    case "edit":
      return `${drafting || step.status === "running" ? "Editing" : "Edited"}${path ? ` ${path}` : ""}`;
    case "read":
      return `${step.status === "done" || step.status === "error" ? "Read" : "Reading"}${path ? ` ${path}` : ""}`;
    case CODEMODE_TOOL:
      return drafting
        ? "Writing a script"
        : step.status === "running"
          ? "Running a script"
          : "Ran a script";
    case "qdash_save_flow":
      return drafting ? `Writing flow${name ? ` ${name}` : ""}` : step.label;
    case CLASSIFY_TOOL: {
      if (drafting) return "Writing a classification question";
      if (step.status === "running") return "Classifying";
      if (step.status === "error") return "Classification failed";
      const outcome = step.classification?.outcome;
      const category = step.classification?.category;
      if (step.status === "done" && outcome === "classified" && category) {
        return `Classified as ${category}`;
      }
      if (step.status === "done" && outcome === "ambiguous") return "Classification unclear";
      return step.status === "done" ? "Classified" : step.label;
    }
    // The waiting tools: while running, the turn is parked on QDash, not working.
    case "qdash_wait_agent_intervention":
      if (step.status === "running") return "Waiting for the expert's answer";
      return step.status === "done" ? "Expert answer received" : step.label;
    case "qdash_wait_agent_action":
      if (step.status === "running") return "Waiting for the calibration step to finish";
      return step.status === "done" ? "Calibration step ended" : step.label;
    case "qdash_wait_execution":
      if (step.status === "running") return "Waiting for the execution to finish";
      return step.status === "done" ? "Execution ended" : step.label;
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
        ? codeLanguage(step.tool)
        : languageForPath(path);
  const others = Object.entries(draft).filter(
    ([key]) => !["content", "code", "command"].includes(key),
  );
  return (
    <div>
      {others.length > 0 && (
        <dl className="mb-1 grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-xs">
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
        <p className="text-xs text-base-content/45">Writing the call…</p>
      )}
    </div>
  );
}

/**
 * Code a call ran, held to a bounded scroll box so an expanded script does not
 * push the newest output far below the fold.
 */
function BoundedCode(props: Parameters<typeof CodeBlock>[0]) {
  return (
    <div className="max-h-72 overflow-y-auto" data-testid="tool-code">
      <CodeBlock compact {...props} />
    </div>
  );
}

function PathLine({ path, detail }: { path: string | undefined; detail?: string }) {
  if (!path) return null;
  return (
    <div className="mb-1 break-all font-mono text-xs text-base-content/60">
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
      <div className="mb-0.5 flex items-center gap-2 text-xs text-base-content/50">
        <span>Output</span>
        {step.exitCode !== undefined && step.exitCode !== 0 && (
          <span className="rounded bg-error/10 px-1.5 py-px font-mono text-error/80">
            exit {step.exitCode}
          </span>
        )}
      </div>
      <pre
        className={`m-0 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md p-2 font-mono text-xs leading-relaxed ${
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
          <div key={i} className="overflow-hidden rounded-md border border-base-300/60 text-xs">
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
function ArgsView({ tool, args }: { tool: string; args: unknown }) {
  if (args === undefined || args === null) return null;
  if (typeof args === "string") return <BoundedCode language="json">{args}</BoundedCode>;
  const values = record(args) ?? {};
  const source =
    typeof values.command === "string"
      ? { key: "command", language: "bash" }
      : typeof values.code === "string"
        ? { key: "code", language: codeLanguage(tool) }
        : undefined;
  if (!source) return <BoundedCode language="json">{JSON.stringify(args, null, 2)}</BoundedCode>;
  const { [source.key]: code, ...rest } = values;
  return (
    <>
      <BoundedCode language={source.language}>{String(code)}</BoundedCode>
      {Object.keys(rest).length > 0 && (
        <BoundedCode language="json">{JSON.stringify(rest, null, 2)}</BoundedCode>
      )}
    </>
  );
}

/** What the assistant asked the classifier: the question, the candidates and the context. */
function ClassifyArgsView({ args }: { args: Record<string, unknown> }) {
  const question = text(args.question);
  const context = text(args.context);
  const categories = (Array.isArray(args.categories) ? args.categories : []).flatMap((entry) => {
    const category = record(entry);
    const name = text(category?.name);
    return name ? [{ name, description: text(category?.description) }] : [];
  });
  return (
    <div className="space-y-1.5 text-xs">
      {question && <p className="text-base-content/75">{question}</p>}
      {categories.length > 0 && (
        <dl className="grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-3 gap-y-0.5">
          {categories.map((category) => (
            <div key={category.name} className="contents">
              <dt className="font-mono text-base-content/60">{category.name}</dt>
              <dd className="m-0 min-w-0 text-base-content/55">{category.description}</dd>
            </div>
          ))}
        </dl>
      )}
      {context && (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-base-200/60 p-2 font-mono leading-relaxed text-base-content/65">
          {context}
        </pre>
      )}
    </div>
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
        {command && <BoundedCode language="bash">{command}</BoundedCode>}
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
          <BoundedCode language={languageForPath(path)} title={path}>
            {content}
          </BoundedCode>
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
  if (step.tool === CLASSIFY_TOOL && args) {
    return <ClassifyArgsView args={args} />;
  }
  if (step.tool === CODEMODE_TOOL) {
    // The script, then what it printed and one line per tool call it made.
    const code = text(args?.code);
    return (
      <div>
        {code && <BoundedCode language="javascript">{code}</BoundedCode>}
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
      <ArgsView tool={step.tool} args={step.args} />
      <OutputPanel step={step} />
    </div>
  );
}
