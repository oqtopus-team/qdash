/**
 * Drive one pi process in RPC mode for a validation scenario.
 *
 * The driver sends one prompt, answers pi's dialogs through `onDialog` (the
 * harness's approval policy), and records what the model did: tool calls with
 * their arguments, how each ended, the approvals, and the final answer. It keeps
 * no tool result text, because a result may quote server output; a blocked or
 * declined call is classified from fixed messages instead.
 *
 * Framing follows pi's RPC contract: one JSON record per LF-terminated line,
 * split on LF only (Node's readline would also split on U+2028 and U+2029).
 */

import { type ChildProcessWithoutNullStreams, spawn } from "node:child_process";

import { isReviewedWriteTool } from "../../../packages/pi-qdash/extensions/lib/tool-policy.ts";
import { GUARD_MESSAGES } from "./guard-extension.ts";

export interface DialogRequest {
  id: string;
  method: "confirm" | "select" | "input" | "editor";
  title: string;
  message: string;
}

/** The reviewed-write tool call a confirm dialog belongs to, when the driver can tell. */
export interface PendingCall {
  toolCallId: string;
  toolName: string;
  args: Record<string, unknown>;
}

export interface DialogAnswer {
  confirmed: boolean;
  reason: string;
}

export type DialogHandler = (request: DialogRequest, call: PendingCall | undefined) => Promise<DialogAnswer>;

export type CallOutcome = "ok" | "error" | "guard_blocked" | "declined" | "not_finished";

export interface ToolCallRecord {
  toolCallId: string;
  toolName: string;
  args: Record<string, unknown>;
  outcome: CallOutcome;
  durationMs?: number;
}

export interface ApprovalRecord {
  title: string;
  toolName: string | null;
  toolCallId: string | null;
  confirmed: boolean;
  reason: string;
}

export interface RunTranscript {
  toolCalls: ToolCallRecord[];
  approvals: ApprovalRecord[];
  /** The model's last answer: its reported interpretation, not evidence. */
  finalText: string;
  settled: boolean;
  timedOut: boolean;
  aborted: boolean;
  exitCode: number | null;
  durationMs: number;
  totalTokens: number;
  extensionErrors: number;
  stderrLines: number;
}

export interface RunOptions {
  command: string;
  args: readonly string[];
  env: NodeJS.ProcessEnv;
  cwd?: string;
  prompt: string;
  timeoutMs: number;
  onDialog: DialogHandler;
  /** Grace period between closing stdin and killing the process. */
  shutdownGraceMs?: number;
}

const DECLINED = [/rejected by user/i, /requires explicit confirmation/i];
const MAX_ARG_STRING = 600;

/** A JSON copy of tool arguments with long strings cut, so a transcript stays small. */
export function compactArgs(value: unknown, depth = 0): unknown {
  if (typeof value === "string") return value.length > MAX_ARG_STRING ? `${value.slice(0, MAX_ARG_STRING)}...` : value;
  if (value === null || typeof value !== "object") return value;
  if (depth > 6) return "[nested]";
  if (Array.isArray(value)) return value.slice(0, 50).map((item) => compactArgs(item, depth + 1));
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, compactArgs(item, depth + 1)]));
}

function resultText(result: unknown): string {
  const content = (result as { content?: unknown } | undefined)?.content;
  if (!Array.isArray(content)) return "";
  return content.map((block) => (block && typeof block === "object" && (block as { type?: string }).type === "text" ? String((block as { text?: unknown }).text ?? "") : "")).join("\n");
}

/** How a finished tool call ended, from pi's flag and the fixed guard and approval messages. */
export function classifyOutcome(isError: boolean, result: unknown): CallOutcome {
  if (!isError) return "ok";
  const text = resultText(result);
  if (Object.values(GUARD_MESSAGES).some((message) => text.includes(message))) return "guard_blocked";
  if (DECLINED.some((pattern) => pattern.test(text))) return "declined";
  return "error";
}

function assistantText(message: unknown): string {
  const content = (message as { content?: unknown } | undefined)?.content;
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.map((block) => (block && typeof block === "object" && (block as { type?: string }).type === "text" ? String((block as { text?: unknown }).text ?? "") : "")).join("");
}

/** Split a byte stream into LF-terminated records. */
export function lineSplitter(onLine: (line: string) => void): (chunk: Buffer | string) => void {
  let buffer = "";
  return (chunk) => {
    buffer += chunk.toString();
    let index = buffer.indexOf("\n");
    while (index >= 0) {
      const line = buffer.slice(0, index).replace(/\r$/, "");
      buffer = buffer.slice(index + 1);
      if (line.trim() !== "") onLine(line);
      index = buffer.indexOf("\n");
    }
  };
}

