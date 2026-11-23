import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CopilotChatSessionProvider,
  useCopilotChatSessionContext,
} from "@/contexts/CopilotChatSessionContext";
import { readStoredTurns, storeTurn } from "@/lib/copilotTurnStore";
import type { CopilotBlocksResult, TraceStep } from "@/types/copilotChat";

import { useCopilotChat } from "../useCopilotChat";

vi.mock("@/client/copilot/copilot", () => ({
  useGetCopilotConfig: () => ({ data: undefined }),
}));

const PROJECT_KEY = "qdash_current_project_id";
const WAIT = "qdash_wait_agent_intervention";

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function controllableStream() {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  return {
    body,
    push: (text: string) => controller.enqueue(encoder.encode(text)),
    close: () => controller.close(),
    abort: (reason?: unknown) =>
      controller.error(reason ?? new DOMException("aborted", "AbortError")),
  };
}

type Stream = ReturnType<typeof controllableStream>;
type Message = { role: string; content: string };
interface Call {
  url: string;
  method: string;
  body: Record<string, unknown>;
  project: string | undefined;
}

let streams: Stream[];
let calls: Call[];
let saved: Record<string, Message[]>;
let streamReply: (body: Record<string, unknown>, stream: Stream) => Response;
let owner: string | null = "alice";
let project: string | null = "p1";

const wrapper = ({ children }: { children: ReactNode }) => (
  <CopilotChatSessionProvider owner={owner} project={project}>
    {children}
  </CopilotChatSessionProvider>
);

beforeEach(() => {
  streams = [];
  calls = [];
  saved = { s1: [] };
  owner = "alice";
  project = "p1";
  localStorage.setItem(PROJECT_KEY, "p1");
  streamReply = (_body, stream) => new Response(stream.body, { status: 200 });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      const method = init?.method ?? "GET";
      calls.push({ url, method, body, project: headers["X-Project-Id"] });
      if (url.endsWith("/stream")) {
        // The API saves the turn's message when it starts the turn, as the server does.
        const start = body.turn_start as { index: number } | undefined;
        const sessionId = String(body.session_id);
        if (!body.reattach && start && !body.continue_run) {
          saved[sessionId] = [
            ...(saved[sessionId] ?? []).slice(0, start.index),
            { role: "user", content: String(body.message), turn_request_id: body.request_id },
          ] as Message[];
        }
        const stream = controllableStream();
        streams.push(stream);
        init?.signal?.addEventListener("abort", () => stream.abort(init.signal!.reason));
        return streamReply(body, stream);
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
          message_count: 0,
          created_at: "2026-11-22T00:00:00Z",
          updated_at: "2026-11-22T00:00:00Z",
          messages: saved[match[1]] ?? [],
        });
      }
      if (match && method === "PATCH") {
        if (body.messages) saved[match[1]] = body.messages as Message[];
        return Response.json({});
      }
      if (url.endsWith("/copilot/chat/active")) return Response.json({ running: false });
      return Response.json({ stopped: true });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

function useChatAndStore() {
  return { chat: useCopilotChat("s1"), store: useCopilotChatSessionContext() };
}

async function renderChat() {
  const hook = renderHook(useChatAndStore, { wrapper });
  await waitFor(() => expect(hook.result.current.store.isLoadingSessions).toBe(false));
  return hook;
}

const streamCalls = () => calls.filter((c) => c.url.endsWith("/stream"));
const stopCalls = () => calls.filter((c) => c.url.endsWith("/copilot/chat/stop"));
const tools = (steps: TraceStep[] | undefined) =>
  (steps ?? []).flatMap((s) => (s.kind === "tool" ? [`${s.tool}:${s.status}`] : []));
const waitStart = sse("tool_start", { id: "w1", tool: WAIT, label: "Wait" });
const waitEnd = sse("tool_end", { id: "w1", tool: WAIT, label: "Wait", is_error: false });
const result = (text: string, entry = "9") =>
  sse("result", { blocks: [{ type: "text", content: text, chart: null }], entry_id: entry });

