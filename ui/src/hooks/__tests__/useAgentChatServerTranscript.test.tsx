/**
 * The server records every chat turn: the page shows what it folds while the turn
 * streams, takes the turn's run as the server saved it once the stream ends, and
 * saves its own copy only when the server did not report one.
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  AgentChatSessionProvider,
  useAgentChatSessionContext,
} from "@/contexts/AgentChatSessionContext";
import { readStoredTurns } from "@/lib/agentTurnStore";
import type { AgentBlocksResult } from "@/types/agentChat";

import { useAgentChat } from "../useAgentChat";

vi.mock("@/client/agent/agent", () => ({
  useGetAgentConfig: () => ({ data: undefined }),
}));

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
type Message = Record<string, unknown> & { role: string; content: string };
interface Call {
  url: string;
  method: string;
  body: Record<string, unknown>;
}

const HISTORY: Message[] = [
  { role: "user", content: "Hi" },
  { role: "assistant", content: "Hello" },
];

let streams: Stream[];
let calls: Call[];
let saved: Record<string, Message[]>;

const wrapper = ({ children }: { children: ReactNode }) => (
  <AgentChatSessionProvider owner="alice" project="p1">
    {children}
  </AgentChatSessionProvider>
);

beforeEach(() => {
  streams = [];
  calls = [];
  saved = { s1: [...HISTORY] };
  localStorage.setItem("qdash_current_project_id", "p1");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      const method = init?.method ?? "GET";
      calls.push({ url, method, body });
      if (url.endsWith("/stream")) {
        const stream = controllableStream();
        streams.push(stream);
        init?.signal?.addEventListener("abort", () => stream.abort(init.signal!.reason));
        return new Response(stream.body, { status: 200 });
      }
      if (url.endsWith("/agent/chat/sessions") && method === "GET") {
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
      const match = /\/agent\/chat\/sessions\/([^/]+)$/.exec(url);
      if (match && method === "GET") {
        return Response.json({
          session_id: match[1],
          title: "Chat",
          message_count: saved[match[1]]?.length ?? 0,
          created_at: "2026-11-22T00:00:00Z",
          updated_at: "2026-11-22T00:00:00Z",
          messages: saved[match[1]] ?? [],
        });
      }
      if (match && method === "PATCH") {
        if (body.messages) saved[match[1]] = body.messages as Message[];
        return Response.json({});
      }
      if (url.endsWith("/agent/chat/active")) return Response.json({ running: false });
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
  return { chat: useAgentChat("s1"), store: useAgentChatSessionContext() };
}

async function startTurn(text = "What is T1?") {
  const hook = renderHook(useChatAndStore, { wrapper });
  await waitFor(() => expect(hook.result.current.store.isLoadingSessions).toBe(false));
  act(() => hook.result.current.store.switchSession("s1"));
  await waitFor(() => expect(hook.result.current.chat.session?.messagesLoaded).toBe(true));
  act(() => {
    hook.result.current.chat.send(text);
  });
  await waitFor(() => expect(streams).toHaveLength(1));
  const requestId = calls.find((c) => c.url.endsWith("/stream"))!.body.request_id as string;
  return { hook, requestId };
}

const last = <T,>(list: T[]): T | undefined => list[list.length - 1];
const patches = () => calls.filter((c) => c.method === "PATCH");
const answer = (text: string) => ({
  blocks: [{ type: "text", content: text, chart: null }],
  assessment: null,
});
const content = (message: { content: string } | undefined) =>
  JSON.parse(message?.content ?? "{}") as AgentBlocksResult;

describe("a turn the server records", () => {
  it("sends the turn's start and saves nothing itself; it shows the run the server saved", async () => {
    const { hook, requestId } = await startTurn();
    const request = calls.find((c) => c.url.endsWith("/stream"))!.body;
    expect(request.turn_start).toMatchObject({ index: 2 });
    // The page shows the message but leaves saving it to the server.
    expect(last(hook.result.current.chat.messages)).toMatchObject({
      role: "user",
      content: "What is T1?",
      turnRequestId: requestId,
    });

    streams[0].push(sse("delta", { text: "T1 is" }));
    streams[0].push(sse("result", { ...answer("T1 is 40 us."), entry_id: "17" }));
    // The server's copy differs from the page's fold (its own timings): the server's wins.
    const run: Message[] = [
      { role: "user", content: "What is T1?", turn_request_id: requestId },
      {
        role: "assistant",
        content: JSON.stringify({ ...answer("T1 is 40 us."), trace: { steps: [], durationMs: 5 } }),
        entry_id: "17",
        turn_request_id: requestId,
      },
    ];
    streams[0].push(sse("transcript", { saved: true, request_id: requestId, messages: run }));
    streams[0].close();

    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    const messages = hook.result.current.chat.messages;
    expect(messages).toHaveLength(4);
    expect(content(messages[3]).trace?.durationMs).toBe(5);
    expect(messages[3]).toMatchObject({ entryId: "17", turnRequestId: requestId });
    expect(patches()).toHaveLength(0);
    // The server holds the end: nothing is left to restore after a reload.
    expect(readStoredTurns("alice").s1).toBeUndefined();
  });

  it("folds a replay once when the server attaches to the turn again", async () => {
    const { hook } = await startTurn();
    streams[0].push(sse("delta", { text: "Part" }));
    await waitFor(() => expect(hook.result.current.chat.liveTurn?.steps).toHaveLength(1));
    streams[0].push(sse("restart", {}));
    streams[0].push(sse("delta", { text: "Part" }));
    await waitFor(() => {
      const steps = hook.result.current.chat.liveTurn?.steps ?? [];
      expect(steps.map((s) => (s.kind === "text" ? s.text : ""))).toEqual(["Part"]);
    });
  });

  it("takes the failed run the server saved, reading on past the error", async () => {
    const { hook, requestId } = await startTurn();
    streams[0].push(sse("error", { step: "run_chat", detail: "Agent runtime returned HTTP 500" }));
    const run: Message[] = [
      { role: "user", content: "What is T1?", turn_request_id: requestId },
      {
        role: "assistant",
        content: "Error: Agent runtime returned HTTP 500",
        turn_request_id: requestId,
      },
    ];
    streams[0].push(sse("transcript", { saved: true, request_id: requestId, messages: run }));
    streams[0].close();
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    expect(last(hook.result.current.chat.messages)?.content).toBe(
      "Error: Agent runtime returned HTTP 500",
    );
    expect(patches()).toHaveLength(0);
  });

  it("saves its own copy, and says so, when the server could not save the turn", async () => {
    const { hook, requestId } = await startTurn();
    streams[0].push(sse("result", answer("Done")));
    streams[0].push(sse("transcript", { saved: false, request_id: requestId }));
    streams[0].close();
    await waitFor(() => expect(patches()).toHaveLength(1));
    expect(hook.result.current.chat.notice).toMatch(/could not save/);
    const sent = patches()[0].body.messages as Message[];
    expect(last(sent)).toMatchObject({ role: "assistant", turn_request_id: requestId });
    expect(content(last(sent)).blocks[0].content).toBe("Done");
  });

  it("shows the saved chat when another window changed it, and sends nothing again", async () => {
    const { hook } = await startTurn();
    // Another window's turn ended in the meantime.
    saved.s1 = [
      ...HISTORY,
      { role: "user", content: "Other" },
      { role: "assistant", content: "Ok" },
    ];
    streams[0].push(
      sse("error", {
        step: "init",
        detail: "This chat changed in another window, so the message was not sent.",
        code: "transcript_conflict",
      }),
    );
    streams[0].close();
    await waitFor(() => expect(hook.result.current.chat.messages).toHaveLength(4));
    expect(hook.result.current.chat.messages.map((m) => m.content)).toEqual([
      "Hi",
      "Hello",
      "Other",
      "Ok",
    ]);
    expect(hook.result.current.chat.notice).toMatch(/changed in another window/);
    expect(patches()).toHaveLength(0);
    expect(calls.filter((c) => c.url.endsWith("/stream"))).toHaveLength(1);
    expect(readStoredTurns("alice").s1).toBeUndefined();
  });

  it("sends nothing while another turn of the chat runs, and saves nothing", async () => {
    const { hook } = await startTurn();
    streams[0].push(
      sse("error", {
        step: "init",
        detail: "Another answer is still running in this chat.",
        code: "turn_running",
      }),
    );
    streams[0].close();
    await waitFor(() => expect(hook.result.current.chat.notice).toMatch(/still running/));
    await waitFor(() => expect(hook.result.current.chat.messages).toHaveLength(2));
    expect(patches()).toHaveLength(0);
  });

  it("stops the turn explicitly and keeps what streamed; closing the stream alone stops nothing", async () => {
    const { hook, requestId } = await startTurn();
    streams[0].push(sse("delta", { text: "Partial" }));
    await waitFor(() => expect(hook.result.current.chat.liveTurn?.steps).toHaveLength(1));
    act(() => hook.result.current.chat.stop());
    await waitFor(() => expect(hook.result.current.chat.isStreaming).toBe(false));
    const stop = calls.find((c) => c.url.endsWith("/agent/chat/stop"));
    expect(stop?.body).toEqual({ session_id: "s1", turn_request_id: requestId });
    const kept = last(hook.result.current.chat.messages);
    expect(content(kept).stopped).toBe(true);
    expect(kept?.turnRequestId).toBe(requestId);
  });
});
