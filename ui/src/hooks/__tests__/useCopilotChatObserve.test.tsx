import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { chatStatus } from "@/components/features/chat/ChatTurnStatus";
import {
  CopilotChatSessionProvider,
  useCopilotChatSessionContext,
} from "@/contexts/CopilotChatSessionContext";
import { turnStartOf } from "@/lib/copilotObservedTurn";
import { readStoredTurns } from "@/lib/copilotTurnStore";
import type {
  ChatMessage,
  ChatTurnEvent,
  CopilotBlocksResult,
  TraceStep,
} from "@/types/copilotChat";

import { useCopilotChat } from "../useCopilotChat";

vi.mock("@/client/copilot/copilot", () => ({
  useGetCopilotConfig: () => ({ data: undefined }),
}));

// A second window (or a reloaded tab without the starting tab's pointer) opens a chat whose
// turn another window started. It learns the turn from the runtime and follows it.

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

/** The start the window that sent a turn reports: messages before it, and its own message. */
const startOf = (history: Message[], own: Message | null) =>
  turnStartOf(history as ChatMessage[], own as ChatMessage | null);
interface Call {
  url: string;
  method: string;
  body: Record<string, unknown>;
  project: string | undefined;
}

let streams: Stream[];
let calls: Call[];
let saved: Record<string, Message[]>;
let active: Record<string, unknown>;

const wrapper = ({ children }: { children: ReactNode }) => (
  <CopilotChatSessionProvider owner="alice" project="p1">
    {children}
  </CopilotChatSessionProvider>
);

beforeEach(() => {
  streams = [];
  calls = [];
  saved = { s1: [{ role: "user", content: "Calibrate Q0" }], s2: [] };
  active = {
    running: true,
    turn_request_id: "t-other",
    continuing: false,
    started_at: 1000,
    turn_start: startOf([], { role: "user", content: "Calibrate Q0" }),
  };
  localStorage.setItem(PROJECT_KEY, "p1");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      const method = init?.method ?? "GET";
      calls.push({ url, method, body, project: headers["X-Project-Id"] });
      if (url.endsWith("/stream")) {
        const stream = controllableStream();
        streams.push(stream);
        init?.signal?.addEventListener("abort", () => stream.abort(init.signal!.reason));
        return new Response(stream.body, { status: 200 });
      }
      if (url.endsWith("/copilot/chat/active")) {
        return Response.json(body.session_id === "s1" ? active : { running: false });
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
      return Response.json({ stopped: true });
    }),
  );
});