export async function runPrompt(options: RunOptions): Promise<RunTranscript> {
  const started = Date.now();
  const child: ChildProcessWithoutNullStreams = spawn(options.command, [...options.args], {
    cwd: options.cwd,
    env: options.env,
    stdio: ["pipe", "pipe", "pipe"],
  });
  const transcript: RunTranscript = {
    toolCalls: [],
    approvals: [],
    finalText: "",
    settled: false,
    timedOut: false,
    aborted: false,
    exitCode: null,
    durationMs: 0,
    totalTokens: 0,
    extensionErrors: 0,
    stderrLines: 0,
  };
  const calls = new Map<string, ToolCallRecord>();
  const send = (record: unknown) => {
    if (!child.stdin.destroyed) child.stdin.write(`${JSON.stringify(record)}\n`);
  };

  let finish: () => void = () => {};
  const done = new Promise<void>((resolve) => {
    finish = resolve;
  });
  const exited = new Promise<void>((resolve) => {
    child.on("close", (code) => {
      transcript.exitCode = code;
      finish();
      resolve();
    });
    child.on("error", () => {
      finish();
      resolve();
    });
  });

  const pendingWrites = () =>
    [...calls.values()].filter((call) => call.outcome === "not_finished" && isReviewedWriteTool(call.toolName));

  const handleDialog = async (record: Record<string, unknown>) => {
    const method = String(record.method);
    const id = String(record.id);
    if (!["confirm", "select", "input", "editor"].includes(method)) return; // fire-and-forget
    const request: DialogRequest = {
      id,
      method: method as DialogRequest["method"],
      title: String(record.title ?? ""),
      message: String(record.message ?? ""),
    };
    if (method !== "confirm") {
      send({ type: "extension_ui_response", id, cancelled: true });
      transcript.approvals.push({ title: request.title, toolName: null, toolCallId: null, confirmed: false, reason: "only confirmations are answered" });
      return;
    }
    // A confirm belongs to the one unfinished reviewed write; with none or several, decline.
    const pending = pendingWrites();
    const call = pending.length === 1 ? { toolCallId: pending[0].toolCallId, toolName: pending[0].toolName, args: pending[0].args } : undefined;
    let answer: DialogAnswer;
    try {
      answer = call ? await options.onDialog(request, call) : { confirmed: false, reason: "the dialog could not be matched to one tool call" };
    } catch {
      answer = { confirmed: false, reason: "the approval policy failed" };
    }
    send({ type: "extension_ui_response", id, confirmed: answer.confirmed });
    transcript.approvals.push({
      title: request.title,
      toolName: call?.toolName ?? null,
      toolCallId: call?.toolCallId ?? null,
      confirmed: answer.confirmed,
      reason: answer.reason,
    });
  };

  const onRecord = (line: string) => {
    let record: Record<string, unknown>;
    try {
      record = JSON.parse(line) as Record<string, unknown>;
    } catch {
      return;
    }
    switch (record.type) {
      case "tool_execution_start": {
        const id = String(record.toolCallId);
        const entry: ToolCallRecord = {
          toolCallId: id,
          toolName: String(record.toolName),
          args: (compactArgs(record.args ?? {}) ?? {}) as Record<string, unknown>,
          outcome: "not_finished",
        };
        calls.set(id, entry);
        transcript.toolCalls.push(entry);
        break;
      }
      case "tool_execution_end": {
        const entry = calls.get(String(record.toolCallId));
        if (entry) {
          entry.outcome = classifyOutcome(record.isError === true, record.result);
          if (typeof record.durationMs === "number") entry.durationMs = record.durationMs;
        }
        break;
      }
      case "message_end": {
        const message = record.message as { role?: string; usage?: { totalTokens?: number } } | undefined;
        if (message?.role === "assistant") {
          const text = assistantText(message).trim();
          if (text) transcript.finalText = text;
          if (typeof message.usage?.totalTokens === "number") transcript.totalTokens += message.usage.totalTokens;
        }
        break;
      }
      case "extension_error":
        transcript.extensionErrors += 1;
        break;
      case "extension_ui_request":
        void handleDialog(record);
        break;
      case "agent_settled":
        transcript.settled = true;
        transcript.aborted = record.aborted === true;
        finish();
        break;
      case "response":
        if (record.command === "prompt" && record.success !== true) finish();
        break;
      default:
        break;
    }
  };

  child.stdout.on("data", lineSplitter(onRecord));
  child.stderr.on("data", lineSplitter(() => {
    transcript.stderrLines += 1;
  }));

  const timer = setTimeout(() => {
    transcript.timedOut = true;
    send({ type: "abort" });
    setTimeout(finish, 5000);
  }, options.timeoutMs);

  send({ id: "validation-prompt", type: "prompt", message: options.prompt });
  await done;
  clearTimeout(timer);

  child.stdin.end();
  const grace = setTimeout(() => child.kill("SIGTERM"), options.shutdownGraceMs ?? 10_000);
  const hard = setTimeout(() => child.kill("SIGKILL"), (options.shutdownGraceMs ?? 10_000) + 5000);
  await exited;
  clearTimeout(grace);
  clearTimeout(hard);
  transcript.durationMs = Date.now() - started;
  return transcript;
}
