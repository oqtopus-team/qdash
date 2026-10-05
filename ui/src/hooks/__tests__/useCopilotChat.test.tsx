import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CopilotChatSessionProvider,
  useCopilotChatSessionContext,
} from "@/contexts/CopilotChatSessionContext";
import type { AnalysisContext, CopilotBlocksResult } from "@/types/copilotChat";

import { useCopilotChat } from "../useCopilotChat";

vi.mock("@/client/copilot/copilot", () => ({
  useGetCopilotConfig: () => ({ data: undefined }),
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
    // What a real fetch does to the body when its signal aborts.
    abort: () => controller.error(new DOMException("aborted", "AbortError")),
  };
}

const wrapper = ({ children }: { children: ReactNode }) => (
  <CopilotChatSessionProvider>{children}</CopilotChatSessionProvider>
);

const CONTEXT: AnalysisContext = {
  taskName: "CheckT1",
  chipId: "64Q",
  qid: "0",
  executionId: "exec-1",
  taskId: "task-1",
};

let stream: ReturnType<typeof controllableStream>;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  stream = controllableStream();
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/stream")) {
      init?.signal?.addEventListener("abort", () => stream.abort());
      return new Response(stream.body, { status: 200 });
    }
    if (url.endsWith("/copilot/chat/sessions") && !init?.method) {
      return Response.json({ sessions: [] });
    }
    return Response.json({ session_id: "x", title: "", messages: [] });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** The chat as one surface sees it, plus the shared store. */
function useChatAndStore() {
  return { chat: useCopilotChat(), store: useCopilotChatSessionContext() };
}

async function renderChat() {
  const { result } = renderHook(useChatAndStore, { wrapper });
  // Let the initial session list land.
  await waitFor(() => expect(result.current.store.isLoadingSessions).toBe(false));
  return result;
}

type Result = Awaited<ReturnType<typeof renderChat>>;

function lastAssistant(result: Result) {
  const messages = result.current.chat.messages;
  const last = messages[messages.length - 1];
  expect(last?.role).toBe("assistant");
  return JSON.parse(last.content) as CopilotBlocksResult;
}

function streamRequest() {
  const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/stream"));
  expect(call).toBeDefined();
  return { url: String(call![0]), body: JSON.parse(String(call![1].body)) };
}

describe("useCopilotChat streaming", () => {
  it("builds a live transcript and persists the work as a trace", async () => {
    const result = await renderChat();

    act(() => result.current.chat.send("Show T1 for Q00"));
    await waitFor(() => expect(result.current.chat.liveTurn).not.toBeNull());

    stream.push(sse("thinking", { text: "Need the " }));
    stream.push(sse("thinking", { text: "timeseries." }));
    stream.push(
      sse("tool_start", {
        id: "c1",
        tool: "qdash_get_timeseries",
        label: "Get timeseries",
        args: { qid: "0" },
      }),
    );
    await waitFor(() =>
      expect(result.current.chat.liveTurn?.steps.map((s) => s.kind)).toEqual(["thinking", "tool"]),
    );
    const thinking = result.current.chat.liveTurn!.steps[0];
    expect(thinking.kind === "thinking" && thinking.text).toBe("Need the timeseries.");

    stream.push(sse("tool_end", { id: "c1", tool: "qdash_get_timeseries", is_error: false }));
    stream.push(sse("delta", { text: "T1 is " }));
    stream.push(sse("delta", { text: "45 us." }));
    await waitFor(() => {
      const steps = result.current.chat.liveTurn?.steps ?? [];
      expect(steps[1]).toMatchObject({ kind: "tool", status: "done" });
      expect(steps[2]).toEqual({ kind: "text", text: "T1 is 45 us." });
    });

    stream.push(
      sse("result", {
        blocks: [{ type: "text", content: "T1 is 45 us.", chart: null }],
        assessment: null,
      }),
    );
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));

    expect(result.current.chat.liveTurn).toBeNull();
    const saved = lastAssistant(result);
    expect(saved.blocks[0].content).toBe("T1 is 45 us.");
    // The answer text is not duplicated into the trace.
    expect(saved.trace?.steps.map((s) => s.kind)).toEqual(["thinking", "tool"]);
    expect(saved.trace?.steps[1]).toMatchObject({ id: "c1", args: { qid: "0" } });
    expect(streamRequest().url).toMatch(/\/copilot\/chat\/stream$/);
  });

  it("keeps the partial answer when the user stops", async () => {
    const result = await renderChat();

    act(() => result.current.chat.send("Explain T2 echo"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    stream.push(sse("delta", { text: "T2 echo measures" }));
    await waitFor(() => expect(result.current.chat.liveTurn?.steps).toHaveLength(1));

    act(() => result.current.chat.stop());
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));

    const saved = lastAssistant(result);
    expect(saved.stopped).toBe(true);
    expect(saved.blocks[0].content).toBe("T2 echo measures");
  });

  it("records a stream that ends without a result as an error", async () => {
    const result = await renderChat();

    act(() => result.current.chat.send("hi"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    stream.push(sse("delta", { text: "partial" }));
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));

    const messages = result.current.chat.messages;
    expect(messages[messages.length - 1].content).toMatch(/^Error: .*closed before/);
  });

  it("sends analysis chats through the analyze endpoint with their result", async () => {
    const result = await renderChat();

    act(() => {
      result.current.store.createNewSession(CONTEXT);
    });
    expect(result.current.chat.session?.title).toBe("CheckT1 / 0");

    act(() => result.current.chat.send("Is this fit good?"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));

    const { url, body } = streamRequest();
    expect(url).toMatch(/\/copilot\/analyze\/stream$/);
    expect(body).toMatchObject({
      task_name: "CheckT1",
      qid: "0",
      execution_id: "exec-1",
      task_id: "task-1",
      message: "Is this fit good?",
      session_id: result.current.chat.session?.id,
    });
    // Only the opening turn carries the figures.
    expect(result.current.chat.messages[0].attachedImage).toBe(true);
  });

  it("shares one streaming turn between every surface showing the chat", async () => {
    const { result } = renderHook(
      () => ({ sidebar: useCopilotChat(), floating: useCopilotChat() }),
      { wrapper },
    );

    act(() => result.current.floating.send("hello"));
    await waitFor(() => expect(result.current.floating.isStreaming).toBe(true));
    stream.push(sse("delta", { text: "Hi" }));

    await waitFor(() =>
      expect(result.current.sidebar.liveTurn?.steps).toEqual([{ kind: "text", text: "Hi" }]),
    );
    act(() => result.current.sidebar.stop());
    await waitFor(() => expect(result.current.floating.isStreaming).toBe(false));
  });
});
