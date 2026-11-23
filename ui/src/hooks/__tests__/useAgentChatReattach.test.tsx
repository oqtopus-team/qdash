import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  AgentChatSessionProvider,
  STREAM_SILENCE_MS,
  useAgentChatSessionContext,
} from "@/contexts/AgentChatSessionContext";
import type { AgentBlocksResult, TraceStep } from "@/types/agentChat";

import { useAgentChat } from "../useAgentChat";

vi.mock("@/client/agent/agent", () => ({
  useGetAgentConfig: () => ({ data: undefined }),
}));

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** A response body whose chunks the test pushes one at a time. */
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

const wrapper = ({ children }: { children: ReactNode }) => (
  <AgentChatSessionProvider>{children}</AgentChatSessionProvider>
);

/** Each /stream request gets the next stream; the test pushes into them. */
let streams: Stream[];
let fetchMock: ReturnType<typeof vi.fn>;
let streamReply: (body: Record<string, unknown>, stream: Stream) => Response;

beforeEach(() => {
  streams = [];
  streamReply = (_body, stream) => new Response(stream.body, { status: 200 });
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/stream")) {
      const stream = controllableStream();
      streams.push(stream);
      init?.signal?.addEventListener("abort", () => stream.abort(init.signal!.reason));
      return streamReply(JSON.parse(String(init!.body)), stream);
    }
    if (url.endsWith("/agent/chat/sessions") && !init?.method) {
      return Response.json({ sessions: [] });
    }
    return Response.json({ session_id: "x", title: "", messages: [] });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
});

function useChatAndStore() {
  return { chat: useAgentChat(), store: useAgentChatSessionContext() };
}

async function renderChat() {
  const { result } = renderHook(useChatAndStore, { wrapper });
  await waitFor(() => expect(result.current.store.isLoadingSessions).toBe(false));
  return result;
}

type Result = Awaited<ReturnType<typeof renderChat>>;

function streamBodies(): Record<string, unknown>[] {
  return fetchMock.mock.calls
    .filter(([url]) => String(url).endsWith("/stream"))
    .map(([, init]) => JSON.parse(String(init.body)));
}

function lastAssistant(result: Result) {
  const messages = result.current.chat.messages;
  const last = messages[messages.length - 1];
  expect(last?.role).toBe("assistant");
  return JSON.parse(last.content) as AgentBlocksResult;
}

function tools(steps: TraceStep[] | undefined) {
  return (steps ?? []).flatMap((s) => (s.kind === "tool" ? [`${s.tool}:${s.status}`] : []));
}

const WAIT = "qdash_wait_agent_intervention";
const waitStart = sse("tool_start", { id: "w1", tool: WAIT, label: "Wait agent intervention" });
const waitEnd = sse("tool_end", {
  id: "w1",
  tool: WAIT,
  label: "Wait agent intervention",
  is_error: false,
});

