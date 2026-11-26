/**
 * Read-only research subagents for the chat agent.
 *
 * `delegate_research` lets the chat model hand one to a few bounded,
 * read-only research tasks to child conversations and get their answers back
 * in one tool result. A child is a Pi conversation owned by the call's tool
 * task (pi-durable's subagent pattern): it lives in the chat's own store, runs
 * with the chat's model, and uses the same signed-in QDash connection as the
 * chat's own tools, because its tools are the same registrations. Stopping the
 * call, the turn, or the runtime aborts the children with it; nothing outlives
 * the call.
 *
 * What a child may do is decided at the executable boundary, not by its
 * prompt:
 *
 * - its agent enables exactly the audited read-only QDash tools (the ones Code
 *   Mode scripts may call, see tool-policy.ts) and selects only the `qdash`
 *   extension and the guard below, so it has no `codemode`, `tool_search`,
 *   workspace, `ask_user`, approval, page-edit, or `delegate_research` tool;
 * - those tools are offered to it directly (`modelTools`), deferred or not, so
 *   it never needs a discovery tool;
 * - the guard's hook blocks, in a child conversation, every call to a tool
 *   outside that set and every nested call, whatever the conversation's stored
 *   agent says. A conversation is a child when the creating commit marked it
 *   (`SubagentDoc`); the mark cannot be set by a model or a tool argument.
 *
 * Progress and results reach the chat through the call's `details`
 * (`{ subagents: { tasks } }`): the running slot carries them while the call
 * runs and the result entry keeps them, so a reload or reattach shows the same
 * tasks. The call is not replay-safe: a runtime restart ends it interrupted and
 * aborts its children, instead of running them again unseen.
 */

import type { Context } from "@earendil-works/chord/context";
import type { JsonValue } from "@earendil-works/chord/json";
import {
  AssistantEntry,
  configure,
  defineDoc,
  defineExtension,
  defineTool,
  hook,
  LiveDoc,
  ToolResultEntry,
  ToolTask,
  type ConversationId,
  type Extension,
  type HookApi,
  type ToolExecutionApi,
  type ToolHookCall,
  type ToolRegistration,
} from "@earendil-works/pi-durable";
import { investigationPolicyBullets } from "@oqtopus-team/pi-qdash/extensions/lib/qdash-guidance.ts";
import { Type } from "typebox";


/** The chat model's tool that starts subagents. */
export const SUBAGENT_TOOL = "delegate_research";
/** Name of the extension that brings `delegate_research`. */
export const SUBAGENT_EXTENSION = "qdash-subagents";
/** Name of the extension whose hook confines child conversations. */
export const SUBAGENT_GUARD_EXTENSION = "qdash-subagent-guard";

/** Research tasks one call may delegate. */
export const MAX_SUBAGENT_TASKS = 4;
/** Children of one call running at once; the rest wait in order. */
export const MAX_PARALLEL_SUBAGENTS = 3;
/** Children running at once in this process, over every chat; the rest wait for a slot. */
export const MAX_RUNNING_SUBAGENTS = 6;
/** Tool rounds one child takes at most before it must answer. */
export const SUBAGENT_MAX_TURNS = 8;
/** How long one child may run before it is stopped. */
const configuredTimeout = Number(process.env.AGENT_SUBAGENT_TIMEOUT_MS ?? 300_000);
export const SUBAGENT_TIMEOUT_MS = Number.isFinite(configuredTimeout) && configuredTimeout > 0
  ? Math.min(configuredTimeout, 2_147_483_647)
  : 300_000;
/** Longest task title kept. */
export const MAX_SUBAGENT_TITLE_CHARS = 80;
/** Longest task brief a child receives. */
export const MAX_SUBAGENT_PROMPT_CHARS = 4_000;
/** Longest answer of one child the chat model reads. */
export const MAX_SUBAGENT_RESULT_CHARS = 5_000;
/** Longest answer of one child the chat shows; the model's copy is bounded above. */
export const MAX_SUBAGENT_DETAIL_CHARS = 4_000;
/** Longest error text of one child. */
export const MAX_SUBAGENT_ERROR_CHARS = 400;
/** How often a running call reads its children's progress. */
const PROGRESS_POLL_MS = 750;

/** Where one delegated task stands, as the chat shows it. */
export type SubagentStatus = "queued" | "running" | "done" | "error" | "cancelled" | "interrupted";

