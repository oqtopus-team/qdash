import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CopilotChatSessionProvider,
  useCopilotChatSessionContext,
} from "@/contexts/CopilotChatSessionContext";
import type { TaskChatContext, CopilotBlocksResult } from "@/types/copilotChat";

import { canContinueMessages, continuationHistory, useCopilotChat } from "../useCopilotChat";

const copilotConfig = vi.hoisted(() => ({ current: undefined as object | undefined }));
vi.mock("@/client/copilot/copilot", () => ({
  useGetCopilotConfig: () => ({
    data: copilotConfig.current ? { data: copilotConfig.current } : undefined,
  }),
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
    abort: (reason?: unknown) =>
      controller.error(reason ?? new DOMException("aborted", "AbortError")),
  };
}

const wrapper = ({ children }: { children: ReactNode }) => (
  <CopilotChatSessionProvider>{children}</CopilotChatSessionProvider>
);

const CONTEXT: TaskChatContext = {
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
      init?.signal?.addEventListener("abort", () => stream.abort(init.signal!.reason));
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
  copilotConfig.current = undefined;
  localStorage.clear();
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
  it("does not send from a restored session before its messages load", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/copilot/chat/sessions") && !init?.method) {
        return Response.json({
          sessions: [
            {
              session_id: "saved-session",
              title: "Saved chat",
              context: null,
              message_count: 2,
              created_at: "2026-10-05T00:00:00Z",
              updated_at: "2026-10-05T00:01:00Z",
            },
          ],
        });
      }
      if (url.endsWith("/copilot/chat/sessions/saved-session") && !init?.method) {
        return new Promise<Response>(() => {});
      }
      return Response.json({
        session_id: "saved-session",
        title: "Saved chat",
        messages: [],
      });
    });
    const result = await renderChat();

    act(() => result.current.store.switchSession("saved-session"));
    await waitFor(() => expect(result.current.chat.isLoadingMessages).toBe(true));
    act(() => result.current.chat.send("Do not overwrite history"));

    expect(result.current.chat.isStreaming).toBe(false);
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) => String(url).endsWith("/stream") || init?.method === "PATCH",
      ),
    ).toBe(false);
  });

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

    stream.push(
      sse("tool_end", {
        id: "c1",
        tool: "qdash_get_timeseries",
        is_error: false,
        figures: ["exec/1/CheckT1_0.png"],
        evaluation: {
          prompt: "Reference for this experiment:\n## Experiment: CheckT1",
          model: "vllm/ising",
        },
      }),
    );
    stream.push(sse("delta", { text: "T1 is " }));
    stream.push(sse("delta", { text: "45 us." }));
    await waitFor(() => {
      const steps = result.current.chat.liveTurn?.steps ?? [];
      expect(steps[1]).toMatchObject({
        kind: "tool",
        status: "done",
        figures: ["exec/1/CheckT1_0.png"],
        evaluation: {
          prompt: "Reference for this experiment:\n## Experiment: CheckT1",
          model: "vllm/ising",
        },
      });
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
    expect(saved.trace?.steps[1]).toMatchObject({
      id: "c1",
      args: { qid: "0" },
      figures: ["exec/1/CheckT1_0.png"],
      evaluation: {
        prompt: "Reference for this experiment:\n## Experiment: CheckT1",
        model: "vllm/ising",
      },
    });
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
    // Closing the stream is not enough: the runtime is told to abort the turn.
    const stopCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/copilot/chat/stop"),
    );
    expect(stopCall).toBeDefined();
    expect(JSON.parse(String(stopCall![1].body))).toEqual({
      session_id: result.current.chat.session!.id,
    });
  });

  it("shows a composed UI as soon as its tool finishes and keeps it when stopped", async () => {
    const result = await renderChat();
    const ui = {
      version: 1,
      spec: {
        root: "m",
        elements: { m: { type: "Metric", props: { label: "T1", value: 45 }, children: [] } },
      },
      fallback: "- T1: 45",
    };
    const block = { type: "ui", content: "- T1: 45", chart: null, ui };

    act(() => result.current.chat.send("Summarize Q00"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    stream.push(sse("ui", block));
    stream.push(sse("delta", { text: "T1 looks" }));
    await waitFor(() => expect(result.current.chat.liveTurn?.blocks).toEqual([block]));

    act(() => result.current.chat.stop());
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));

    const saved = lastAssistant(result);
    expect(saved.stopped).toBe(true);
    expect(saved.blocks).toEqual([block, { type: "text", content: "T1 looks", chart: null }]);
  });

  it("edits a sent message by resending it with the history before it", async () => {
    const result = await renderChat();

    act(() => result.current.chat.send("Show T1 for Q00"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    stream.push(
      sse("result", {
        blocks: [{ type: "text", content: "Here", chart: null }],
      }),
    );
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    expect(result.current.chat.messages).toHaveLength(2);

    stream = controllableStream();
    fetchMock.mockClear();
    act(() => result.current.chat.editMessage(0, "Show T2 for Q00"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));

    // The old exchange is replaced by the edited question alone.
    expect(result.current.chat.messages.map((m) => m.content)).toEqual(["Show T2 for Q00"]);
    expect(streamRequest().body).toMatchObject({
      message: "Show T2 for Q00",
      conversation_history: [],
    });
  });

  it("ignores edits of assistant messages and empty text", async () => {
    const result = await renderChat();

    act(() => result.current.chat.send("Hello"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    stream.push(sse("result", { blocks: [{ type: "text", content: "Hi", chart: null }] }));
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    fetchMock.mockClear();

    act(() => result.current.chat.editMessage(1, "Not a user message"));
    act(() => result.current.chat.editMessage(0, "   "));

    expect(result.current.chat.isStreaming).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/stream"))).toBe(false);
  });

  it("renames a session locally and on the server", async () => {
    const result = await renderChat();

    act(() => result.current.chat.send("Hello"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    const id = result.current.chat.session!.id;

    act(() => result.current.store.renameSession(id, "  T1 drift  "));
    expect(result.current.chat.session?.title).toBe("T1 drift");
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            String(url).endsWith(`/copilot/chat/sessions/${id}`) &&
            init?.method === "PATCH" &&
            JSON.parse(String(init.body)).title === "T1 drift",
        ),
      ).toBe(true),
    );

    // Blank titles are ignored.
    act(() => result.current.store.renameSession(id, "   "));
    expect(result.current.chat.session?.title).toBe("T1 drift");
  });

  it("stores a rating inside the answer and clears it when given again", async () => {
    const result = await renderChat();

    act(() => result.current.chat.send("Hello"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    stream.push(sse("result", { blocks: [{ type: "text", content: "Hi", chart: null }] }));
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    fetchMock.mockClear();

    act(() => result.current.chat.rateAnswer(1, "down"));
    expect(lastAssistant(result).feedback).toBe("down");
    expect(lastAssistant(result).blocks[0].content).toBe("Hi");
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([, init]) => {
          if (init?.method !== "PATCH") return false;
          const body = JSON.parse(String(init.body)) as {
            messages?: { content: string }[];
          };
          return body.messages?.some((m) => m.content.includes('"feedback":"down"')) ?? false;
        }),
      ).toBe(true),
    );

    act(() => result.current.chat.rateAnswer(1, "down"));
    expect(lastAssistant(result).feedback).toBeUndefined();
    // User messages cannot be rated.
    act(() => result.current.chat.rateAnswer(0, "up"));
    expect(result.current.chat.messages[0].content).toBe("Hello");
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

  it("sends a task chat through the chat endpoint naming its task result", async () => {
    const result = await renderChat();

    act(() => {
      result.current.store.createNewSession(CONTEXT);
    });
    expect(result.current.chat.session?.title).toBe("CheckT1 / 0");

    act(() => result.current.chat.send("Is this fit good?"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));

    const { url, body } = streamRequest();
    expect(url).toMatch(/\/copilot\/chat\/stream$/);
    expect(body).toMatchObject({
      task: { task_name: "CheckT1", qid: "0", execution_id: "exec-1", task_id: "task-1" },
      message: "Is this fit good?",
      session_id: result.current.chat.session?.id,
    });
    // Only the opening turn carries the figures.
    expect(result.current.chat.messages[0].attachedImage).toBe(true);
  });

  it("sends the model and thinking chosen on another surface, also on an edit", async () => {
    const kimi = { provider: "openai-compatible-chat", name: "kimi" };
    copilotConfig.current = {
      chat_models: [{ provider: "openai-compatible-chat", name: "qwen" }, kimi],
    };
    const { result } = renderHook(
      () => ({
        page: useCopilotChat(),
        dock: useCopilotChat(),
        store: useCopilotChatSessionContext(),
      }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.store.isLoadingSessions).toBe(false));
    expect(result.current.page.model.selected).toMatchObject({ label: "qwen", model: null });

    act(() => {
      result.current.dock.model.select("model:openai-compatible-chat:kimi");
      result.current.dock.thinking.select("high");
    });
    act(() => result.current.page.send("Show T1"));
    await waitFor(() => expect(result.current.page.isStreaming).toBe(true));
    expect(streamRequest().body).toMatchObject({ model_override: kimi, thinking_level: "high" });
    stream.push(sse("result", { blocks: [{ type: "text", content: "Here", chart: null }] }));
    stream.close();
    await waitFor(() => expect(result.current.page.isStreaming).toBe(false));

    // Back to the default: no override, so the server's first chat model answers.
    act(() => {
      result.current.dock.model.select("default");
      result.current.dock.thinking.select("auto");
    });
    stream = controllableStream();
    fetchMock.mockClear();
    act(() => result.current.page.editMessage(0, "Show T2"));
    await waitFor(() => expect(result.current.page.isStreaming).toBe(true));
    const body = streamRequest().body;
    expect(body.model_override).toBeNull();
    expect(body).not.toHaveProperty("thinking_level");
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

describe("image turn replay", () => {
  it.each(["retry", "edit"])("preserves the original image on %s", async (action) => {
    const result = await renderChat();
    const images = [{ data: "iVBORw0KGgo=", mimeType: "image/png" }];
    act(() => result.current.chat.send("Evaluate", images));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    stream.push(
      sse("result", {
        blocks: [{ type: "text", content: "Here", chart: null }],
      }),
    );
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    stream = controllableStream();
    fetchMock.mockClear();
    act(() =>
      action === "retry"
        ? result.current.chat.retryLast()
        : result.current.chat.editMessage(0, "Evaluate again"),
    );
    await waitFor(() => expect(streamRequest().body.images).toEqual(images));
    expect(result.current.chat.messages[0].attachments).toEqual([
      "data:image/png;base64,iVBORw0KGgo=",
    ]);
  });

  it("blocks retry and edit when reloaded images cannot be recovered", async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/copilot/chat/sessions") && !init?.method) {
        return Response.json({
          sessions: [{ session_id: "saved", title: "Plot", context: null }],
        });
      }
      return Response.json({
        session_id: "saved",
        title: "Plot",
        context: null,
        messages: [
          { role: "user", content: "Evaluate", attached_image: "1" },
          { role: "assistant", content: "Done" },
        ],
      });
    });
    const result = await renderChat();
    act(() => result.current.store.switchSession("saved"));
    await waitFor(() => expect(result.current.chat.messages).toHaveLength(2));
    expect(result.current.chat.canRetryLast).toBe(false);
    expect(result.current.chat.canEditMessage(0)).toBe(false);
    fetchMock.mockClear();
    act(() => {
      result.current.chat.retryLast();
      result.current.chat.editMessage(0, "Again");
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reports whether a turn was accepted before React renders the active stream", async () => {
    const result = await renderChat();
    act(() => result.current.store.createNewSession(null));
    act(() => {
      expect(result.current.chat.send("First")).toBe(true);
      expect(result.current.chat.send("Second")).toBe(false);
    });
    await waitFor(() => expect(result.current.chat.messages[0]?.content).toBe("First"));
  });
});

describe("turn request IDs", () => {
  const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  const realCrypto = globalThis.crypto;

  function streamBodies() {
    return fetchMock.mock.calls
      .filter(([url]) => String(url).endsWith("/stream"))
      .map(([, init]) => JSON.parse(String(init.body)));
  }

  async function finishTurn(result: Result) {
    stream.push(sse("result", { blocks: [{ type: "text", content: "Ok", chart: null }] }));
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    stream = controllableStream();
  }

  it("sends fresh UUID v4 request IDs when served over plain HTTP", async () => {
    // Insecure contexts expose getRandomValues but not randomUUID.
    const getRandomValues = vi.fn(realCrypto.getRandomValues.bind(realCrypto));
    vi.stubGlobal("crypto", { getRandomValues });
    const result = await renderChat();

    act(() => result.current.chat.send("First"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    await finishTurn(result);
    act(() => result.current.chat.send("Second"));
    await waitFor(() => expect(streamBodies()).toHaveLength(2));

    const [first, second] = streamBodies();
    expect(first.request_id).toMatch(UUID_V4);
    expect(second.request_id).toMatch(UUID_V4);
    // Each turn is its own request; the conversation stays one session.
    expect(second.request_id).not.toBe(first.request_id);
    expect(second.session_id).toBe(first.session_id);
    expect(getRandomValues).toHaveBeenCalled();
  });

  it("uses the native randomUUID in secure contexts", async () => {
    const ids = ["aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"];
    const randomUUID = vi.fn(() => ids.shift()!);
    vi.stubGlobal("crypto", {
      randomUUID,
      getRandomValues: realCrypto.getRandomValues.bind(realCrypto),
    });
    const result = await renderChat();

    act(() => result.current.chat.send("First"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    await finishTurn(result);
    act(() => result.current.chat.send("Second"));
    await waitFor(() => expect(streamBodies()).toHaveLength(2));

    expect(streamBodies().map((body) => body.request_id)).toEqual([
      "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    ]);
    expect(randomUUID).toHaveBeenCalledTimes(2);
  });
});

it("keeps retry available for locally known task chat figures", async () => {
  const result = await renderChat();
  act(() => result.current.store.createNewSession(CONTEXT));
  act(() => result.current.chat.send("Is this fit good?"));
  await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
  stream.push(sse("result", { blocks: [{ type: "text", content: "Here", chart: null }] }));
  stream.close();
  await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
  expect(result.current.chat.canRetryLast).toBe(true);
  expect(result.current.chat.canEditMessage(0)).toBe(true);
});

/** Answer steer requests with `reply`, recording what was sent. */
function replyToSteers(reply: (body: Record<string, unknown>) => Response | Promise<Response>) {
  const base = fetchMock.getMockImplementation() as (
    url: string,
    init?: RequestInit,
  ) => Promise<Response>;
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (String(url).endsWith("/copilot/chat/steer")) return reply(JSON.parse(String(init!.body)));
    return base(url, init);
  });
}

/** Answer steer status lookups with `reply`, recording what was asked. */
function replyToStatus(reply: (body: Record<string, unknown>) => Response | Promise<Response>) {
  const base = fetchMock.getMockImplementation() as (
    url: string,
    init?: RequestInit,
  ) => Promise<Response>;
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (String(url).endsWith("/copilot/chat/steer/status")) {
      return reply(JSON.parse(String(init!.body)));
    }
    return base(url, init);
  });
}

function statusCalls() {
  return fetchMock.mock.calls
    .filter(([url]) => String(url).endsWith("/copilot/chat/steer/status"))
    .map(([, init]) => JSON.parse(String(init.body)));
}

function streamCalls() {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/stream"));
}

function steerCalls() {
  return fetchMock.mock.calls
    .filter(([url]) => String(url).endsWith("/copilot/chat/steer"))
    .map(([, init]) => JSON.parse(String(init.body)));
}

/** The messages last sent to the server for the active session. */
function lastPersisted() {
  const patches = fetchMock.mock.calls.filter(
    ([url, init]) => /\/copilot\/chat\/sessions\//.test(String(url)) && init?.method === "PATCH",
  );
  const body = JSON.parse(String(patches[patches.length - 1][1].body));
  return body.messages as Array<{
    role: string;
    content: string;
    steer?: { request_id: string; entry_id: string | null; placement: string } | null;
  }>;
}

describe("steering an answer in progress", () => {
  it("places a steer where it landed, exactly once, between the answer before it and after it", async () => {
    replyToSteers(() => Response.json({ status: "queued", reason: null, entry_id: null }));
    const result = await renderChat();
    act(() => result.current.chat.send("Calibrate Q4"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    stream.push(sse("tool_start", { id: "w1", tool: "wait_calibration", label: "Wait" }));
    await waitFor(() => expect(result.current.chat.liveTurn?.steps).toHaveLength(1));

    act(() => {
      expect(result.current.chat.steer("Use Q5 instead")).toBe(true);
    });
    await waitFor(() => expect(result.current.chat.steers[0]?.status).toBe("queued"));
    const [{ request_id: requestId, ...sent }] = steerCalls();
    // It names the turn it was sent to: the stream request's own ID.
    expect(sent).toEqual({
      session_id: result.current.chat.session!.id,
      turn_request_id: streamRequest().body.request_id,
      message: "Use Q5 instead",
    });
    expect(typeof sent.turn_request_id).toBe("string");

    stream.push(sse("tool_end", { id: "w1", tool: "wait_calibration", is_error: false }));
    const placed = {
      request_id: requestId,
      status: "applied",
      entry_id: "4",
      text: "Use Q5 instead",
      result: { blocks: [], assessment: null },
    };
    stream.push(sse("steer", placed));
    // A repeated report of the same steer changes nothing.
    stream.push(sse("steer", placed));
    stream.push(sse("delta", { text: "Using Q5." }));
    stream.push(
      sse("result", {
        blocks: [{ type: "text", content: "Using Q5.", chart: null }],
        assessment: null,
        entry_id: "5",
      }),
    );
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));

    const messages = result.current.chat.messages;
    expect(messages.map((m) => m.role)).toEqual(["user", "assistant", "user", "assistant"]);
    // The work before the steer stays with the answer it belongs to.
    const before = JSON.parse(messages[1].content) as CopilotBlocksResult;
    expect(before.blocks).toEqual([]);
    expect(before.trace?.steps).toMatchObject([{ kind: "tool", id: "w1", status: "done" }]);
    expect(messages[2].content).toBe("Use Q5 instead");
    const after = JSON.parse(messages[3].content) as CopilotBlocksResult;
    expect(after.blocks[0].content).toBe("Using Q5.");
    expect(after.trace).toBeUndefined();
    // The final answer's runtime entry is kept with the message, not in its blocks.
    expect(messages[3].entryId).toBe("5");
    expect(after).not.toHaveProperty("entry_id");
    // The answer a steer closed off has no entry of its own here.
    expect(messages[1].entryId).toBeUndefined();
    expect(result.current.chat.steers).toEqual([]);
    expect(lastPersisted().map((m) => m.role)).toEqual(["user", "assistant", "user", "assistant"]);
  });

  it("splits the answer a steer follows up from the run that answers the steer", async () => {
    replyToSteers(() => Response.json({ status: "queued" }));
    const result = await renderChat();
    act(() => result.current.chat.send("What is T1?"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    stream.push(sse("delta", { text: "T1 is 42 us." }));
    await waitFor(() => expect(result.current.chat.liveTurn?.steps).toHaveLength(1));
    act(() => {
      result.current.chat.steer("And T2?");
    });
    await waitFor(() => expect(steerCalls()).toHaveLength(1));
    stream.push(
      sse("steer", {
        request_id: steerCalls()[0].request_id,
        status: "applied",
        entry_id: "3",
        text: "And T2?",
        result: {
          blocks: [{ type: "text", content: "T1 is 42 us.", chart: null }],
          assessment: null,
        },
      }),
    );
    stream.push(sse("delta", { text: "T2 is 30 us." }));
    stream.push(
      sse("result", {
        blocks: [{ type: "text", content: "T2 is 30 us.", chart: null }],
        assessment: null,
      }),
    );
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));

    expect(result.current.chat.messages.map((m) => m.content)).toEqual([
      "What is T1?",
      JSON.stringify({
        blocks: [{ type: "text", content: "T1 is 42 us.", chart: null }],
        assessment: null,
      }),
      "And T2?",
      JSON.stringify({
        blocks: [{ type: "text", content: "T2 is 30 us.", chart: null }],
        assessment: null,
      }),
    ]);
  });

  /** A turn streaming, with one steer the runtime admitted (queued). */
  async function steeredTurn(result: Result, text = "Also plot it") {
    act(() => result.current.chat.send("Long job"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    act(() => {
      result.current.chat.steer(text);
    });
    await waitFor(() =>
      expect(result.current.chat.steers.find((s) => s.text === text)?.status).toBe("queued"),
    );
    return steerCalls().find((c) => c.message === text)!.request_id as string;
  }

  it("after a stop, keeps a steer unconfirmed until the store says, then offers to resend one never read", async () => {
    replyToSteers(() => Response.json({ status: "queued" }));
    let withdrawn = false;
    replyToStatus(() =>
      Response.json(withdrawn ? { status: "withdrawn", reason: "aborted" } : { status: "queued" }),
    );
    const result = await renderChat();
    const requestId = await steeredTurn(result);

    act(() => result.current.chat.stop());
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    // The stop says nothing about whether the answer read it: not "not delivered", and no resend.
    expect(result.current.chat.steers[0].status).toBe("unconfirmed");
    expect(result.current.chat.canContinue).toBe(false);
    await waitFor(() => expect(statusCalls()).toHaveLength(1));
    expect(statusCalls()[0]).toEqual({
      session_id: result.current.chat.session!.id,
      request_id: requestId,
    });
    // Still queued while the runtime stops: asked again until it settles.
    withdrawn = true;
    await waitFor(() =>
      expect(result.current.chat.steers).toMatchObject([
        { text: "Also plot it", status: "withdrawn", reason: "aborted" },
      ]),
    );
    expect(result.current.chat.messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    // The lookups never sent the steer again.
    expect(steerCalls()).toHaveLength(1);

    stream = controllableStream();
    act(() => result.current.chat.resendSteer(requestId));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    expect(result.current.chat.steers).toEqual([]);
    const shown = result.current.chat.messages;
    expect(shown[shown.length - 1]?.content).toBe("Also plot it");
  });

  it("places a steer the runtime read just before a stop, once, and keeps it across a reload", async () => {
    replyToSteers(() => Response.json({ status: "queued" }));
    replyToStatus(() => Response.json({ status: "applied", entry_id: "4", submission_id: "3" }));
    const result = await renderChat();
    const requestId = await steeredTurn(result);
    stream.push(sse("delta", { text: "Working" }));
    await waitFor(() => expect(result.current.chat.liveTurn?.steps.length).toBeGreaterThan(0));

    act(() => result.current.chat.stop());
    await waitFor(() => expect(result.current.chat.steers).toEqual([]));
    const messages = result.current.chat.messages;
    expect(messages.map((m) => m.role)).toEqual(["user", "assistant", "user"]);
    expect(messages[2]).toMatchObject({
      content: "Also plot it",
      steer: { requestId, entryId: "4", placement: "approximate" },
    });
    // Saved, so a reload shows what Continue would answer.
    const saved = lastPersisted();
    expect(saved[2]).toMatchObject({
      role: "user",
      content: "Also plot it",
      steer: { request_id: requestId, entry_id: "4", placement: "approximate" },
    });
    expect(streamCalls()).toHaveLength(1);
    expect(steerCalls()).toHaveLength(1);

    // Reload: a new provider reads the saved messages back.
    const id = result.current.chat.session!.id;
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/copilot/chat/sessions") && !init?.method) {
        return Response.json({
          sessions: [
            {
              session_id: id,
              title: "Long job",
              context: null,
              message_count: saved.length,
              created_at: "2026-11-16T00:00:00Z",
              updated_at: "2026-11-16T00:01:00Z",
            },
          ],
        });
      }
      return Response.json({ session_id: id, title: "Long job", messages: saved });
    });
    const reloaded = await renderChat();
    act(() => reloaded.current.store.switchSession(id));
    await waitFor(() => expect(reloaded.current.chat.messages).toHaveLength(3));
    expect(reloaded.current.chat.messages[2]).toMatchObject({
      role: "user",
      content: "Also plot it",
      steer: { requestId, entryId: "4", placement: "approximate" },
    });
  });

  it("places a steer applied by its own request when the connection dropped before the stream said", async () => {
    replyToSteers(() => Response.json({ status: "applied", entry_id: "4", submission_id: "3" }));
    const result = await renderChat();
    act(() => result.current.chat.send("Long job"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    act(() => {
      result.current.chat.steer("Use Q5");
    });
    // The stream is still going: it reports where the steer landed, so nothing is placed yet.
    await waitFor(() => expect(result.current.chat.steers[0]?.status).toBe("delivered"));
    expect(result.current.chat.messages.some((m) => m.steer)).toBe(false);
    stream.abort(new TypeError("network error"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    await waitFor(() => expect(result.current.chat.steers).toEqual([]));
    const placed = result.current.chat.messages.filter((m) => m.steer);
    expect(placed).toMatchObject([
      { content: "Use Q5", steer: { entryId: "4", placement: "approximate" } },
    ]);
    expect(lastPersisted().filter((m) => m.steer)).toHaveLength(1);
    expect(statusCalls()).toHaveLength(0);
  });

  it("orders late receipts by where they landed, not by when they arrived", async () => {
    replyToSteers(() => Response.json({ status: "queued" }));
    const entries: Record<string, string> = {};
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    replyToStatus(async ({ request_id }) => {
      const entry = entries[String(request_id)];
      // The receipt of the earlier steer arrives last.
      if (entry === "5") await gate;
      else setTimeout(release, 20);
      return Response.json({ status: "applied", entry_id: entry });
    });
    const result = await renderChat();
    const first = await steeredTurn(result, "First");
    act(() => {
      result.current.chat.steer("Second");
    });
    await waitFor(() => expect(result.current.chat.steers[1]?.status).toBe("queued"));
    const second = steerCalls()[1].request_id as string;
    entries[first] = "5";
    entries[second] = "9";

    act(() => result.current.chat.stop());
    await waitFor(() => expect(result.current.chat.steers).toEqual([]));
    expect(result.current.chat.messages.filter((m) => m.steer).map((m) => m.content)).toEqual([
      "First",
      "Second",
    ]);
  });

  it("never sends an unconfirmed steer again; it asks the store, and says so when that fails", async () => {
    // The steer request got no reply, twice.
    replyToSteers(() => Promise.reject(new TypeError("network error")));
    let storeDown = true;
    replyToStatus(() =>
      storeDown
        ? new Response(JSON.stringify({ detail: "not reachable" }), { status: 502 })
        : Response.json({ status: "not_found" }),
    );
    const result = await renderChat();
    act(() => result.current.chat.send("Long job"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    act(() => {
      result.current.chat.steer("Use Q5");
    });
    await waitFor(() => expect(statusCalls()).toHaveLength(1));
    act(() => result.current.chat.stop());
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    await waitFor(() =>
      expect(result.current.chat.steers[0]).toMatchObject({
        status: "unconfirmed",
        checking: false,
      }),
    );
    // Not resendable while not confirmed, and Continue waits too.
    act(() => result.current.chat.resendSteer(result.current.chat.steers[0].requestId));
    expect(streamCalls()).toHaveLength(1);
    expect(result.current.chat.canContinue).toBe(false);
    expect(steerCalls()).toHaveLength(2);

    // The store answers: it never saw it (and will not admit it later).
    storeDown = false;
    const before = statusCalls().length;
    act(() => result.current.chat.checkSteer(result.current.chat.steers[0].requestId));
    await waitFor(() =>
      expect(result.current.chat.steers[0]).toMatchObject({
        status: "rejected",
        reason: "not_found",
      }),
    );
    expect(statusCalls()).toHaveLength(before + 1);
    expect(steerCalls()).toHaveLength(2);
  });

  it("settles a steer whose reply came after its stream ended by asking, not by trusting queued", async () => {
    let answer!: (r: Response) => void;
    replyToSteers(() => new Promise<Response>((resolve) => (answer = resolve)));
    replyToStatus(() => Response.json({ status: "withdrawn", reason: "aborted" }));
    const result = await renderChat();
    act(() => result.current.chat.send("Long job"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    act(() => {
      result.current.chat.steer("Use Q5");
    });
    await waitFor(() => expect(steerCalls()).toHaveLength(1));
    act(() => result.current.chat.stop());
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    // Its request is still on its way: the reply settles it, not a lookup.
    expect(result.current.chat.steers[0].status).toBe("sending");
    expect(statusCalls()).toHaveLength(0);
    answer(Response.json({ status: "queued" }));
    await waitFor(() =>
      expect(result.current.chat.steers[0]).toMatchObject({
        status: "withdrawn",
        reason: "aborted",
      }),
    );
  });

  it("reports a steer refused because the answer had finished, without starting anything", async () => {
    const result = await renderChat();
    replyToSteers(() =>
      Response.json({ status: "rejected", reason: "idle", entry_id: null }, { status: 200 }),
    );
    act(() => result.current.chat.send("hi"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    act(() => {
      result.current.chat.steer("one more");
    });
    await waitFor(() => expect(result.current.chat.steers[0]?.status).toBe("rejected"));
    // The stream's end does not overwrite a settled steer.
    stream.push(
      sse("result", { blocks: [{ type: "text", content: "Hi", chart: null }], assessment: null }),
    );
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    expect(result.current.chat.steers[0].status).toBe("rejected");
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/stream"))).toHaveLength(1);
  });

  it("marks a steer withdrawn by the runtime when the run failed", async () => {
    replyToSteers(() => Response.json({ status: "queued" }));
    const result = await renderChat();
    act(() => result.current.chat.send("Summarize"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    act(() => {
      result.current.chat.steer("Shorter");
    });
    await waitFor(() => expect(result.current.chat.steers[0]?.status).toBe("queued"));
    stream.push(
      sse("steer", {
        request_id: steerCalls()[0].request_id,
        status: "withdrawn",
        reason: "run_failed",
      }),
    );
    stream.push(sse("error", { detail: "conversation was not answered: model_error" }));
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    expect(result.current.chat.steers).toMatchObject([
      { status: "withdrawn", reason: "run_failed" },
    ]);
    expect(result.current.chat.canContinue).toBe(true);
  });

  it("refuses to steer when nothing is streaming", async () => {
    const result = await renderChat();
    act(() => {
      expect(result.current.chat.steer("x")).toBe(false);
    });
    expect(steerCalls()).toHaveLength(0);
  });
});

describe("continuing an answer that ended early", () => {
  async function failedTurn(result: Result) {
    act(() => result.current.chat.send("Explain T1"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    stream.push(sse("error", { detail: "conversation was not answered: model_error" }));
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    stream = controllableStream();
  }

  it("continues without a new user message and replaces the error with the answer", async () => {
    const result = await renderChat();
    await failedTurn(result);
    expect(result.current.chat.canContinue).toBe(true);

    fetchMock.mockClear();
    act(() => result.current.chat.continueLast());
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    const { body } = streamRequest();
    expect(body).toMatchObject({ message: "", continue_run: true });
    expect(body.conversation_history).toEqual([{ role: "user", content: "Explain T1" }]);
    expect(typeof body.request_id).toBe("string");

    stream.push(
      sse("result", {
        blocks: [{ type: "text", content: "T1 is…", chart: null }],
        assessment: null,
      }),
    );
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    expect(result.current.chat.messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(lastAssistant(result).blocks[0].content).toBe("T1 is…");
    expect(result.current.chat.canContinue).toBe(false);
  });

  it("keeps a stopped answer and adds the continuation after it", async () => {
    const result = await renderChat();
    act(() => result.current.chat.send("Explain T2"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    stream.push(sse("delta", { text: "T2 is" }));
    await waitFor(() => expect(result.current.chat.liveTurn?.steps).toHaveLength(1));
    act(() => result.current.chat.stop());
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    expect(result.current.chat.canContinue).toBe(true);
    stream = controllableStream();

    act(() => result.current.chat.continueLast());
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    stream.push(
      sse("result", {
        blocks: [{ type: "text", content: "the decay", chart: null }],
        assessment: null,
      }),
    );
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    const roles = result.current.chat.messages.map((m) => m.role);
    expect(roles).toEqual(["user", "assistant", "assistant"]);
    expect(JSON.parse(result.current.chat.messages[1].content).stopped).toBe(true);
  });

  it("treats nothing to continue as a notice, not an answer or an error", async () => {
    const result = await renderChat();
    await failedTurn(result);
    const before = result.current.chat.messages;

    act(() => result.current.chat.continueLast());
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    stream.push(sse("noop", { reason: "nothing_to_answer" }));
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    expect(result.current.chat.messages).toEqual(before);
    expect(result.current.chat.notice).toMatch(/Nothing to continue/);
    act(() => result.current.chat.dismissNotice());
    expect(result.current.chat.notice).toBeNull();
  });

  it("shows why a continue was refused and leaves the chat as it was", async () => {
    const result = await renderChat();
    await failedTurn(result);
    const before = result.current.chat.messages;

    act(() => result.current.chat.continueLast());
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    stream.push(sse("error", { detail: "The assistant is waiting for your answer" }));
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    expect(result.current.chat.messages).toEqual(before);
    expect(result.current.chat.notice).toBe("The assistant is waiting for your answer");
  });
});

describe("canContinueMessages", () => {
  const stopped = (blocks: unknown[]) =>
    JSON.stringify({ blocks, assessment: null, stopped: true });

  it("offers continue only after a stopped or failed answer that waits for nobody", () => {
    const user = { role: "user" as const, content: "q" };
    expect(canContinueMessages([])).toBe(false);
    expect(canContinueMessages([user])).toBe(false);
    expect(canContinueMessages([user, { role: "assistant", content: "Error: x" }])).toBe(true);
    expect(canContinueMessages([{ role: "assistant", content: "Error: x" }])).toBe(false);
    expect(canContinueMessages([user, { role: "assistant", content: stopped([]) }])).toBe(true);
    expect(
      canContinueMessages([
        user,
        { role: "assistant", content: JSON.stringify({ blocks: [], assessment: null }) },
      ]),
    ).toBe(false);
    expect(
      canContinueMessages([
        user,
        { role: "assistant", content: stopped([{ type: "approval", approval: {} }]) },
      ]),
    ).toBe(false);
    expect(canContinueMessages([user, { role: "assistant", content: "plain" }])).toBe(false);
  });

  it("counts steers the stopped answer read as part of it, keeping every blocker", () => {
    const user = { role: "user" as const, content: "q" };
    const steer = (requestId: string) => ({
      role: "user" as const,
      content: `steer ${requestId}`,
      steer: { requestId, entryId: "4", placement: "approximate" as const },
    });
    const stoppedAnswer = { role: "assistant" as const, content: stopped([]) };
    const error = { role: "assistant" as const, content: "Error: x" };
    expect(canContinueMessages([user, stoppedAnswer, steer("a")])).toBe(true);
    expect(canContinueMessages([user, stoppedAnswer, steer("a"), steer("b")])).toBe(true);
    expect(canContinueMessages([user, error, steer("a")])).toBe(true);
    // A user's own new message is not a steer: there is nothing to continue.
    expect(canContinueMessages([user, stoppedAnswer, user])).toBe(false);
    // Only steers: no answer to continue.
    expect(canContinueMessages([steer("a")])).toBe(false);
    for (const card of ["ask", "approval", "edit"]) {
      expect(
        canContinueMessages([
          user,
          { role: "assistant", content: stopped([{ type: card }]) },
          steer("a"),
        ]),
      ).toBe(false);
    }
    // A completed answer before a steer is not continued.
    expect(
      canContinueMessages([
        user,
        { role: "assistant", content: JSON.stringify({ blocks: [], assessment: null }) },
        steer("a"),
      ]),
    ).toBe(false);
    // The failed answer's error is dropped from what a continue sends; the steer stays.
    expect(continuationHistory([user, error, steer("a")])).toEqual([user, steer("a")]);
    expect(continuationHistory([user, stoppedAnswer, steer("a")])).toEqual([
      user,
      stoppedAnswer,
      steer("a"),
    ]);
  });
});