/** Start a turn in s1 that parks on the expert's answer. */
async function startWaitingTurn(hook: Awaited<ReturnType<typeof renderChat>>) {
  act(() => hook.result.current.store.switchSession("s1"));
  await waitFor(() => expect(hook.result.current.chat.session?.messagesLoaded).toBe(true));
  act(() => {
    hook.result.current.chat.send("Calibrate Q0");
  });
  await waitFor(() => expect(streams).toHaveLength(1));
  streams[0].push(waitStart);
  await waitFor(() =>
    expect(tools(hook.result.current.chat.liveTurn?.steps)).toEqual([`${WAIT}:running`]),
  );
  // The server saved the user's message when it started the turn.
  await waitFor(() => expect(saved.s1[saved.s1.length - 1]?.content).toBe("Calibrate Q0"));
  return streamCalls()[0].body.request_id as string;
}

describe("a running turn across surfaces and navigation", () => {
  it("keeps the turn and its one stream while a chat surface closes and opens again", async () => {
    // One provider, as in AppLayout; the surface (sidebar, floating window) comes and goes.
    function Surface() {
      const { liveTurn, send, session } = useCopilotChat("s1");
      return (
        <div>
          <span data-testid="steps">{tools(liveTurn?.steps).join(",")}</span>
          <button
            type="button"
            disabled={!session?.messagesLoaded}
            onClick={() => send("Calibrate Q0")}
          >
            send
          </button>
        </div>
      );
    }
    function Select() {
      const { switchSession } = useCopilotChatSessionContext();
      return (
        <button type="button" onClick={() => switchSession("s1")}>
          select
        </button>
      );
    }
    const view = render(
      <CopilotChatSessionProvider owner="alice" project="p1">
        <Select />
        <Surface />
      </CopilotChatSessionProvider>,
    );
    fireEvent.click(screen.getByText("select"));
    await waitFor(() => expect(screen.getByText("send")).not.toBeDisabled());
    fireEvent.click(screen.getByText("send"));
    await waitFor(() => expect(streams).toHaveLength(1));
    streams[0].push(waitStart);
    await waitFor(() => expect(screen.getByTestId("steps")).toHaveTextContent(`${WAIT}:running`));

    // Closed: the surface unmounts, the provider stays.
    view.rerender(
      <CopilotChatSessionProvider owner="alice" project="p1">
        <Select />
      </CopilotChatSessionProvider>,
    );
    expect(screen.queryByTestId("steps")).toBeNull();
    // Reopened: it shows the same live turn.
    view.rerender(
      <CopilotChatSessionProvider owner="alice" project="p1">
        <Select />
        <Surface />
      </CopilotChatSessionProvider>,
    );
    expect(screen.getByTestId("steps")).toHaveTextContent(`${WAIT}:running`);
    expect(streamCalls()).toHaveLength(1);
    expect(stopCalls()).toHaveLength(0);
    // The original stream goes on into the reopened surface.
    streams[0].push(waitEnd);
    await waitFor(() => expect(screen.getByTestId("steps")).toHaveTextContent(`${WAIT}:done`));
  });

  it("reattaches after the provider remounts, without resending or stopping the turn", async () => {
    const first = await renderChat();
    const requestId = await startWaitingTurn(first);
    expect(readStoredTurns("alice").s1).toMatchObject({
      requestId,
      projectId: "p1",
      start: 0,
      continuing: false,
      activity: { tool: WAIT, label: "Wait" },
    });
    // The stored pointer holds no message text, argument, or result.
    expect(JSON.stringify(readStoredTurns("alice"))).not.toContain("Calibrate Q0");

    first.unmount();
    expect(stopCalls()).toHaveLength(0);

    const hook = await renderChat();
    await waitFor(() => expect(streams).toHaveLength(2));
    const reattach = streamCalls()[1];
    expect(reattach.body).toMatchObject({ reattach: true, request_id: requestId, message: "" });
    expect(reattach.project).toBe("p1");

    // The runtime streams the turn from its start; the expert answers and the same turn resumes.
    streams[1].push(waitStart);
    await waitFor(() =>
      expect(tools(hook.result.current.chat.liveTurn?.steps)).toEqual([`${WAIT}:running`]),
    );
    expect(hook.result.current.chat.connection?.state).toBe("live");
    streams[1].push(waitEnd);
    streams[1].push(result("Resumed after the expert."));
    streams[1].close();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));

    const messages = hook.result.current.chat.messages;
    expect(messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    const answer = JSON.parse(messages[1].content) as CopilotBlocksResult;
    expect(answer.blocks[0].content).toBe("Resumed after the expert.");
    expect(tools(answer.trace?.steps)).toEqual([`${WAIT}:done`]);
    // Saved once acknowledged, the pointer goes: nothing is restored again.
    await waitFor(() => expect(saved.s1).toHaveLength(2));
    await waitFor(() => expect(readStoredTurns("alice").s1).toBeUndefined());
    expect(streamCalls().filter((c) => !c.body.reattach)).toHaveLength(1);
  });

  it("restores an ended turn from its stored record and saves its answer once", async () => {
    saved.s1 = [{ role: "user", content: "Calibrate Q0" }];
    storeTurn("alice", {
      sessionId: "s1",
      requestId: "r-ended",
      projectId: "p1",
      start: 0,
      continuing: false,
      startedAt: Date.now() - 60_000,
      ended: true,
    });
    const hook = await renderChat();
    await waitFor(() => expect(streams).toHaveLength(1));
    expect(streamCalls()[0].body).toMatchObject({ reattach: true, request_id: "r-ended" });
    streams[0].push(result("Done before the reload."));
    streams[0].close();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    await waitFor(() => expect(saved.s1).toHaveLength(2));
    await waitFor(() => expect(readStoredTurns("alice").s1).toBeUndefined());
    expect(streamCalls()).toHaveLength(1);
  });

  it("says when the runtime never got the message, and does not resend it", async () => {
    saved.s1 = [{ role: "user", content: "Calibrate Q0" }];
    storeTurn("alice", {
      sessionId: "s1",
      requestId: "r-lost",
      projectId: "p1",
      start: 0,
      continuing: false,
      startedAt: Date.now(),
    });
    const hook = await renderChat();
    await waitFor(() => expect(streams).toHaveLength(1));
    streams[0].push(sse("error", { detail: "no record", code: "turn_not_found" }));
    streams[0].close();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    const last = hook.result.current.chat.messages.slice(-1)[0];
    expect(last?.content).toMatch(/^Error: The connection dropped before the assistant received/);
    expect(readStoredTurns("alice").s1).toBeUndefined();
    expect(streamCalls()).toHaveLength(1);
  });

  it("leaves the saved chat as it was when a restored turn cannot be followed", async () => {
    saved.s1 = [
      { role: "user", content: "Calibrate Q0" },
      { role: "assistant", content: "Error: Lost the connection to the assistant." },
    ];
    storeTurn("alice", {
      sessionId: "s1",
      requestId: "r-refused",
      projectId: "p1",
      start: 0,
      continuing: false,
      startedAt: Date.now(),
    });
    const hook = await renderChat();
    await waitFor(() => expect(streams).toHaveLength(1));
    streams[0].push(sse("error", { detail: "belongs to another project", code: "wrong_project" }));
    streams[0].close();
    await waitFor(() =>
      expect(hook.result.current.chat.notice).toBe(
        "Could not reconnect to the answer: belongs to another project",
      ),
    );
    // Nothing is claimed about the turn, nothing saved over the chat, and it is not tried again.
    expect(hook.result.current.chat.messages).toHaveLength(2);
    expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(0);
    expect(readStoredTurns("alice").s1).toBeUndefined();
  });

  it("does not restore a turn the server has no record of and the runtime does not run", async () => {
    storeTurn("alice", {
      sessionId: "s1",
      requestId: "r-unsaved",
      projectId: "p1",
      start: 0,
      continuing: false,
      // Sent long enough ago that its start is not still on its way to the server.
      startedAt: Date.now() - 60_000,
    });
    const hook = await renderChat();
    await waitFor(() => expect(hook.result.current.chat.notice).toMatch(/cannot be shown here/));
    expect(streamCalls()).toHaveLength(0);
    expect(readStoredTurns("alice").s1).toBeUndefined();
  });
});

