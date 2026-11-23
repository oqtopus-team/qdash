/**
 * Live state of a running turn across windows and reloads.
 *
 * The fake API below behaves like `chat_turn_runs.py`: one run per turn, whose
 * events every stream of the turn (the request itself, a reattach, another window's
 * follow) gets from the start and then live, while the server records the turn in
 * the session (`turn_request_id` on each message, the session's `turn`). Only the
 * request that starts a turn submits anything.
 */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { chatStatus } from "@/components/features/chat/ChatTurnStatus";
import {
  CopilotChatSessionProvider,
  useCopilotChatSessionContext,
} from "@/contexts/CopilotChatSessionContext";
import { turnStartOf } from "@/lib/copilotObservedTurn";
import { readStoredTurns, storeTurn } from "@/lib/copilotTurnStore";
import type { ChatMessage, CopilotBlocksResult, TraceStep } from "@/types/copilotChat";

import { useCopilotChat } from "../useCopilotChat";

vi.mock("@/client/copilot/copilot", () => ({
  useGetCopilotConfig: () => ({ data: undefined }),
}));

const WAIT = "qdash_wait_agent_intervention";
const GET = "qdash_get";
const UNPLACEABLE = /cannot be shown here/;

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

type Message = Record<string, unknown> & { role: string; content: string };
interface Subscriber {
  push: (text: string) => void;
  close: () => void;
}
interface Run {
  requestId: string;
  sessionId: string;
  events: string[];
  subscribers: Set<Subscriber>;
  done: boolean;
  steps: { id: string; tool: string; status: string }[];
}
interface Recorded {
  request_id: string;
  project_id: string | null;
  status: string;
  start_index: number;
  continuing: boolean;
  started_at: string;
}
interface Call {
  url: string;
  method: string;
  body: Record<string, unknown>;
  project: string | undefined;
}

let calls: Call[];
let saved: Record<string, Message[]>;
let recorded: Record<string, Recorded | null>;
let runs: Map<string, Run>;
/** Turns the runtime runs now, by session: what `/chat/active` reports. */
let runtime: Record<string, string | undefined>;
/** What the runtime replays for a turn whose API run is gone (it restarted). */
let stored: Map<string, string[]>;
/** When set, answers `/chat/active` in place of the runtime (an outage, a slow reply). */
let activeReply: ((sessionId: string) => Response | Promise<Response>) | null;
/** The project the provider is in (the open project). */
let project: string;

const iso = (ms: number) => new Date(ms).toISOString();

function subscribe(run: Run, signal: AbortSignal | null | undefined): Response {
  const encoder = new TextEncoder();
  let sub!: Subscriber;
  let fail!: (reason: unknown) => void;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      fail = (reason) => controller.error(reason);
      sub = {
        push: (text) => controller.enqueue(encoder.encode(text)),
        close: () => controller.close(),
      };
      for (const event of run.events) sub.push(event);
      if (run.done) sub.close();
      else run.subscribers.add(sub);
    },
  });
  // Closing the response only unsubscribes; the run goes on.
  signal?.addEventListener("abort", () => {
    run.subscribers.delete(sub);
    fail(signal.reason);
  });
  return new Response(body, { status: 200 });
}

/** The turn's run as the server stores it: its own message, then its progress. */
function runMessages(run: Run, end?: Message): Message[] {
  const start = recorded[run.sessionId]!.start_index;
  const own = saved[run.sessionId].slice(start).filter((m) => m.turn_request_id === run.requestId);
  const head = own.filter((m) => m.role === "user");
  if (end) return [...head, end];
  if (run.steps.length === 0) return head;
  return [
    ...head,
    {
      role: "assistant",
      content: JSON.stringify({
        blocks: [],
        assessment: null,
        in_progress: true,
        trace: { steps: run.steps.map((s) => ({ kind: "tool", ...s, startedAt: 1 })) },
      }),
      turn_request_id: run.requestId,
    },
  ];
}

function writeRun(run: Run, end?: Message) {
  const start = recorded[run.sessionId]!.start_index;
  saved[run.sessionId] = [...saved[run.sessionId].slice(0, start), ...runMessages(run, end)];
}

/** The runtime sends one event of turn `requestId`; the server keeps its progress. */
function emit(requestId: string, event: string, data: Record<string, unknown>) {
  const run = runs.get(requestId)!;
  const chunk = sse(event, data);
  run.events.push(chunk);
  if (event === "tool_start") {
    run.steps.push({ id: String(data.id), tool: String(data.tool), status: "running" });
  } else if (event === "tool_end") {
    run.steps = run.steps.map((s) => (s.id === data.id ? { ...s, status: "done" } : s));
  }
  if (event === "tool_start" || event === "tool_end") writeRun(run);
  for (const sub of run.subscribers) sub.push(chunk);
}

