import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CopilotChatSessionProvider } from "@/contexts/CopilotChatSessionContext";

import { useCopilotChat, type CopilotBlocksResult } from "../useCopilotChat";

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

let stream: ReturnType<typeof controllableStream>;

beforeEach(() => {
  stream = controllableStream();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/copilot/chat/stream")) {
        init?.signal?.addEventListener("abort", () => stream.abort());
        return new Response(stream.body, { status: 200 });
      }
      if (url.endsWith("/copilot/chat/sessions") && !init?.method) {
        return Response.json({ sessions: [] });
      }
      return Response.json({ session_id: "x", title: "", messages: [] });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function renderChat() {
  const { result } = renderHook(() => useCopilotChat(), { wrapper });
  // Let the initial session list land so it does not replace the new session.
  await waitFor(() => expect(result.current.isLoadingSessions).toBe(false));
  return result;
}

function lastAssistant(result: { current: ReturnType<typeof useCopilotChat> }) {
  const messages = result.current.activeSession?.messages ?? [];
  const last = messages[messages.length - 1];
  expect(last?.role).toBe("assistant");
  return JSON.parse(last.content) as CopilotBlocksResult;
}

describe("useCopilotChat streaming", () => {
  it("builds a live transcript and persists the work as a trace", async () => {
    const result = await renderChat();

    act(() => {
      void result.current.sendMessage("Show T1 for Q00");
    });
    await waitFor(() => expect(result.current.liveTurn).not.toBeNull());

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
      expect(result.current.liveTurn?.steps.map((s) => s.kind)).toEqual(["thinking", "tool"]),
    );
    const thinking = result.current.liveTurn!.steps[0];
    expect(thinking.kind === "thinking" && thinking.text).toBe("Need the timeseries.");

    stream.push(sse("tool_end", { id: "c1", tool: "qdash_get_timeseries", is_error: false }));
    stream.push(sse("delta", { text: "T1 is " }));
    stream.push(sse("delta", { text: "45 us." }));
    await waitFor(() => {
      const steps = result.current.liveTurn?.steps ?? [];
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
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.liveTurn).toBeNull();
    const saved = lastAssistant(result);
    expect(saved.blocks[0].content).toBe("T1 is 45 us.");
    // The answer text is not duplicated into the trace.
    expect(saved.trace?.steps.map((s) => s.kind)).toEqual(["thinking", "tool"]);
    expect(saved.trace?.steps[1]).toMatchObject({ id: "c1", args: { qid: "0" } });
  });

  it("keeps the partial answer when the user stops", async () => {
    const result = await renderChat();

    act(() => {
      void result.current.sendMessage("Explain T2 echo");
    });
    stream.push(sse("delta", { text: "T2 echo measures" }));
    await waitFor(() => expect(result.current.liveTurn?.steps).toHaveLength(1));

    act(() => result.current.stop());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const saved = lastAssistant(result);
    expect(saved.stopped).toBe(true);
    expect(saved.blocks[0].content).toBe("T2 echo measures");
  });

  it("records a stream that ends without a result as an error", async () => {
    const result = await renderChat();

    act(() => {
      void result.current.sendMessage("hi");
    });
    stream.push(sse("delta", { text: "partial" }));
    stream.close();
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.error).toMatch(/closed before/);
    const messages = result.current.activeSession?.messages ?? [];
    expect(messages[messages.length - 1].content).toMatch(/^Error: /);
  });
});