afterEach(() => {
  // Each test is one window: none stays open to follow the next test's turns.
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

function useChatAndStore() {
  const store = useCopilotChatSessionContext();
  const chat = useCopilotChat("s1");
  const session = store.sessions.find((s) => s.id === "s1");
  const status = session
    ? chatStatus({ run: store.runs.s1, detached: null, messages: session.messages })
    : null;
  return { chat, store, status };
}

async function openSecondWindow() {
  const hook = renderHook(useChatAndStore, { wrapper });
  await waitFor(() => expect(hook.result.current.store.isLoadingSessions).toBe(false));
  const events: ChatTurnEvent[] = [];
  hook.result.current.store.subscribeChatEvents((e) => events.push(e));
  act(() => hook.result.current.store.switchSession("s1"));
  return { hook, events };
}

const streamCalls = () => calls.filter((c) => c.url.endsWith("/stream"));
const activeCalls = () => calls.filter((c) => c.url.endsWith("/copilot/chat/active"));
const patches = () => calls.filter((c) => c.method === "PATCH");
const tools = (steps: TraceStep[] | undefined) =>
  (steps ?? []).flatMap((s) => (s.kind === "tool" ? [`${s.tool}:${s.status}`] : []));
const waitStart = sse("tool_start", { id: "w1", tool: WAIT, label: "Wait" });
const waitEnd = sse("tool_end", { id: "w1", tool: WAIT, label: "Wait", is_error: false });
const result = (text: string, entry = "9") =>
  sse("result", { blocks: [{ type: "text", content: text, chart: null }], entry_id: entry });

describe("a turn another window started", () => {
  it("is found when the chat opens late, shows what it waits for, and ends here without saving", async () => {
    const { hook, events } = await openSecondWindow();
    await waitFor(() => expect(streams).toHaveLength(1));
    // Looked up for the open project, then followed by reattaching: nothing is submitted.
    expect(activeCalls()[0]).toMatchObject({ body: { session_id: "s1" }, project: "p1" });
    expect(streamCalls()[0].body).toMatchObject({
      session_id: "s1",
      request_id: "t-other",
      reattach: true,
      message: "",
    });
    expect(streamCalls()[0].project).toBe("p1");
    // The other window's message is shown with the live answer after it.
    expect(hook.result.current.chat.messages.map((m) => m.content)).toEqual(["Calibrate Q0"]);

    // The replay brings the turn up to the wait it is parked on.
    streams[0].push(sse("delta", { text: "Asking the expert." }));
    streams[0].push(waitStart);
    await waitFor(() => expect(hook.result.current.status?.kind).toBe("waiting_expert"));
    expect(hook.result.current.status?.label).toBe("Waiting for the expert's answer");
    expect(tools(hook.result.current.chat.liveTurn?.steps)).toEqual([`${WAIT}:running`]);

    // The expert answers and the turn ends: the status follows to the end.
    streams[0].push(waitEnd);
    await waitFor(() => expect(hook.result.current.status?.kind).toBe("working"));
    streams[0].push(result("Resumed after the expert."));
    streams[0].close();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    expect(hook.result.current.status?.kind).toBe("answered");
    const answer = JSON.parse(hook.result.current.chat.messages[1].content) as CopilotBlocksResult;
    expect(answer.blocks[0].content).toBe("Resumed after the expert.");

    // The server saves the turn and the starting window notifies; this one stores no pointer.
    expect(patches()).toHaveLength(0);
    expect(events).toEqual([]);
    expect(readStoredTurns("alice")).toEqual({});
    // Only the reattach: nothing was resent.
    expect(streamCalls()).toHaveLength(1);
  });

  it("takes the run the server saved as soon as the followed turn ends", async () => {
    const { hook } = await openSecondWindow();
    await waitFor(() => expect(streams).toHaveLength(1));
    streams[0].push(result("Folded here."));
    // The server recorded the turn, whether or not the starting window is still open.
    streams[0].push(
      sse("transcript", {
        saved: true,
        request_id: "t-other",
        messages: [
          { role: "user", content: "Calibrate Q0", turn_request_id: "t-other" },
          { role: "assistant", content: "Saved by the server.", turn_request_id: "t-other" },
        ],
      }),
    );
    streams[0].close();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    expect(hook.result.current.chat.messages[1]?.content).toBe("Saved by the server.");
    expect(patches()).toHaveLength(0);
  });

  it("takes the saved transcript after the turn ended when the stream did not report it", async () => {
    const { hook } = await openSecondWindow();
    await waitFor(() => expect(streams).toHaveLength(1));
    streams[0].push(result("Folded here."));
    streams[0].close();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    // The server's copy of the answer, loaded shortly after.
    saved.s1 = [
      { role: "user", content: "Calibrate Q0" },
      { role: "assistant", content: "Saved by the server." },
    ];
    await waitFor(
      () => expect(hook.result.current.chat.messages[1]?.content).toBe("Saved by the server."),
      { timeout: 4_000 },
    );
    expect(patches()).toHaveLength(0);
  });

  it("clears the live state when the turn fails or is stopped", async () => {
    const { hook } = await openSecondWindow();
    await waitFor(() => expect(streams).toHaveLength(1));
    streams[0].push(waitStart);
    await waitFor(() => expect(hook.result.current.status?.kind).toBe("waiting_expert"));
    streams[0].push(sse("error", { detail: "conversation was not answered: aborted" }));
    streams[0].close();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    expect(hook.result.current.status?.kind).toBe("failed");
    expect(patches()).toHaveLength(0);

    // The next turn of the other window is found when this window is focused again.
    saved.s1 = [
      { role: "user", content: "Calibrate Q0" },
      { role: "assistant", content: "Error: aborted" },
      { role: "user", content: "Try again" },
    ];
    active = {
      running: true,
      turn_request_id: "t-next",
      continuing: false,
      turn_start: startOf(saved.s1.slice(0, 2), saved.s1[2]),
    };
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() => expect(streams).toHaveLength(2));
    expect(streamCalls()[1].body).toMatchObject({ request_id: "t-next", reattach: true });
    expect(hook.result.current.chat.messages.map((m) => m.content)).toEqual(
      saved.s1.map((m) => m.content),
    );
    streams[1].push(waitStart);
    await waitFor(() => expect(hook.result.current.status?.kind).toBe("waiting_expert"));

    // Stopped from this window: the stop names the followed turn.
    act(() => hook.result.current.chat.stop());
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    expect(hook.result.current.status?.kind).toBe("stopped");
    const stop = calls.find((c) => c.url.endsWith("/copilot/chat/stop"));
    expect(stop?.body).toEqual({ session_id: "s1", turn_request_id: "t-next" });
    expect(patches()).toHaveLength(0);
  });

  it("follows nothing when no turn runs, and never a turn this tab already streams", async () => {
    active = { running: false };
    const { hook } = await openSecondWindow();
    await waitFor(() => expect(activeCalls()).toHaveLength(1));
    await waitFor(() => expect(hook.result.current.chat.session?.messagesLoaded).toBe(true));
    expect(streams).toHaveLength(0);
    expect(hook.result.current.status?.kind ?? null).toBeNull();

    // This tab sends its own turn; the runtime then reports it as running.
    act(() => {
      hook.result.current.chat.send("Calibrate Q1");
    });
    await waitFor(() => expect(streams).toHaveLength(1));
    const own = streamCalls()[0].body.request_id as string;
    active = { running: true, turn_request_id: own, continuing: false };
    const asked = activeCalls().length;
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });
    // Not even asked while this tab streams the chat, and no second stream is opened.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(activeCalls()).toHaveLength(asked);
    expect(streams).toHaveLength(1);
    expect(streamCalls().filter((c) => c.body.reattach)).toHaveLength(0);
  });

  it("applies a late lookup only while nothing else started in the chat", async () => {
    let answerLookup!: (value: Response) => void;
    const fetchMock = vi.mocked(fetch);
    const base = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (url, init) => {
      if (String(url).endsWith("/copilot/chat/active")) {
        calls.push({ url: String(url), method: "POST", body: {}, project: undefined });
        return new Promise<Response>((resolve) => (answerLookup = resolve));
      }
      return base(url, init);
    });
    const { hook } = await openSecondWindow();
    await waitFor(() => expect(activeCalls()).toHaveLength(1));
    await waitFor(() => expect(hook.result.current.chat.session?.messagesLoaded).toBe(true));
    // This tab sends a message before the lookup answers.
    act(() => {
      hook.result.current.chat.send("Mine");
    });
    await waitFor(() => expect(streams).toHaveLength(1));
    answerLookup(Response.json(active));
    await new Promise((resolve) => setTimeout(resolve, 50));
    // The stale answer starts nothing: the chat keeps its own one turn.
    expect(streams).toHaveLength(1);
    expect(streamCalls()[0].body.reattach).toBeUndefined();
  });

  it("preserves feedback edited while the observer fetches the transcript", async () => {
    active = { running: false };
    saved.s1.push({ role: "assistant", content: "Earlier answer" });
    const { hook } = await openSecondWindow();
    await waitFor(() => expect(hook.result.current.chat.session?.messages).toHaveLength(2));
    await new Promise((resolve) => setTimeout(resolve, 50));
    const fetchMock = vi.mocked(fetch);
    const base = fetchMock.getMockImplementation()!;
    let release!: (response: Response) => void;
    let staleResponse!: Response;
    fetchMock.mockImplementation(async (url, init) => {
      if (String(url).endsWith("/sessions/s1") && (!init?.method || init.method === "GET")) {
        staleResponse = await base(url, init);
        return new Promise<Response>((resolve) => (release = resolve));
      }
      return base(url, init);
    });
    active = {
      running: true,
      turn_request_id: "continuing-elsewhere",
      continuing: true,
      turn_start: startOf(saved.s1, null),
    };
    act(() => window.dispatchEvent(new Event("focus")));
    await waitFor(() => expect(release).toBeDefined());
    act(() => hook.result.current.store.setMessageFeedback("s1", 1, "up"));
    await waitFor(() => expect(patches().length).toBeGreaterThan(0));
    await act(async () => release(staleResponse));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(streams).toHaveLength(0);
    expect(JSON.parse(hook.result.current.chat.session!.messages[1].content).feedback).toBe("up");
  });

  it("waits for the starting window's save instead of answering an older question", async () => {
    // The other window sent "Calibrate Q1" after an older exchange; its save of the new
    // message is still queued, so the server holds only the older conversation.
    const older = [
      { role: "user", content: "What is T1 of Q0?" },
      { role: "assistant", content: "T1 is 50 us." },
    ];
    const question = { role: "user", content: "Calibrate Q1" };
    saved.s1 = older;
    active = {
      running: true,
      turn_request_id: "t-new",
      continuing: false,
      turn_start: startOf(older, question),
    };
    const { hook } = await openSecondWindow();
    await waitFor(() => expect(activeCalls()).toHaveLength(1));
    await new Promise((resolve) => setTimeout(resolve, 100));
    // Nothing is attached: the new answer never goes under "What is T1 of Q0?".
    expect(streams).toHaveLength(0);
    expect(hook.result.current.chat.isStreaming).toBe(false);

    // The save lands; the next lookup, shortly after, follows the turn under its own message.
    saved.s1 = [...older, question];
    await waitFor(() => expect(streams).toHaveLength(1), { timeout: 3_000 });
    expect(streamCalls()[0].body).toMatchObject({ request_id: "t-new", reattach: true });
    expect(hook.result.current.chat.messages.map((m) => m.content)).toEqual([
      "What is T1 of Q0?",
      "T1 is 50 us.",
      "Calibrate Q1",
    ]);
    streams[0].push(result("Q1 calibrated."));
    streams[0].close();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    expect(hook.result.current.chat.messages).toHaveLength(4);
    expect(patches()).toHaveLength(0);
  });

  it("follows a continue only over the answer it continues", async () => {
    const stopped = [
      { role: "user", content: "Calibrate Q0" },
      { role: "assistant", content: "Stopped part." },
    ];
    // The stopped answer's save has not landed yet.
    saved.s1 = [stopped[0]];
    active = {
      running: true,
      turn_request_id: "t-cont",
      continuing: true,
      turn_start: startOf(stopped, null),
    };
    const { hook } = await openSecondWindow();
    await waitFor(() => expect(activeCalls()).toHaveLength(1));
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(streams).toHaveLength(0);

    saved.s1 = stopped;
    await waitFor(() => expect(streams).toHaveLength(1), { timeout: 3_000 });
    expect(streamCalls()[0].body).toMatchObject({ request_id: "t-cont", reattach: true });
    // The continue's answer follows the answer it continues; nothing of its own is added.
    expect(hook.result.current.chat.messages.map((m) => m.content)).toEqual([
      "Calibrate Q0",
      "Stopped part.",
    ]);
    streams[0].push(result("Continued."));
    streams[0].close();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    expect(hook.result.current.chat.messages).toHaveLength(3);
  });

  it("replays a steered turn from its own message, leaving out what the replay places again", async () => {
    // The other window saved the turn's message, the part of the answer a steer closed
    // off, and the steer.
    saved.s1 = [
      { role: "user", content: "Calibrate Q0" },
      { role: "assistant", content: "Part before the steer." },
      {
        role: "user",
        content: "Use 5 GHz",
        steer: { request_id: "s-1", entry_id: null, placement: "exact" },
      } as Message,
    ];
    const { hook } = await openSecondWindow();
    await waitFor(() => expect(streams).toHaveLength(1));
    expect(hook.result.current.chat.messages.map((m) => m.content)).toEqual(["Calibrate Q0"]);
  });

  it("does not follow a turn the runtime reports without its start", async () => {
    active = { running: true, turn_request_id: "t-old-page", continuing: false };
    const { hook } = await openSecondWindow();
    await waitFor(() => expect(activeCalls()).toHaveLength(1));
    await waitFor(() => expect(hook.result.current.chat.session?.messagesLoaded).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(streams).toHaveLength(0);
  });

  it("takes a turn another window started and finished between two checks", async () => {
    active = { running: false };
    const { hook } = await openSecondWindow();
    await waitFor(() => expect(hook.result.current.chat.session?.messagesLoaded).toBe(true));
    expect(hook.result.current.chat.messages.map((m) => m.content)).toEqual(["Calibrate Q0"]);

    // The other window's whole turn ran and was saved while this window was not looking.
    saved.s1 = [
      { role: "user", content: "Calibrate Q0" },
      { role: "assistant", content: "Done there." },
    ];
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() =>
      expect(hook.result.current.chat.messages.map((m) => m.content)).toEqual([
        "Calibrate Q0",
        "Done there.",
      ]),
    );
    // Taken, not saved again, and nothing was followed or sent.
    expect(patches()).toHaveLength(0);
    expect(streams).toHaveLength(0);
  });

  it("keeps a followed answer the starting window has not saved over a shorter saved copy", async () => {
    const { hook } = await openSecondWindow();
    await waitFor(() => expect(streams).toHaveLength(1));
    streams[0].push(result("Folded here."));
    streams[0].close();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    // The starting window has not saved its answer (or was closed first).
    active = { running: false };
    const asked = calls.length;
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() => expect(calls.length).toBeGreaterThan(asked + 1));
    await new Promise((resolve) => setTimeout(resolve, 50));
    const answer = JSON.parse(hook.result.current.chat.messages[1].content) as CopilotBlocksResult;
    expect(answer.blocks[0].content).toBe("Folded here.");
  });
});
