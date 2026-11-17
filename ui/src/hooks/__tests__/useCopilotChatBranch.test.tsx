import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CopilotChatSessionProvider,
  useCopilotChatSessionContext,
} from "@/contexts/CopilotChatSessionContext";

import { isBranchableAnswer, useCopilotChat } from "../useCopilotChat";

vi.mock("@/client/copilot/copilot", () => ({
  useGetCopilotConfig: () => ({ data: undefined }),
  useGetChatGPTConnection: () => ({ data: undefined, isPending: false, isError: true }),
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
  };
}

const wrapper = ({ children }: { children: ReactNode }) => (
  <CopilotChatSessionProvider>{children}</CopilotChatSessionProvider>
);

const answer = (text: string, extra: Record<string, unknown> = {}) =>
  JSON.stringify({
    blocks: [{ type: "text", content: text, chart: null }],
    assessment: null,
    ...extra,
  });

/** A saved chat: answers with and without their runtime entry, and ones that cannot be branched. */
const SAVED = [
  { role: "user", content: "Q1" },
  { role: "assistant", content: answer("A1"), entry_id: "5" },
  { role: "user", content: "Q2" },
  { role: "assistant", content: answer("A2, saved before entry IDs") },
  { role: "user", content: "Q3" },
  { role: "assistant", content: answer("Partial", { stopped: true }), entry_id: "8" },
  { role: "user", content: "Q4" },
  {
    role: "assistant",
    content: JSON.stringify({
      blocks: [
        { type: "ask", content: null, chart: null, ask: { question: "Which?", options: [] } },
      ],
      assessment: null,
    }),
    entry_id: "11",
  },
  { role: "user", content: "Q5" },
  { role: "assistant", content: answer("A5"), entry_id: "14" },
];

const BRANCH = {
  session_id: "b-new",
  title: "Saved chat",
  context: null,
  message_count: 2,
  branch: { source_session_id: "saved", source_entry_id: "5" },
  created_at: "2026-11-16T00:00:00Z",
  updated_at: "2026-11-16T00:00:00Z",
  messages: SAVED.slice(0, 2),
};

let stream: ReturnType<typeof controllableStream>;
let fetchMock: ReturnType<typeof vi.fn>;
let branchReply: () => Promise<Response>;

beforeEach(() => {
  stream = controllableStream();
  branchReply = async () => Response.json(BRANCH);
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/stream")) return new Response(stream.body, { status: 200 });
    if (url.endsWith("/branches")) return branchReply();
    if (url.endsWith("/copilot/chat/sessions") && !init?.method) {
      return Response.json({
        sessions: [
          {
            session_id: "saved",
            title: "Saved chat",
            context: null,
            message_count: SAVED.length,
            created_at: "2026-11-15T00:00:00Z",
            updated_at: "2026-11-15T00:00:00Z",
          },
        ],
      });
    }
    if (url.endsWith("/copilot/chat/sessions/saved") && !init?.method) {
      return Response.json({
        session_id: "saved",
        title: "Saved chat",
        context: null,
        messages: SAVED,
        created_at: "2026-11-15T00:00:00Z",
        updated_at: "2026-11-15T00:00:00Z",
      });
    }
    return Response.json({ session_id: "x", title: "", messages: [] });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function useChatAndStore() {
  return { chat: useCopilotChat(), store: useCopilotChatSessionContext() };
}

async function openSaved() {
  const { result } = renderHook(useChatAndStore, { wrapper });
  await waitFor(() => expect(result.current.store.isLoadingSessions).toBe(false));
  act(() => result.current.store.switchSession("saved"));
  await waitFor(() => expect(result.current.chat.messages).toHaveLength(SAVED.length));
  return result;
}

function branchCalls() {
  return fetchMock.mock.calls
    .filter(([url]) => String(url).endsWith("/branches"))
    .map(([url, init]) => ({ url: String(url), body: JSON.parse(String(init.body)) }));
}

describe("an answer's runtime entry", () => {
  it("is kept with the answer from the stream's result and saved with it, outside the blocks", async () => {
    const { result } = renderHook(useChatAndStore, { wrapper });
    await waitFor(() => expect(result.current.store.isLoadingSessions).toBe(false));
    act(() => result.current.chat.send("Show T1"));
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(true));
    // Nothing can be branched while an answer streams.
    expect(result.current.chat.canBranchAt(0)).toBe(false);
    stream.push(
      sse("result", {
        blocks: [{ type: "text", content: "T1 is 45 us.", chart: null }],
        assessment: null,
        entry_id: "17",
      }),
    );
    stream.close();
    await waitFor(() => expect(result.current.chat.isStreaming).toBe(false));
    const saved = result.current.chat.messages[1];
    expect(saved.entryId).toBe("17");
    expect(JSON.parse(saved.content)).not.toHaveProperty("entry_id");
    expect(result.current.chat.canBranchAt(1)).toBe(true);
    await waitFor(() => {
      const patches = fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH");
      const body = JSON.parse(String(patches[patches.length - 1]?.[1].body));
      expect(body.messages[1]).toMatchObject({ role: "assistant", entry_id: "17" });
    });
  });

  it("is loaded with a saved chat; only complete answers that have one can be branched from", async () => {
    const result = await openSaved();
    const branchable = SAVED.map((_m, i) => result.current.chat.canBranchAt(i));
    expect(branchable).toEqual([
      false,
      true,
      false,
      false,
      false,
      false,
      false,
      false,
      false,
      true,
    ]);
    // Never inferred from the position: the answer saved without an entry has none.
    expect(result.current.chat.messages[3].entryId).toBeUndefined();
    expect(isBranchableAnswer({ role: "assistant", content: "Error: boom", entryId: "3" })).toBe(
      false,
    );
  });
});

describe("branching from an answer", () => {
  it("creates the branch once for repeated clicks and switches to it", async () => {
    const result = await openSaved();
    let release!: (response: Response) => void;
    branchReply = () => new Promise<Response>((resolve) => (release = resolve));
    act(() => {
      result.current.chat.branchFrom(1);
      result.current.chat.branchFrom(1);
    });
    await waitFor(() => expect(result.current.chat.branchingIndex).toBe(1));
    // No other answer can be branched meanwhile.
    expect(result.current.chat.canBranchAt(9)).toBe(false);
    act(() => result.current.chat.branchFrom(9));
    const calls = branchCalls();
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toMatch(/\/copilot\/chat\/sessions\/saved\/branches$/);
    expect(calls[0].body).toMatchObject({ entry_id: "5" });
    expect(typeof calls[0].body.target_session_id).toBe("string");

    await act(async () => release(Response.json(BRANCH)));
    await waitFor(() => expect(result.current.store.activeSessionId).toBe("b-new"));
    expect(result.current.chat.session?.branch).toEqual({
      sourceSessionId: "saved",
      sourceEntryId: "5",
    });
    expect(result.current.chat.messages.map((m) => m.content)).toEqual([
      SAVED[0].content,
      SAVED[1].content,
    ]);
    expect(result.current.chat.messages[1].entryId).toBe("5");
    expect(result.current.chat.isLoadingMessages).toBe(false);
    expect(result.current.store.sessions.map((s) => s.id)).toEqual(["b-new", "saved"]);
  });

  it("says why a branch was refused, and retries one that may have been made under the same ID", async () => {
    const result = await openSaved();
    branchReply = async () =>
      Response.json({ detail: "The Copilot runtime is not reachable; try again" }, { status: 502 });
    await act(async () => {
      expect(await result.current.store.branchFrom("saved", "5")).toBeNull();
    });
    expect(result.current.chat.notice).toMatch(
      /Could not branch from this answer: .*not reachable/,
    );
    expect(result.current.chat.branchingIndex).toBe(-1);

    branchReply = async () =>
      Response.json(
        {
          detail: "This chat or one of its branches is answering. Try again when it has finished.",
        },
        { status: 409 },
      );
    await act(async () => {
      await result.current.store.branchFrom("saved", "5");
    });
    expect(result.current.chat.notice).toMatch(/one of its branches is answering/);

    branchReply = async () => Response.json(BRANCH);
    await act(async () => {
      expect(await result.current.store.branchFrom("saved", "5")).toBe("b-new");
    });
    branchReply = async () =>
      Response.json({ detail: "This answer is not saved with its runtime entry" }, { status: 404 });
    await act(async () => {
      expect(await result.current.store.branchFrom("saved", "5")).toBeNull();
    });
    branchReply = async () => Response.json(BRANCH);
    await act(async () => {
      await result.current.store.branchFrom("saved", "5");
    });
    const [failed, busy, made, missing, fresh] = branchCalls().map(
      (call) => call.body.target_session_id,
    );
    // A request that may have reached the runtime, or one refused while the branch is
    // still being created or the chat is busy, is retried with its ID: the server joins
    // or takes over that branch rather than leaving it pending under a lost ID.
    expect(busy).toBe(failed);
    expect(made).toBe(busy);
    // Once made, or after a refusal that made nothing, the next branch gets a new ID.
    expect(missing).not.toBe(made);
    expect(fresh).not.toBe(missing);
    expect(result.current.store.activeSessionId).toBe("b-new");
  });

  it("retries under the same ID when the branch's reply body is lost after its headers", async () => {
    const result = await openSaved();
    // HTTP 200 arrived, then the connection dropped while the body was read.
    branchReply = async () =>
      new Response(
        new ReadableStream({
          start(controller) {
            controller.error(new TypeError("network error"));
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    await act(async () => {
      expect(await result.current.store.branchFrom("saved", "5")).toBeNull();
    });
    expect(result.current.chat.notice).toMatch(/Could not branch from this answer: .*Try again/);
    expect(result.current.chat.branchingIndex).toBe(-1);
    branchReply = async () => Response.json(BRANCH);
    await act(async () => {
      expect(await result.current.store.branchFrom("saved", "5")).toBe("b-new");
    });
    const [lost, retried] = branchCalls().map((call) => call.body.target_session_id);
    expect(retried).toBe(lost);
  });
});