describe("project and user scope", () => {
  it("does not attach a pending restoration after switching projects", async () => {
    const first = await renderChat();
    await startWaitingTurn(first);
    first.unmount();
    const originalFetch = globalThis.fetch;
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    let loading = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const response = await originalFetch(url, init);
        if (url.endsWith("/copilot/chat/sessions/s1") && (init?.method ?? "GET") === "GET") {
          loading = true;
          await pending;
        }
        return response;
      }),
    );
    const hook = await renderChat();
    await waitFor(() => expect(loading).toBe(true));
    project = "p2";
    hook.rerender();
    await act(async () => {
      release();
      await pending;
    });
    await waitFor(() =>
      expect(hook.result.current.store.detachedTurns.s1?.reason).toBe("other_project"),
    );
    expect(streamCalls()).toHaveLength(1);
    expect(stopCalls()).toHaveLength(0);
    project = "p1";
    hook.rerender();
    await waitFor(() => expect(streamCalls()).toHaveLength(2));
  });

  it("stops showing a turn of another project, without stopping it, and follows it again on return", async () => {
    const hook = await renderChat();
    const requestId = await startWaitingTurn(hook);

    project = "p2";
    localStorage.setItem(PROJECT_KEY, "p2");
    hook.rerender();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    await waitFor(() =>
      expect(hook.result.current.chat.detachedTurn).toMatchObject({
        reason: "other_project",
        requestId,
        projectId: "p1",
      }),
    );
    expect(stopCalls()).toHaveLength(0);
    // Nothing of it is shown or saved in p2, and a new message would race it: refused.
    expect(hook.result.current.chat.liveTurn).toBeNull();
    let sent = true;
    act(() => {
      sent = hook.result.current.chat.send("Another question");
    });
    expect(sent).toBe(false);

    project = "p1";
    localStorage.setItem(PROJECT_KEY, "p1");
    hook.rerender();
    await waitFor(() => expect(streams).toHaveLength(2));
    expect(streamCalls()[1]).toMatchObject({
      project: "p1",
      body: expect.objectContaining({ reattach: true, request_id: requestId }),
    });
    await waitFor(() => expect(hook.result.current.chat.detachedTurn).toBeNull());
  });

  it("names the turn's own project on every reattach, also after the stored project changed", async () => {
    const hook = await renderChat();
    const requestId = await startWaitingTurn(hook);
    // Another tab switched the stored project; this provider has not seen a switch yet.
    localStorage.setItem(PROJECT_KEY, "p2");
    streams[0].abort(new TypeError("network error"));
    await waitFor(() => expect(streams).toHaveLength(2));
    expect(streamCalls()[1]).toMatchObject({
      project: "p1",
      body: expect.objectContaining({ reattach: true, request_id: requestId }),
    });
    act(() => hook.result.current.chat.stop());
    await waitFor(() => expect(stopCalls()).toHaveLength(1));
    expect(stopCalls()[0]).toMatchObject({
      project: "p1",
      body: { session_id: "s1", turn_request_id: requestId },
    });
  });

  it("never restores another user's turn, and forgets the user's own on sign-out", async () => {
    saved.s1 = [{ role: "user", content: "Calibrate Q0" }];
    storeTurn("bob", {
      sessionId: "s1",
      requestId: "r-bob",
      projectId: "p1",
      start: 0,
      continuing: false,
      startedAt: Date.now(),
    });
    const hook = await renderChat();
    await waitFor(() => expect(readStoredTurns("bob")).toEqual({}));
    expect(streamCalls()).toHaveLength(0);

    await startWaitingTurn(hook);
    owner = null;
    hook.rerender();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    expect(readStoredTurns("alice")).toEqual({});
    expect(stopCalls()).toHaveLength(0);
  });
});