/** The turn ends: the server writes its end, reports it, and closes every stream. */
function end(requestId: string, how: "completed" | "stopped", text: string) {
  const run = runs.get(requestId)!;
  const payload: CopilotBlocksResult =
    how === "completed"
      ? { blocks: [{ type: "text", content: text, chart: null }], assessment: null }
      : { blocks: [{ type: "text", content: text, chart: null }], assessment: null, stopped: true };
  const last: Message = {
    role: "assistant",
    content: JSON.stringify(payload),
    turn_request_id: requestId,
  };
  const terminal =
    how === "completed"
      ? sse("result", { ...payload, entry_id: "9" })
      : sse("error", { detail: "Stopped by the user" });
  writeRun(run, last);
  recorded[run.sessionId] = { ...recorded[run.sessionId]!, status: how };
  runtime[run.sessionId] = undefined;
  const transcript = sse("transcript", {
    saved: true,
    request_id: requestId,
    messages: runMessages(run, last),
  });
  for (const chunk of [terminal, transcript]) {
    run.events.push(chunk);
    for (const sub of run.subscribers) sub.push(chunk);
  }
  run.done = true;
  for (const sub of run.subscribers) sub.close();
  run.subscribers.clear();
}

function newRun(sessionId: string, requestId: string): Run {
  const run: Run = {
    requestId,
    sessionId,
    events: [],
    subscribers: new Set(),
    done: false,
    steps: [],
  };
  runs.set(requestId, run);
  return run;
}