describe("a turn whose stream drops while it waits for the expert", () => {
  it("reattaches, shows the resumed turn once, and saves its answer without resending", async () => {
    const result = await renderChat();
    act(() => result.current.chat.send("Calibrate Q0"));
    await waitFor(() => expect(streams).toHaveLength(1));
    streams[0].push(sse("delta", { text: "Asking the expert." }));
    streams[0].push(waitStart);
    await waitFor(() =>
      expect(tools(result.current.chat.liveTurn?.steps)).toEqual([`${WAIT}:running`]),
    );
    expect(result.current.chat.connection?.state).toBe("live");

    // A proxy drops the stream during the wait.
    streamReply = (body, stream) =>
      body.reattach
        ? new Response(stream.body, { status: 200 })
        : new Response(null, { status: 500 });
    streams[0].abort(new TypeError("network error"));
    await waitFor(() => expect(streams).toHaveLength(2));
    const [sent, reattach] = streamBodies();
    expect(reattach).toMatchObject({ reattach: true, request_id: sent.request_id });

    // The runtime replays the turn from its start: the trace is rebuilt, not doubled.
    streams[1].push(sse("delta", { text: "Asking the expert." }));
    streams[1].push(waitStart);
    await waitFor(() => expect(result.current.chat.connection?.state).toBe("live"));
    await waitFor(() =>
      expect(tools(result.current.chat.liveTurn?.steps)).toEqual([`${WAIT}:running`]),
    );

    // The expert answers; the resumed turn reaches the original chat.
    streams[1].push(waitEnd);
    streams[1].push(
      sse("tool_start", { id: "s1", tool: "qdash_run_agent_session_step", label: "Run" }),
    );
    streams[1].push(
      sse("tool_end", {
        id: "s1",
        tool: "qdash_run_agent_session_step",
        label: "Run",
        is_error: false,
      }),
    );
    streams[1].push(sse("delta", { text: "Resumed with 5.1 GHz." }));
    streams[1].push(
      sse("result", {
        blocks: [{ type: "text", content: "Resumed with 5.1 GHz.", chart: null }],
        entry_id: "12",
      }),
    );
    streams[1].close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));

    const saved = lastAssistant(result);
    expect(saved.blocks.map((b) => b.content)).toEqual(["Resumed with 5.1 GHz."]);
    expect(tools(saved.trace?.steps)).toEqual([
      `${WAIT}:done`,
      "qdash_run_agent_session_step:done",
    ]);
    expect(result.current.chat.messages.filter((m) => m.role === "user")).toHaveLength(1);
    const messages = result.current.chat.messages;
    expect(messages[messages.length - 1]?.entryId).toBe("12");
    // One request and one reattach: the message was sent once.
    expect(streamBodies()).toHaveLength(2);
  });

  it("stops reattaching when the user stops, keeping what had streamed", async () => {
    streamReply = (body, stream) =>
      body.reattach
        ? new Response("down", { status: 503 })
        : new Response(stream.body, { status: 200 });
    const result = await renderChat();
    act(() => result.current.chat.send("Calibrate Q0"));
    await waitFor(() => expect(streams).toHaveLength(1));
    streams[0].push(waitStart);
    await waitFor(() =>
      expect(tools(result.current.chat.liveTurn?.steps)).toEqual([`${WAIT}:running`]),
    );
    streams[0].abort(new TypeError("network error"));
    // The first reattach is refused by a restarting proxy; the chat waits to try again.
    await waitFor(() => expect(result.current.chat.connection?.state).toBe("reconnecting"));
    const tried = streamBodies().length;

    act(() => result.current.chat.stop());
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    expect(lastAssistant(result).stopped).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, 1200));
    expect(streamBodies()).toHaveLength(tried);
  });
});

describe("a stream that goes silent", () => {
  it("counts heartbeats as a live connection but not as an update, and reattaches once they stop", async () => {
    const result = await renderChat();
    act(() => result.current.chat.send("Calibrate Q0"));
    await waitFor(() => expect(streams).toHaveLength(1));
    streams[0].push(waitStart);
    await waitFor(() =>
      expect(tools(result.current.chat.liveTurn?.steps)).toEqual([`${WAIT}:running`]),
    );
    const updatedAt = result.current.chat.connection!.lastUpdateAt;

    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    // A heartbeat arrives before the silence limit: the stream is alive, but nothing was updated.
    await act(async () => {
      vi.advanceTimersByTime(STREAM_SILENCE_MS - 5_000);
      streams[0].push(":\n\n");
      await Promise.resolve();
      await new Promise((resolve) => queueMicrotask(() => resolve(undefined)));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(STREAM_SILENCE_MS - 5_000);
    });
    expect(streams).toHaveLength(1);
    expect(result.current.chat.connection?.lastUpdateAt).toBe(updatedAt);

    // Then the heartbeat stops: the chat takes the stream for dead and reattaches.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    vi.useRealTimers();
    await waitFor(() => expect(streams).toHaveLength(2));
    expect(streamBodies()[1]).toMatchObject({ reattach: true });
  });
});