describe("chat events for notifications", () => {
  function collect(hook: Awaited<ReturnType<typeof renderChat>>) {
    const events: Array<{ kind: string; requestId: string; projectId: string | null }> = [];
    hook.result.current.store.subscribeChatEvents((event) => events.push(event));
    return events;
  }

  it("raises each moment once per turn, not again when a reattach replays it", async () => {
    const hook = await renderChat();
    const events = collect(hook);
    const requestId = await startWaitingTurn(hook);
    await waitFor(() => expect(events.map((e) => e.kind)).toEqual(["expert"]));

    // The stream drops; the reattach replays the wait from the turn's start.
    streams[0].abort(new TypeError("network error"));
    await waitFor(() => expect(streams).toHaveLength(2));
    streams[1].push(waitStart);
    streams[1].push(waitEnd);
    // An answer that asks for approval is input needed, not a finished answer.
    streams[1].push(
      sse("result", {
        blocks: [{ type: "approval", content: "Apply 5.1 GHz?", chart: null }],
        entry_id: "9",
      }),
    );
    streams[1].close();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    expect(events).toEqual([
      expect.objectContaining({ kind: "expert", requestId, projectId: "p1" }),
      expect.objectContaining({ kind: "approval", requestId, projectId: "p1" }),
    ]);
  });

  it("raises nothing a restored turn already raised, and the answer it had not", async () => {
    saved.s1 = [{ role: "user", content: "Calibrate Q0" }];
    storeTurn("alice", {
      sessionId: "s1",
      requestId: "r-restored",
      projectId: "p1",
      start: 0,
      continuing: false,
      startedAt: Date.now(),
      notified: ["expert"],
    });
    const hook = await renderChat();
    const events = collect(hook);
    await waitFor(() => expect(streams).toHaveLength(1));
    streams[0].push(waitStart);
    streams[0].push(waitEnd);
    streams[0].push(result("Resumed."));
    streams[0].close();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    expect(events.map((e) => e.kind)).toEqual(["answer"]);
  });

  it("raises nothing for history loaded from the server, or for a turn of another project", async () => {
    saved.s1 = [
      { role: "user", content: "Q" },
      { role: "assistant", content: JSON.stringify({ blocks: [], assessment: null }) },
    ];
    const hook = await renderChat();
    const events = collect(hook);
    act(() => hook.result.current.store.switchSession("s1"));
    await waitFor(() => expect(hook.result.current.chat.session?.messagesLoaded).toBe(true));
    expect(events).toEqual([]);

    act(() => {
      hook.result.current.chat.send("Calibrate Q0");
    });
    await waitFor(() => expect(streams).toHaveLength(1));
    project = "p2";
    localStorage.setItem(PROJECT_KEY, "p2");
    hook.rerender();
    await waitFor(() =>
      expect(hook.result.current.chat.detachedTurn?.reason).toBe("other_project"),
    );
    // The detached stream is not read: nothing it would have said is raised in p2.
    expect(events).toEqual([]);
  });

  it("raises a failure once", async () => {
    streamReply = () => new Response("bad request", { status: 400 });
    const hook = await renderChat();
    const events = collect(hook);
    act(() => hook.result.current.store.switchSession("s1"));
    await waitFor(() => expect(hook.result.current.chat.session?.messagesLoaded).toBe(true));
    act(() => {
      hook.result.current.chat.send("Calibrate Q0");
    });
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    expect(events.map((e) => e.kind)).toEqual(["failed"]);
  });
});