beforeEach(() => {
  calls = [];
  saved = {
    s1: [
      { role: "user", content: "Hi" },
      { role: "assistant", content: "Hello" },
    ],
  };
  recorded = { s1: null };
  runs = new Map();
  runtime = {};
  stored = new Map();
  activeReply = null;
  project = "p1";
  localStorage.setItem("qdash_current_project_id", "p1");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      const method = init?.method ?? "GET";
      const asked = ((init?.headers ?? {}) as Record<string, string>)["X-Project-Id"];
      calls.push({ url, method, body, project: asked });
      if (url.endsWith("/stream")) {
        const sessionId = String(body.session_id);
        const requestId = String(body.request_id);
        let run = runs.get(requestId);
        if (!body.reattach) {
          // The claim: the saved chat becomes the turn's start and its own message.
          const start = body.turn_start as { index: number };
          saved[sessionId] = [
            ...saved[sessionId].slice(0, start.index),
            ...(body.continue_run
              ? []
              : [{ role: "user", content: String(body.message), turn_request_id: requestId }]),
          ];
          recorded[sessionId] = {
            request_id: requestId,
            project_id: "p1",
            status: "running",
            start_index: start.index,
            continuing: body.continue_run === true,
            started_at: iso(Date.now()),
          };
          runtime[sessionId] = requestId;
          run = newRun(sessionId, requestId);
        } else if (!run && stored.has(requestId)) {
          // The API restarted: the reattach opens a new run, which the runtime replays.
          run = newRun(sessionId, requestId);
          run.events.push(...stored.get(requestId)!);
          run.done = true;
        }
        if (!run) return new Response("no such turn", { status: 404 });
        return subscribe(run, init?.signal);
      }
      if (url.endsWith("/copilot/chat/active")) {
        const sessionId = String(body.session_id);
        if (activeReply) return activeReply(sessionId);
        const requestId = runtime[sessionId];
        const record = recorded[sessionId];
        if (!requestId || !record) return Response.json({ running: false });
        // As the runtime does: a turn of another project is not named.
        if (record.project_id !== asked)
          return Response.json({ running: true, other_project: true });
        const messages = saved[sessionId] as unknown as ChatMessage[];
        const own = record.continuing ? null : messages[record.start_index];
        return Response.json({
          running: true,
          turn_request_id: requestId,
          continuing: record.continuing,
          started_at: Date.parse(record.started_at),
          turn_start: turnStartOf(messages.slice(0, record.start_index), own ?? null),
        });
      }
      if (url.endsWith("/copilot/chat/stop")) {
        const requestId = String(body.turn_request_id);
        if (runs.get(requestId) && !runs.get(requestId)!.done) {
          end(requestId, "stopped", "Partial answer");
        }
        return Response.json({ stopped: true });
      }
      if (url.endsWith("/copilot/chat/sessions") && method === "GET") {
        return Response.json({
          sessions: Object.keys(saved).map((id) => ({
            session_id: id,
            title: "Chat",
            message_count: saved[id].length,
            created_at: "2026-11-22T00:00:00Z",
            updated_at: "2026-11-22T00:00:00Z",
          })),
        });
      }
      const match = /\/copilot\/chat\/sessions\/([^/]+)$/.exec(url);
      if (match && method === "GET") {
        return Response.json({
          session_id: match[1],
          title: "Chat",
          message_count: saved[match[1]]?.length ?? 0,
          created_at: "2026-11-22T00:00:00Z",
          updated_at: "2026-11-22T00:00:00Z",
          messages: saved[match[1]] ?? [],
          // As the API does: the turn is named only in the project it was sent from.
          turn: recorded[match[1]]?.project_id === asked ? recorded[match[1]] : null,
        });
      }
      if (match && method === "PATCH") return Response.json({});
      return Response.json({});
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

const wrapper = ({ children }: { children: ReactNode }) => (
  <CopilotChatSessionProvider owner="alice" project={project}>
    {children}
  </CopilotChatSessionProvider>
);

/** The user switches the open project. */
function switchProject(w: Window, to: string) {
  project = to;
  localStorage.setItem("qdash_current_project_id", to);
  w.rerender();
}

function useWindow() {
  const store = useCopilotChatSessionContext();
  const chat = useCopilotChat("s1");
  const session = store.sessions.find((s) => s.id === "s1");
  const status = session
    ? chatStatus({
        run: store.runs.s1,
        detached: store.detachedTurns.s1 ?? null,
        messages: session.messages,
      })
    : null;
  return { chat, store, status };
}

/** A browser window showing chat s1. */
async function openWindow() {
  const hook = renderHook(useWindow, { wrapper });
  await waitFor(() => expect(hook.result.current.store.isLoadingSessions).toBe(false));
  act(() => hook.result.current.store.switchSession("s1"));
  await waitFor(() => expect(hook.result.current.chat.session?.messagesLoaded).toBe(true));
  return hook;
}
type Window = Awaited<ReturnType<typeof openWindow>>;

const submissions = () => calls.filter((c) => c.url.endsWith("/stream") && !c.body.reattach);
const reattaches = () => calls.filter((c) => c.url.endsWith("/stream") && c.body.reattach);
const tools = (w: Window) =>
  (w.result.current.chat.liveTurn?.steps ?? []).flatMap((s: TraceStep) =>
    s.kind === "tool" ? [`${s.tool}:${s.status}`] : [],
  );
const contents = (w: Window) => w.result.current.chat.messages.map((m) => m.content);
const inProgressShown = (w: Window) =>
  w.result.current.chat.messages.some((m) => m.content.includes('"in_progress":true'));
const lastAnswer = (w: Window) => {
  const messages = w.result.current.chat.messages;
  return JSON.parse(messages[messages.length - 1].content) as CopilotBlocksResult;
};

async function send(w: Window, text: string) {
  act(() => {
    w.result.current.chat.send(text);
  });
  await waitFor(() => expect(submissions()).toHaveLength(1));
  return String(submissions()[0].body.request_id);
}

/** Both windows show the same live step list and status. */
async function bothShow(windows: Window[], steps: string[], status: string) {
  for (const w of windows) {
    await waitFor(() => expect(tools(w)).toEqual(steps));
    await waitFor(() => expect(w.result.current.status?.kind).toBe(status));
  }
}

describe("a running turn in every window showing its chat", () => {
  it("follows each tool, the wait, and the end live in the sending and a late window", async () => {
    const sender = await openWindow();
    const turn = await send(sender, "Calibrate Q0");
    emit(turn, "tool_start", { id: "c1", tool: GET, label: "Get" });
    emit(turn, "tool_end", { id: "c1", tool: GET, label: "Get", is_error: false });
    emit(turn, "tool_start", { id: "w1", tool: WAIT, label: "Wait" });
    await bothShow([sender], [`${GET}:done`, `${WAIT}:running`], "waiting_expert");

    // A second window opens the chat while the turn waits. Its tab has no pointer.
    sessionStorage.clear();
    const late = await openWindow();
    // It recovers the current live state (not a static saved bubble) and stays subscribed.
    await bothShow([sender, late], [`${GET}:done`, `${WAIT}:running`], "waiting_expert");
    expect(inProgressShown(late)).toBe(false);
    expect(contents(late)).toEqual(["Hi", "Hello", "Calibrate Q0"]);

    // The expert answers: both move from waiting to running the next tool, as it happens.
    emit(turn, "tool_end", { id: "w1", tool: WAIT, label: "Wait", is_error: false });
    emit(turn, "tool_start", { id: "c2", tool: GET, label: "Get" });
    await bothShow([sender, late], [`${GET}:done`, `${WAIT}:done`, `${GET}:running`], "working");

    emit(turn, "tool_end", { id: "c2", tool: GET, label: "Get", is_error: false });
    end(turn, "completed", "Q0 is calibrated.");
    for (const w of [sender, late]) {
      await waitFor(() => expect(w.result.current.chat.isStreaming).toBe(false));
      expect(w.result.current.status?.kind).toBe("answered");
      expect(lastAnswer(w).blocks[0].content).toBe("Q0 is calibrated.");
    }
    // One submission; the late window only reattached, which submits nothing.
    expect(submissions()).toHaveLength(1);
    expect(reattaches().every((c) => c.body.message === "")).toBe(true);
  });

  it("shows a stop from one window in both", async () => {
    const sender = await openWindow();
    const turn = await send(sender, "Calibrate Q0");
    emit(turn, "tool_start", { id: "w1", tool: WAIT, label: "Wait" });
    sessionStorage.clear();
    const late = await openWindow();
    await bothShow([sender, late], [`${WAIT}:running`], "waiting_expert");

    // The late window stops the turn it follows.
    act(() => late.result.current.chat.stop());
    for (const w of [sender, late]) {
      await waitFor(() => expect(w.result.current.chat.isStreaming).toBe(false));
      await waitFor(() => expect(w.result.current.status?.kind).toBe("stopped"));
    }
    expect(submissions()).toHaveLength(1);
  });

  it("is announced by the sending window and followed at once by one already showing the chat", async () => {
    // What the sending window tells the other windows of this browser.
    const heard: unknown[] = [];
    const listener = new BroadcastChannel("qdash.copilot.turns.v1");
    listener.onmessage = (event) => heard.push(event.data);
    try {
      const sender = await openWindow();
      await send(sender, "Calibrate Q0");
      await waitFor(() => expect(heard).toEqual([{ owner: "alice", sessionId: "s1" }]));
    } finally {
      listener.close();
    }
    cleanup();
    sessionStorage.clear();
    calls = [];
    runs.clear();

    // A window that already shows the chat, idle, while another tab (its own session
    // storage) starts a turn: it follows on the announcement, not at its next check (15 s).
    saved.s1 = saved.s1.slice(0, 2);
    const idle = await openWindow();
    await waitFor(() =>
      expect(calls.some((c) => c.url.endsWith("/copilot/chat/active"))).toBe(true),
    );
    saved.s1 = [...saved.s1, { role: "user", content: "Calibrate Q1", turn_request_id: "r-tab" }];
    recorded.s1 = {
      request_id: "r-tab",
      project_id: "p1",
      status: "running",
      start_index: 2,
      continuing: false,
      started_at: iso(Date.now()),
    };
    runtime.s1 = "r-tab";
    newRun("s1", "r-tab");
    emit("r-tab", "tool_start", { id: "w1", tool: WAIT, label: "Wait" });
    const announce = new BroadcastChannel("qdash.copilot.turns.v1");
    announce.postMessage({ owner: "alice", sessionId: "s1" });
    announce.close();
    await waitFor(() => expect(tools(idle)).toEqual([`${WAIT}:running`]), { timeout: 2_000 });
    end("r-tab", "completed", "Done.");
    await waitFor(() => expect(idle.result.current.status?.kind).toBe("answered"));
    expect(submissions()).toHaveLength(0);
  });

  it("ignores an announcement of another user", async () => {
    const idle = await openWindow();
    await waitFor(() =>
      expect(calls.some((c) => c.url.endsWith("/copilot/chat/active"))).toBe(true),
    );
    const before = calls.length;
    const announce = new BroadcastChannel("qdash.copilot.turns.v1");
    announce.postMessage({ owner: "mallory", sessionId: "s1" });
    announce.close();
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(calls.slice(before).filter((c) => c.url.endsWith("/copilot/chat/active"))).toEqual([]);
    expect(idle.result.current.chat.isStreaming).toBe(false);
  });
});

describe("a reload of the window that sent the turn", () => {
  /** What the server saved of a multi-tool turn caught mid-wait, as #1919 wrote it. */
  function savedMidTurn(requestId: string): Message[] {
    return [
      { role: "user", content: "Hi" },
      { role: "assistant", content: "Hello" },
      { role: "user", content: "Calibrate Q0", turn_request_id: requestId },
      {
        role: "assistant",
        content: JSON.stringify({
          blocks: [],
          assessment: null,
          in_progress: true,
          trace: {
            steps: [
              { kind: "tool", id: "c1", tool: GET, status: "done", startedAt: 1, endedAt: 2 },
              { kind: "tool", id: "w1", tool: WAIT, status: "done", startedAt: 1, endedAt: 2 },
              { kind: "tool", id: "c2", tool: GET, status: "cancelled", startedAt: 2 },
            ],
            durationMs: 2000,
          },
        }),
        turn_request_id: requestId,
      },
    ];
  }

  /** The turn runs on in the runtime with this history; the reload reattaches to it. */
  function runningTurn(requestId: string, start: number) {
    saved.s1 = savedMidTurn(requestId);
    recorded.s1 = {
      request_id: requestId,
      project_id: "p1",
      status: "running",
      start_index: start,
      continuing: false,
      started_at: iso(Date.now() - 5_000),
    };
    runtime.s1 = requestId;
    const run = newRun("s1", requestId);
    emit(requestId, "tool_start", { id: "c1", tool: GET, label: "Get" });
    emit(requestId, "tool_end", { id: "c1", tool: GET, label: "Get", is_error: false });
    emit(requestId, "tool_start", { id: "w1", tool: WAIT, label: "Wait" });
    saved.s1 = savedMidTurn(requestId);
    return run;
  }

  it("reattaches by the turn's identity when the remembered position no longer fits", async () => {
    // The tab remembered the turn one message off (a steer or a recovered run moved
    // it): #1919 then said "its message was not saved" over the server's progress.
    runningTurn("r1", 2);
    storeTurn("alice", {
      sessionId: "s1",
      requestId: "r1",
      projectId: "p1",
      start: 3,
      continuing: false,
      startedAt: Date.now() - 5_000,
    });
    const reloaded = await openWindow();
    await waitFor(() => expect(tools(reloaded)).toEqual([`${GET}:done`, `${WAIT}:running`]));
    expect(reloaded.result.current.status?.kind).toBe("waiting_expert");
    expect(reloaded.result.current.chat.notice).toBeNull();
    // The live answer replaces the saved progress, which is not shown as a static bubble.
    expect(inProgressShown(reloaded)).toBe(false);
    expect(contents(reloaded)).toEqual(["Hi", "Hello", "Calibrate Q0"]);

    emit("r1", "tool_end", { id: "w1", tool: WAIT, label: "Wait", is_error: false });
    end("r1", "completed", "Q0 is calibrated.");
    await waitFor(() => expect(reloaded.result.current.status?.kind).toBe("answered"));
    expect(lastAnswer(reloaded).blocks[0].content).toBe("Q0 is calibrated.");
    expect(readStoredTurns("alice").s1).toBeUndefined();
    expect(submissions()).toHaveLength(0);
  });

  it("reattaches a continue whose answer so far the server saved", async () => {
    saved.s1 = [
      { role: "user", content: "Hi" },
      { role: "assistant", content: "Hello" },
      {
        role: "assistant",
        content: JSON.stringify({ blocks: [], assessment: null, in_progress: true }),
        turn_request_id: "r-cont",
      },
    ];
    recorded.s1 = {
      request_id: "r-cont",
      project_id: "p1",
      status: "running",
      start_index: 2,
      continuing: true,
      started_at: iso(Date.now() - 5_000),
    };
    runtime.s1 = "r-cont";
    newRun("s1", "r-cont");
    emit("r-cont", "tool_start", { id: "w1", tool: WAIT, label: "Wait" });
    storeTurn("alice", {
      sessionId: "s1",
      requestId: "r-cont",
      projectId: "p1",
      start: 2,
      continuing: true,
      startedAt: Date.now() - 5_000,
    });
    const reloaded = await openWindow();
    await waitFor(() => expect(tools(reloaded)).toEqual([`${WAIT}:running`]));
    expect(contents(reloaded)).toEqual(["Hi", "Hello"]);
    end("r-cont", "completed", "Continued.");
    await waitFor(() => expect(lastAnswer(reloaded).blocks[0].content).toBe("Continued."));
    expect(reloaded.result.current.chat.notice).toBeNull();
  });

  it("shows a turn that ended meanwhile as saved and follows the newer turn live, never the old question", async () => {
    // The pointer still names r1, which ended; another window has since sent r2.
    saved.s1 = [
      { role: "user", content: "Old question", turn_request_id: "r1" },
      {
        role: "assistant",
        content: JSON.stringify({ blocks: [{ type: "text", content: "Old answer" }] }),
        turn_request_id: "r1",
      },
    ];
    recorded.s1 = null;
    storeTurn("alice", {
      sessionId: "s1",
      requestId: "r1",
      projectId: "p1",
      start: 0,
      continuing: false,
      startedAt: Date.now() - 60_000,
    });
    // r2 starts from the saved chat and waits on a tool.
    saved.s1 = [...saved.s1, { role: "user", content: "New question", turn_request_id: "r2" }];
    recorded.s1 = {
      request_id: "r2",
      project_id: "p1",
      status: "running",
      start_index: 2,
      continuing: false,
      started_at: iso(Date.now() - 5_000),
    };
    runtime.s1 = "r2";
    newRun("s1", "r2");
    emit("r2", "tool_start", { id: "w1", tool: WAIT, label: "Wait" });

    const reloaded = await openWindow();
    await waitFor(() => expect(tools(reloaded)).toEqual([`${WAIT}:running`]));
    // r1 is never replayed (it would show the old question with a live answer under it).
    expect(reattaches().map((c) => c.body.request_id)).toEqual(["r2"]);
    expect(contents(reloaded).slice(-1)).toEqual(["New question"]);
    expect(reloaded.result.current.chat.notice).toBeNull();
    expect(readStoredTurns("alice").s1).toBeUndefined();
    end("r2", "completed", "New answer");
    await waitFor(() => expect(lastAnswer(reloaded).blocks[0].content).toBe("New answer"));
  });

  it("waits for a start still on its way instead of saying the turn was not saved", async () => {
    // Reloaded the moment the message went out: the server has not saved its start yet.
    storeTurn("alice", {
      sessionId: "s1",
      requestId: "r-late",
      projectId: "p1",
      start: 2,
      continuing: false,
      startedAt: Date.now(),
    });
    const reloaded = await openWindow();
    // The claim lands a moment later and the turn runs.
    await waitFor(() =>
      expect(calls.some((c) => c.url.endsWith("/copilot/chat/active"))).toBe(true),
    );
    saved.s1 = [...saved.s1, { role: "user", content: "Calibrate Q0", turn_request_id: "r-late" }];
    recorded.s1 = {
      request_id: "r-late",
      project_id: "p1",
      status: "running",
      start_index: 2,
      continuing: false,
      started_at: iso(Date.now()),
    };
    runtime.s1 = "r-late";
    newRun("s1", "r-late");
    emit("r-late", "tool_start", { id: "w1", tool: WAIT, label: "Wait" });
    await waitFor(() => expect(tools(reloaded)).toEqual([`${WAIT}:running`]), {
      timeout: 4_000,
    });
    expect(reloaded.result.current.chat.notice).toBeNull();
    expect(submissions()).toHaveLength(0);
  });

  it("says a turn is gone only when nothing of it was saved and nothing runs it", async () => {
    storeTurn("alice", {
      sessionId: "s1",
      requestId: "r-gone",
      projectId: "p1",
      start: 2,
      continuing: false,
      startedAt: Date.now() - 60_000,
    });
    const reloaded = await openWindow();
    await waitFor(() => expect(reloaded.result.current.chat.notice).toMatch(UNPLACEABLE));
    expect(reattaches()).toHaveLength(0);
    expect(contents(reloaded)).toEqual(["Hi", "Hello"]);
    expect(readStoredTurns("alice").s1).toBeUndefined();
  });
});

describe("progress the server saved for a turn that no API process runs any more", () => {
  it("is reattached once so the server records its end, instead of showing it as running", async () => {
    // The API restarted mid-turn; the runtime finished the turn meanwhile.
    saved.s1 = [
      { role: "user", content: "Hi" },
      { role: "assistant", content: "Hello" },
      { role: "user", content: "Calibrate Q0", turn_request_id: "r-orphan" },
      {
        role: "assistant",
        content: JSON.stringify({ blocks: [], assessment: null, in_progress: true }),
        turn_request_id: "r-orphan",
      },
    ];
    recorded.s1 = {
      request_id: "r-orphan",
      project_id: "p1",
      status: "running",
      start_index: 2,
      continuing: false,
      started_at: iso(Date.now() - 120_000),
    };
    const final = JSON.stringify({
      blocks: [{ type: "text", content: "Finished while nobody watched.", chart: null }],
      assessment: null,
    });
    stored.set("r-orphan", [
      sse("tool_start", { id: "c1", tool: GET, label: "Get" }),
      sse("tool_end", { id: "c1", tool: GET, label: "Get", is_error: false }),
      sse("result", { ...JSON.parse(final), entry_id: "9" }),
      sse("transcript", {
        saved: true,
        request_id: "r-orphan",
        messages: [
          { role: "user", content: "Calibrate Q0", turn_request_id: "r-orphan" },
          { role: "assistant", content: final, turn_request_id: "r-orphan" },
        ],
      }),
    ]);
    const opened = await openWindow();
    await waitFor(() => expect(reattaches().map((c) => c.body.request_id)).toEqual(["r-orphan"]));
    await waitFor(() =>
      expect(lastAnswer(opened).blocks[0].content).toBe("Finished while nobody watched."),
    );
    expect(inProgressShown(opened)).toBe(false);
    expect(opened.result.current.status?.kind).toBe("answered");
    expect(submissions()).toHaveLength(0);
  });
});

describe("a turn whose state the runtime cannot report", () => {
  const pointer = (requestId: string) =>
    storeTurn("alice", {
      sessionId: "s1",
      requestId,
      projectId: "p1",
      start: 2,
      continuing: false,
      // Well past the grace for a start still on its way.
      startedAt: Date.now() - 60_000,
    });

  /** The turn runs, and the server has saved its start and its progress. */
  function runs(requestId: string) {
    saved.s1 = [
      { role: "user", content: "Hi" },
      { role: "assistant", content: "Hello" },
      { role: "user", content: "Calibrate Q0", turn_request_id: requestId },
    ];
    recorded.s1 = {
      request_id: requestId,
      project_id: "p1",
      status: "running",
      start_index: 2,
      continuing: false,
      started_at: iso(Date.now() - 60_000),
    };
    runtime.s1 = requestId;
    newRun("s1", requestId);
    emit(requestId, "tool_start", { id: "w1", tool: WAIT, label: "Wait" });
  }

  const activeCalls = () => calls.filter((c) => c.url.endsWith("/copilot/chat/active"));

  it.each([
    ["reports itself unavailable", () => Response.json({ running: false, unavailable: true })],
    ["answers with a server error", () => new Response("bad gateway", { status: 502 })],
    ["answers something malformed", () => Response.json({ running: "maybe" })],
    ["is not reachable", () => Promise.reject(new TypeError("Failed to fetch"))],
  ])(
    "keeps the pointer and asks again when the API %s, never saying the turn is gone",
    async (_case, outage) => {
      pointer("r-out");
      activeReply = outage;
      const reloaded = await openWindow();
      await waitFor(() => expect(activeCalls()).toHaveLength(1));
      // The saved chat lacked the turn while the runtime could not say: unknown, not gone.
      expect(reloaded.result.current.chat.notice).toBeNull();
      expect(readStoredTurns("alice").s1?.requestId).toBe("r-out");
      expect(contents(reloaded)).toEqual(["Hi", "Hello"]);
      expect(reloaded.result.current.store.detachedTurns.s1?.reason).toBe("restoring");

      // The runtime answers again, and the turn was running all along: followed live.
      activeReply = null;
      runs("r-out");
      await waitFor(() => expect(tools(reloaded)).toEqual([`${WAIT}:running`]), {
        timeout: 4_000,
      });
      expect(reloaded.result.current.chat.notice).toBeNull();
      expect(reattaches().map((c) => c.body.request_id)).toEqual(["r-out"]);
      expect(submissions()).toHaveLength(0);
      end("r-out", "completed", "Q0 is calibrated.");
      await waitFor(() => expect(lastAnswer(reloaded).blocks[0].content).toBe("Q0 is calibrated."));
      expect(readStoredTurns("alice").s1).toBeUndefined();
    },
  );

  it("recovers live after the initial outage retries are exhausted without reloading", async () => {
    pointer("r-long-outage");
    activeReply = () => Response.json({ running: false, unavailable: true });
    const reloaded = await openWindow();
    await waitFor(() => expect(activeCalls()).toHaveLength(4), { timeout: 20_000 });
    expect(reloaded.result.current.store.detachedTurns.s1?.reason).toBe("restoring");
    expect(readStoredTurns("alice").s1?.requestId).toBe("r-long-outage");
    expect(reloaded.result.current.chat.notice).toBeNull();

    activeReply = null;
    runs("r-long-outage");
    await waitFor(() => expect(tools(reloaded)).toEqual([`${WAIT}:running`]), {
      timeout: 17_000,
    });
    expect(reattaches().map((c) => c.body.request_id)).toEqual(["r-long-outage"]);
    expect(submissions()).toHaveLength(0);
    end("r-long-outage", "completed", "Recovered without a reload.");
    await waitFor(() =>
      expect(lastAnswer(reloaded).blocks[0].content).toBe("Recovered without a reload."),
    );
    expect(readStoredTurns("alice").s1).toBeUndefined();
  }, 40_000);

  it("never takes a recorded turn for orphaned while the runtime cannot say", async () => {
    saved.s1 = [
      { role: "user", content: "Hi" },
      { role: "assistant", content: "Hello" },
      { role: "user", content: "Calibrate Q0", turn_request_id: "r-busy" },
      {
        role: "assistant",
        content: JSON.stringify({ blocks: [], assessment: null, in_progress: true }),
        turn_request_id: "r-busy",
      },
    ];
    recorded.s1 = {
      request_id: "r-busy",
      project_id: "p1",
      status: "running",
      start_index: 2,
      continuing: false,
      started_at: iso(Date.now() - 120_000),
    };
    activeReply = () => Response.json({ running: false, unavailable: true });
    const opened = await openWindow();
    await waitFor(() => expect(activeCalls().length).toBeGreaterThan(0));
    await act(() => new Promise((r) => setTimeout(r, 50)));
    // Not reattached to "heal" it: that is only for the runtime's own answer that nothing runs.
    expect(reattaches()).toHaveLength(0);
    // What the server saved stays shown as it is.
    expect(contents(opened)).toHaveLength(4);
    expect(opened.result.current.chat.notice).toBeNull();
  });
});

describe("a turn being looked up while the user switches project", () => {
  function deferred() {
    let resolve!: (r: Response) => void;
    const promise = new Promise<Response>((r) => {
      resolve = r;
    });
    return { promise, resolve };
  }

  function pointerWithRun() {
    storeTurn("alice", {
      sessionId: "s1",
      requestId: "r1",
      projectId: "p1",
      start: 2,
      continuing: false,
      startedAt: Date.now() - 60_000,
    });
  }

  function runs() {
    saved.s1 = [
      { role: "user", content: "Hi" },
      { role: "assistant", content: "Hello" },
      { role: "user", content: "Calibrate Q0", turn_request_id: "r1" },
    ];
    recorded.s1 = {
      request_id: "r1",
      project_id: "p1",
      status: "running",
      start_index: 2,
      continuing: false,
      started_at: iso(Date.now() - 60_000),
    };
    runtime.s1 = "r1";
    newRun("s1", "r1");
    emit("r1", "tool_start", { id: "w1", tool: WAIT, label: "Wait" });
  }

  const activeCalls = () => calls.filter((c) => c.url.endsWith("/copilot/chat/active"));

  it("drops a reply that comes after a switch to another project (A -> B)", async () => {
    pointerWithRun();
    const slow = deferred();
    activeReply = () => slow.promise;
    const w = await openWindow();
    await waitFor(() => expect(activeCalls()).toHaveLength(1));
    expect(activeCalls()[0].project).toBe("p1");

    switchProject(w, "p2");
    // The late reply says nothing runs; acted on, it would delete the pointer and warn.
    await act(async () => slow.resolve(Response.json({ running: false })));
    await act(() => new Promise((r) => setTimeout(r, 50)));
    expect(w.result.current.chat.notice).toBeNull();
    expect(readStoredTurns("alice").s1?.requestId).toBe("r1");
    expect(reattaches()).toHaveLength(0);
    // Parked as a turn of another project, not reconnecting here.
    expect(w.result.current.store.detachedTurns.s1?.reason).toBe("other_project");

    // Back in p1, it is looked up afresh there and followed live.
    activeReply = null;
    runs();
    switchProject(w, "p1");
    await waitFor(() => expect(tools(w)).toEqual([`${WAIT}:running`]));
    expect(reattaches().every((c) => c.project === "p1")).toBe(true);
    expect(w.result.current.chat.notice).toBeNull();
  });

  it("drops a reply begun before a round trip to another project (A -> B -> A)", async () => {
    pointerWithRun();
    const slow = deferred();
    activeReply = () => slow.promise;
    const w = await openWindow();
    await waitFor(() => expect(activeCalls()).toHaveLength(1));

    switchProject(w, "p2");
    switchProject(w, "p1");
    // The turn runs by now; the first lookup's late reply still says it does not.
    runs();
    activeReply = null;
    await act(async () => slow.resolve(Response.json({ running: false })));
    // Not acted on: the restore looks the turn up again in p1 and follows it.
    await waitFor(() => expect(tools(w)).toEqual([`${WAIT}:running`]));
    expect(w.result.current.chat.notice).toBeNull();
    expect(readStoredTurns("alice").s1?.requestId).toBe("r1");
    expect(activeCalls().length).toBeGreaterThan(1);
    expect(submissions()).toHaveLength(0);
  });

  it("never deletes a newer pointer when an old lookup's reply comes late", async () => {
    pointerWithRun();
    const slow = deferred();
    activeReply = () => slow.promise;
    const w = await openWindow();
    await waitFor(() => expect(activeCalls()).toHaveLength(1));
    // Meanwhile this tab's pointer names a newer turn (r2).
    storeTurn("alice", {
      sessionId: "s1",
      requestId: "r2",
      projectId: "p1",
      start: 2,
      continuing: false,
      startedAt: Date.now(),
    });
    activeReply = () => Response.json({ running: false, unavailable: true });
    await act(async () => slow.resolve(Response.json({ running: false })));
    await act(() => new Promise((r) => setTimeout(r, 50)));
    expect(readStoredTurns("alice").s1?.requestId).toBe("r2");
    expect(w.result.current.chat.notice).toBeNull();
  });
});