/** One delegated task in the call's details: bounded, and never its tools' data or credentials. */
export interface SubagentTaskDetail {
  /** Its position in the call, from 1. */
  id: string;
  title: string;
  status: SubagentStatus;
  startedAt?: number;
  endedAt?: number;
  /** Tool calls the child made so far. */
  toolCalls: number;
  /** What the child is doing now, while it runs: a tool name, or `thinking`. */
  activity?: string;
  /** The child's answer, bounded. */
  result?: string;
  /** Why the child gave no answer, bounded. */
  error?: string;
}

/** What `delegate_research` keeps in its details. */
export interface SubagentDetails {
  subagents: { tasks: SubagentTaskDetail[] };
}

/**
 * Marks a conversation `delegate_research` created as a child, in the commit
 * that creates it. The guard reads it; nothing else writes it.
 */
export const SubagentDoc = defineDoc<{ child: boolean; parentCallId: string }>({
  kind: "qdash.subagent",
  version: 1,
  scope: "conversation",
  history: "latest",
  fork: "current",
  initial: () => ({ child: false, parentCallId: "" }),
  checkpointWhen: () => true,
});

/** What the model reads when a child tried a tool it may not call. */
export function subagentBlockMessage(name: string): string {
  return `${name} is not available to a research subagent: it may only call the read-only QDash tools it was given.`;
}

/** Whether the conversation of a hook call is a `delegate_research` child. */
async function isChild(api: Pick<HookApi, "conversationId" | "snapshot">, context: Context): Promise<boolean> {
  const mark = await api.snapshot(SubagentDoc, api.conversationId, context);
  return mark?.child === true;
}

/**
 * The guard: in a child conversation, only a model call to one of `allowed`
 * runs. Nested calls are blocked too, since no allowed tool makes one and a
 * tool that did would act outside the child's own calls. Conversations that
 * are not children are left alone.
 */
export function subagentGuardExtension(allowed: Iterable<string>): Extension {
  const names = new Set(allowed);
  return defineExtension({
    name: SUBAGENT_GUARD_EXTENSION,
    hooks: [
      hook(ToolTask, {
        beforeTool: async (call: ToolHookCall, api: HookApi, context: Context) => {
          if (!(await isChild(api, context))) return undefined;
          if (call.parent === undefined && names.has(call.name)) return undefined;
          console.warn(`[agent-runtime] blocked subagent call to ${call.name}`);
          return { block: subagentBlockMessage(call.name) };
        },
      }),
    ],
  });
}

/** What a child reads as its instructions, besides its brief. */
export function subagentInstructions(): string {
  return [
    "You are a read-only research subagent of QDash Agent. The main assistant gave you one bounded research task; your final answer goes back to it, not to the user.",
    "",
    "Rules:",
    "- Use only the QDash read tools you are offered. You cannot write to QDash, run code or shell commands, ask the user anything, request approvals, or delegate further.",
    "- Stay within the task. When it is ambiguous, state the assumption you made instead of asking.",
    "- Answer with findings only: the identifiers, values, units, and timestamps the tools returned, and what was missing or failed. Do not invent values.",
    "- Keep the answer under about 300 words. Plain text or a compact Markdown list; no greetings.",
    // A subagent has no skills to read; the rules that point at one stay with the main assistant.
    ...investigationPolicyBullets().filter((rule) => !/\bskill\b/.test(rule)),
  ].join("\n");
}

const TaskParameter = Type.Object({
  title: Type.String({
    description: `A short label for the task, shown to the user (up to ${MAX_SUBAGENT_TITLE_CHARS} characters).`,
  }),
  prompt: Type.String({
    description:
      "The complete, self-contained brief: what to find, for which chip, qubits, tasks or time range, and what to report. The subagent sees nothing else of this chat.",
  }),
});

const SubagentParameters = Type.Object({
  tasks: Type.Array(TaskParameter, {
    minItems: 1,
    maxItems: MAX_SUBAGENT_TASKS,
    description: `1 to ${MAX_SUBAGENT_TASKS} independent read-only research tasks, run in parallel.`,
  }),
});

/** Guideline for the chat's system prompt. */
export const SUBAGENT_GUIDELINE = `- \`${SUBAGENT_TOOL}\` runs 1-${MAX_SUBAGENT_TASKS} independent read-only research tasks in parallel, each in its own subagent with the QDash read tools, and returns their findings. Use it when a question splits into separate lookups (for example several chips, qubits, or time ranges) that each need a few tool calls; call tools directly for one or two lookups. Give each task a complete brief, since a subagent sees nothing else of this chat. Subagents cannot write, run code, ask the user, or request approvals; check their findings against each other and answer the user yourself.`;

/** Suffix for an unanswered submission's detail (as `formatSettledDetail` in events.ts). */
function settledDetail(detail: unknown): string {
  if (detail === undefined || detail === null || detail === "") return "";
  return `: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`;
}

const STATUSES = new Set<SubagentStatus>(["queued", "running", "done", "error", "cancelled", "interrupted"]);

/**
 * The delegated tasks of a `delegate_research` call's details, when well-formed:
 * only the known fields, bounded, for the chat. Anything else yields nothing.
 */
export function subagentsFromDetails(details: unknown): SubagentTaskDetail[] | undefined {
  const tasks = (details as { subagents?: { tasks?: unknown } } | undefined)?.subagents?.tasks;
  if (!Array.isArray(tasks) || tasks.length === 0) return undefined;
  const out: SubagentTaskDetail[] = [];
  for (const raw of tasks.slice(0, MAX_SUBAGENT_TASKS)) {
    if (!raw || typeof raw !== "object") continue;
    const task = raw as Record<string, unknown>;
    const status = task.status as SubagentStatus;
    if (typeof task.id !== "string" || typeof task.title !== "string" || !STATUSES.has(status)) continue;
    const time = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? value : undefined);
    const startedAt = time(task.startedAt);
    const endedAt = time(task.endedAt);
    const calls = time(task.toolCalls);
    out.push({
      id: task.id.slice(0, 8),
      title: clip(task.title, MAX_SUBAGENT_TITLE_CHARS),
      status,
      toolCalls: calls === undefined ? 0 : Math.max(0, Math.floor(calls)),
      ...(startedAt !== undefined ? { startedAt } : {}),
      ...(endedAt !== undefined ? { endedAt } : {}),
      ...(typeof task.activity === "string" && task.activity ? { activity: task.activity.slice(0, 80) } : {}),
      ...(typeof task.result === "string" && task.result ? { result: clip(task.result, MAX_SUBAGENT_DETAIL_CHARS) } : {}),
      ...(typeof task.error === "string" && task.error ? { error: clip(task.error, MAX_SUBAGENT_ERROR_CHARS) } : {}),
    });
  }
  return out.length ? out : undefined;
}

function clip(text: string, max: number): string {
  const trimmed = text.trim();
  return trimmed.length > max ? `${trimmed.slice(0, max)}…` : trimmed;
}

/** Concatenated text blocks of an assistant message. */
function assistantText(message: unknown): string {
  const content = (message as { content?: unknown } | undefined)?.content;
  if (!Array.isArray(content)) return "";
  return content
    .map((block) => (block && typeof block === "object" && block.type === "text" ? String(block.text ?? "") : ""))
    .join("");
}

/** A process-wide count of running children, with waiters in order. */
class ChildSlots {
  #running = 0;
  readonly #waiting: Array<() => void> = [];
  constructor(readonly limit: number) {}

  get running(): number {
    return this.#running;
  }

  /** Wait for a slot; rejects when `signal` aborts first. */
  async acquire(signal: AbortSignal | undefined): Promise<() => void> {
    if (signal?.aborted) throw signal.reason ?? new Error("aborted");
    if (this.#running >= this.limit) {
      await new Promise<void>((resolve, reject) => {
        const wake = () => {
          signal?.removeEventListener("abort", onAbort);
          resolve();
        };
        const onAbort = () => {
          const index = this.#waiting.indexOf(wake);
          if (index !== -1) this.#waiting.splice(index, 1);
          reject(signal?.reason ?? new Error("aborted"));
        };
        this.#waiting.push(wake);
        signal?.addEventListener("abort", onAbort, { once: true });
      });
    } else {
      this.#running += 1;
    }
    let released = false;
    return () => {
      if (released) return;
      released = true;
      const next = this.#waiting.shift();
      // Transfer the reserved slot before another caller can acquire it.
      if (next) next();
      else this.#running -= 1;
    };
  }
}

const slots = new ChildSlots(MAX_RUNNING_SUBAGENTS);

/** Children running now in this process, for tests and logs. */
export function runningSubagentCount(): number {
  return slots.running;
}

/** What `delegate_research` needs of the chat's registry. */
export interface SubagentParts {
  /** The chat's `qdash` extension, which brings the children's tools. */
  qdash: Extension;
  /** The audited read-only tools a child may call, from that extension. */
  readTools: readonly ToolRegistration[];
  /** From `subagentGuardExtension`, installed in the same registry. */
  guard: Extension;
}

/** One delegated task as the call runs it. */
interface DelegatedTask {
  index: number;
  title: string;
  prompt: string;
}

/** Run each of `items` with at most `limit` at once, in order of `items`. */
async function inPool<T>(items: readonly T[], limit: number, run: (item: T) => Promise<void>): Promise<void> {
  let next = 0;
  const lanes = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const item = items[next++];
      await run(item);
    }
  });
  await Promise.all(lanes);
}

/** The text the chat model reads for the call's children. */
export function subagentReport(tasks: readonly SubagentTaskDetail[], answers: ReadonlyMap<string, string>): string {
  const done = tasks.filter((task) => task.status === "done").length;
  const lines = [
    `[QDash runtime] ${tasks.length} research subagent${tasks.length === 1 ? "" : "s"}: ${done} answered${
      done < tasks.length ? `, ${tasks.length - done} did not` : ""
    }. Their findings come from read-only QDash tools; reconcile them and answer the user yourself.`,
  ];
  for (const task of tasks) {
    const calls = `${task.toolCalls} tool call${task.toolCalls === 1 ? "" : "s"}`;
    lines.push("", `## Task ${task.id}: ${task.title} (${task.status}, ${calls})`);
    if (task.status === "done") lines.push(answers.get(task.id) || "(empty answer)");
    else lines.push(`No answer: ${task.error ?? task.status}`);
  }
  return lines.join("\n");
}

/**
 * The `delegate_research` tool and its extension. Install it with `parts.guard`
 * and `parts.qdash` in the same registry.
 */
export function buildSubagentExtension(parts: SubagentParts): Extension {
  const tool = defineTool({
    name: SUBAGENT_TOOL,
    description: `Delegate 1-${MAX_SUBAGENT_TASKS} independent, read-only QDash research tasks to subagents that run in parallel, and get their findings back. Each subagent runs with this chat's model and the user's QDash access, but only the read-only QDash tools: it cannot write, run code, ask the user, or request approvals. Give each task a short title and a complete, self-contained brief; the subagent sees nothing else of this chat.`,
    parameters: SubagentParameters,
    // A restart ends the call interrupted and aborts its children, instead of
    // running them again with no one watching.
    replay: "unsafe",
    callers: ["model"],
    // One delegation at a time per conversation keeps a round within the per-call bound.
    executionMode: "sequential",
    execute: async (args, api, context) => runDelegation(args, api as ToolExecutionApi, context, parts),
  });
  return defineExtension({ name: SUBAGENT_EXTENSION, tools: [tool as ToolRegistration] });
}

async function runDelegation(
  args: { tasks: Array<{ title: string; prompt: string }> },
  api: ToolExecutionApi,
  context: Context,
  parts: SubagentParts,
) {
  const tasks: DelegatedTask[] = args.tasks.slice(0, MAX_SUBAGENT_TASKS).map((task, index) => ({
    index,
    title: clip(task.title, MAX_SUBAGENT_TITLE_CHARS) || `Task ${index + 1}`,
    prompt: clip(task.prompt, MAX_SUBAGENT_PROMPT_CHARS),
  }));
  const state: SubagentTaskDetail[] = tasks.map((task) => ({
    id: String(task.index + 1),
    title: task.title,
    status: "queued",
    toolCalls: 0,
  }));
  const answers = new Map<string, string>();
  const signal = context.abortSignal;

  // Details are committed one at a time, newest state last; none after the call returns.
  let closed = false;
  let publishing: Promise<void> = Promise.resolve();
  let dirty = false;
  const publish = (): Promise<void> => {
    dirty = true;
    publishing = publishing.then(async () => {
      if (!dirty || closed) return;
      dirty = false;
      const value = { subagents: { tasks: state.map((task) => ({ ...task })) } };
      await api.details(value as unknown as JsonValue, context).catch(() => undefined);
    });
    return publishing;
  };

  await publish();
  const runOne = async (task: DelegatedTask): Promise<void> => {
    const detail = state[task.index];
    if (signal?.aborted) {
      detail.status = "cancelled";
      return;
    }
    let release: (() => void) | undefined;
    try {
      release = await slots.acquire(signal);
    } catch {
      detail.status = "cancelled";
      return;
    }
    let poll: ReturnType<typeof setInterval> | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let timedOut = false;
    try {
      const childId: ConversationId = await api.commit(async (tx) => {
        const created = await tx.createConversation({ ownership: { kind: "task", taskId: api.taskId } });
        const mark = await tx.doc(SubagentDoc, created.id);
        mark.child = true;
        mark.parentCallId = api.callId;
        await configure(tx, created.id, {
          extensions: [parts.qdash, parts.guard],
          tools: parts.readTools,
          modelTools: parts.readTools,
          instructions: subagentInstructions(),
          maxTurns: SUBAGENT_MAX_TURNS,
        });
        return created.id;
      }, context);
      const child = await api.conversation(childId, context);
      if (!child) throw new Error("the subagent's conversation could not be opened");
      detail.status = "running";
      detail.startedAt = api.now();
      detail.activity = "thinking";
      await publish();

      const seen = new Set<string>();
      const readProgress = async () => {
        const live = await api.snapshot(LiveDoc, childId, context).catch(() => undefined);
        if (!live || detail.status !== "running") return;
        for (const slot of live.tools ?? []) seen.add(slot.callId);
        const runningTool = (live.tools ?? []).find((slot) => slot.status === "running" || slot.status === "pending");
        const activity = runningTool ? runningTool.name : live.generation ? "thinking" : detail.activity;
        if (seen.size !== detail.toolCalls || activity !== detail.activity) {
          detail.toolCalls = Math.max(detail.toolCalls, seen.size);
          detail.activity = activity;
          await publish();
        }
      };
      poll = setInterval(() => void readProgress(), PROGRESS_POLL_MS);
      if (SUBAGENT_TIMEOUT_MS > 0) {
        timer = setTimeout(() => {
          timedOut = true;
          void child.abort(context).catch(() => undefined);
        }, SUBAGENT_TIMEOUT_MS);
      }

      const submission = await child.submit(
        { type: "input", content: task.prompt, requestId: `subagent:${api.callId}:${task.index + 1}` },
        context,
      );
      const settled = await submission.wait(context);
      clearInterval(poll);
      poll = undefined;

      const { answer, calls } = await api.commit(async (tx) => {
        const page = await tx.scanEntries({ conversationId: childId }, 500);
        const calls = page.items.filter((entry) => ToolResultEntry.is(entry)).length;
        if (settled.status !== "done" || settled.type !== "input") return { answer: "", calls };
        const entry = await tx.entry(AssistantEntry, settled.answer);
        return { answer: assistantText(entry?.model?.[0]), calls };
      }, context);
      detail.toolCalls = calls;
      detail.endedAt = api.now();
      delete detail.activity;
      if (settled.status === "done") {
        detail.status = "done";
        answers.set(detail.id, clip(answer, MAX_SUBAGENT_RESULT_CHARS));
        detail.result = clip(answer, MAX_SUBAGENT_DETAIL_CHARS);
      } else {
        detail.status = signal?.aborted ? "cancelled" : "error";
        detail.error = clip(
          timedOut
            ? `stopped after ${Math.round(SUBAGENT_TIMEOUT_MS / 1000)} s without an answer`
            : settled.reason === "turn_limit"
              ? `reached its limit of ${SUBAGENT_MAX_TURNS} tool rounds without an answer`
              : `not answered: ${settled.reason}${settledDetail(settled.detail)}`,
          MAX_SUBAGENT_ERROR_CHARS,
        );
      }
    } catch (error) {
      detail.endedAt = api.now();
      delete detail.activity;
      if (signal?.aborted) {
        detail.status = "cancelled";
      } else {
        detail.status = "error";
        detail.error = clip(error instanceof Error ? error.message : String(error), MAX_SUBAGENT_ERROR_CHARS);
      }
    } finally {
      if (poll) clearInterval(poll);
      if (timer) clearTimeout(timer);
      release?.();
      await publish();
    }
  };

  try {
    await inPool(tasks, MAX_PARALLEL_SUBAGENTS, runOne);
  } finally {
    await publishing;
    closed = true;
  }
  if (signal?.aborted) throw signal.reason ?? new Error(`${SUBAGENT_TOOL} was stopped`);
  const details: SubagentDetails = { subagents: { tasks: state } };
  const answered = state.some((task) => task.status === "done");
  return {
    output: [{ type: "text" as const, text: subagentReport(state, answers) }],
    details: details as unknown as JsonValue,
    ...(answered ? {} : { isError: true }),
  };
}
