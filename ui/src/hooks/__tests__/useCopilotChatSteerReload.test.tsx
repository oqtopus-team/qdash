import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CopilotChatSessionProvider,
  useCopilotChatSessionContext,
} from "@/contexts/CopilotChatSessionContext";

import { useCopilotChat } from "../useCopilotChat";

vi.mock("@/client/copilot/copilot", () => ({
  useGetCopilotConfig: () => ({ data: undefined }),
  useGetChatGPTConnection: () => ({ data: undefined, isPending: false, isError: true }),
}));

const STORE_PREFIX = "qdash.copilot.pendingSteers.v1:";

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

type Message = Record<string, unknown>;

/** A fake API: one user's session list and saved messages, steers, and status lookups. */
let stream: ReturnType<typeof controllableStream>;
let fetchMock: ReturnType<typeof vi.fn>;
let listed: Array<{ session_id: string }> = [];
let saved: Record<string, Message[]> = {};
let steerReply: () => Response = () => Response.json({ status: "queued" });
let statusReply: () => Response = () => new Response("unavailable", { status: 503 });
let storedWhenSteerSent: string | null = null;
// How the fake API answers a transcript save; by default it stores it.
let patchReply: ((sessionId: string, body: { messages?: Message[] }) => Promise<Response>) | null =
  null;
// The signed-in user the provider is given; changed between renders.
let owner: string | null | undefined = "alice";

const wrapper = ({ children }: { children: ReactNode }) => (
  <CopilotChatSessionProvider owner={owner}>{children}</CopilotChatSessionProvider>
);

beforeEach(() => {
  stream = controllableStream();
  listed = [];
  saved = {};
  owner = "alice";
  storedWhenSteerSent = null;
  patchReply = null;
  steerReply = () => Response.json({ status: "queued" });
  statusReply = () => new Response("unavailable", { status: 503 });
  localStorage.setItem("qdash_current_project_id", "p1");
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url);
    if (path.endsWith("/stream")) {
      init?.signal?.addEventListener("abort", () => stream.abort(init.signal!.reason));
      return new Response(stream.body, { status: 200 });
    }
    if (path.endsWith("/copilot/chat/steer")) {
      storedWhenSteerSent = sessionStorage.getItem(STORE_PREFIX + "alice");
      return steerReply();
    }
    if (path.endsWith("/copilot/chat/steer/status")) return statusReply();
    if (path.endsWith("/copilot/chat/sessions") && !init?.method) {
      return Response.json({
        sessions: listed.map((s) => ({
          ...s,
          title: "Long job",
          context: null,
          message_count: (saved[s.session_id] ?? []).length,
          created_at: "2026-11-16T00:00:00Z",
          updated_at: "2026-11-16T00:01:00Z",
        })),
      });
    }
    const match = /\/copilot\/chat\/sessions\/([^/]+)$/.exec(path);
    if (match && init?.method === "PATCH") {
      const body = JSON.parse(String(init.body)) as { messages?: Message[] };
      if (patchReply) return patchReply(match[1], body);
      if (body.messages) saved[match[1]] = body.messages;
      return Response.json({});
    }
    if (match && !init?.method) {
      return Response.json({
        session_id: match[1],
        title: "Long job",
        messages: saved[match[1]] ?? [],
      });
    }
    return Response.json({ session_id: "x", title: "", messages: [] });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

function useChatAndStore() {
  return { chat: useCopilotChat(), store: useCopilotChatSessionContext() };
}

async function mount() {
  const rendered = renderHook(useChatAndStore, { wrapper });
  await waitFor(() => expect(rendered.result.current.store.isLoadingSessions).toBe(false));
  return rendered;
}

type Rendered = Awaited<ReturnType<typeof mount>>;

const calls = (suffix: string) =>
  fetchMock.mock.calls
    .filter(([url]) => String(url).endsWith(suffix))
    .map(([, init]) => ({
      body: JSON.parse(String(init.body)) as Record<string, unknown>,
      headers: init.headers as Record<string, string>,
    }));
const steerCalls = () => calls("/copilot/chat/steer");
const statusCalls = () => calls("/copilot/chat/steer/status");
const streamCalls = () => fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/stream"));

function stored(who = "alice") {
  const raw = sessionStorage.getItem(STORE_PREFIX + who);
  return raw ? (JSON.parse(raw) as Record<string, Array<Record<string, unknown>>>) : null;
}

/** A turn that streamed, got a steer the runtime admitted, and was stopped before saying where it landed. */
async function stoppedWithUnconfirmedSteer(r: Rendered) {
  act(() => r.result.current.chat.send("Long job"));
  await waitFor(() => expect(r.result.current.chat.isStreaming).toBe(true));
  act(() => {
    r.result.current.chat.steer("Also plot it");
  });
  await waitFor(() => expect(r.result.current.chat.steers[0]?.status).toBe("queued"));
  stream.push(sse("delta", { text: "Working" }));
  await waitFor(() => expect(r.result.current.chat.liveTurn?.steps.length).toBeGreaterThan(0));
  act(() => r.result.current.chat.stop());
  await waitFor(() => expect(r.result.current.chat.isStreaming).toBe(false));
  // The store cannot be read (5xx): the chat does not know whether the answer read it.
  await waitFor(() => expect(statusCalls().length).toBeGreaterThan(0));
  await waitFor(() =>
    expect(r.result.current.chat.steers[0]).toMatchObject({
      status: "unconfirmed",
      checking: false,
    }),
  );
  const sessionId = r.result.current.chat.session!.id;
  const requestId = steerCalls()[0].body.request_id as string;
  listed = [{ session_id: sessionId }];
  return { sessionId, requestId };
}

/** Reload: the old provider goes away (its stream with it) and a new one mounts. */
async function reload(r: Rendered, sessionId: string) {
  r.unmount();
  stream = controllableStream();
  const next = await mount();
  act(() => next.result.current.store.switchSession(sessionId));
  return next;
}

describe("unresolved steers across a reload", () => {
  it("are stored before the request is sent, with no credential", async () => {
    const r = await mount();
    const { sessionId, requestId } = await stoppedWithUnconfirmedSteer(r);
    // Written before the network send, with the project the steer was sent from.
    expect(storedWhenSteerSent).not.toBeNull();
    const atSend = JSON.parse(storedWhenSteerSent!) as Record<
      string,
      Array<Record<string, unknown>>
    >;
    expect(atSend[sessionId]).toEqual([
      expect.objectContaining({
        requestId,
        text: "Also plot it",
        status: "sending",
        projectId: "p1",
        anchor: { start: 0, userText: "Long job" },
      }),
    ]);
    expect(stored()![sessionId][0]).toMatchObject({
      requestId,
      status: "unconfirmed",
    });
    expect(JSON.stringify(stored())).not.toMatch(/token|Bearer/i);
    // Session storage only: nothing of it in local storage.
    expect(Object.keys(localStorage).some((k) => k.startsWith(STORE_PREFIX))).toBe(false);
  });

  it("keeps Continue locked through a reload while the store cannot say, then places it once when it can", async () => {
    let r = await mount();
    const { sessionId, requestId } = await stoppedWithUnconfirmedSteer(r);
    expect(r.result.current.chat.canContinue).toBe(false);
    const statusBefore = statusCalls().length;

    // The user switches project before the reload: the lookup still names the steer's own.
    localStorage.setItem("qdash_current_project_id", "p2");
    r = await reload(r, sessionId);
    await waitFor(() => expect(r.result.current.chat.messages).toHaveLength(2));
    // The chip is back, Continue stays locked, and only the status is asked: never sent again.
    expect(r.result.current.chat.steers).toMatchObject([
      { requestId, text: "Also plot it", status: "unconfirmed" },
    ]);
    expect(r.result.current.chat.canContinue).toBe(false);
    await waitFor(() => expect(statusCalls().length).toBeGreaterThan(statusBefore));
    const lookups = statusCalls();
    const lookup = lookups[lookups.length - 1];
    expect(lookup.body).toEqual({
      session_id: sessionId,
      request_id: requestId,
    });
    expect(lookup.headers["X-Project-Id"]).toBe("p1");
    await waitFor(() =>
      expect(r.result.current.chat.steers[0]).toMatchObject({
        status: "unconfirmed",
        checking: false,
      }),
    );
    expect(r.result.current.chat.canContinue).toBe(false);
    expect(steerCalls()).toHaveLength(1);
    expect(streamCalls()).toHaveLength(1);

    // Mount again while the store still cannot say: still one chip, still locked.
    r = await reload(r, sessionId);
    await waitFor(() => expect(r.result.current.chat.messages).toHaveLength(2));
    expect(r.result.current.chat.steers).toHaveLength(1);
    expect(r.result.current.chat.canContinue).toBe(false);

    // The store now says the answer read it: placed once, approximately, and saved.
    statusReply = () => Response.json({ status: "applied", entry_id: "4", submission_id: "3" });
    act(() => r.result.current.chat.checkSteer(requestId));
    await waitFor(() => expect(r.result.current.chat.steers).toEqual([]));
    const messages = r.result.current.chat.messages;
    expect(messages.filter((m) => m.steer?.requestId === requestId)).toHaveLength(1);
    expect(messages[2]).toMatchObject({
      role: "user",
      content: "Also plot it",
      steer: { requestId, entryId: "4", placement: "approximate" },
    });
    expect(stored()).toBeNull();

    // Reloaded once more: the saved conversation holds it, and nothing is restored twice.
    r = await reload(r, sessionId);
    await waitFor(() => expect(r.result.current.chat.messages).toHaveLength(3));
    expect(r.result.current.chat.steers).toEqual([]);
    expect(
      r.result.current.chat.messages.filter((m) => m.steer?.requestId === requestId),
    ).toHaveLength(1);
    expect(steerCalls()).toHaveLength(1);
    expect(streamCalls()).toHaveLength(1);

    // The stopped answer, then the steer it read: Continue answers both, the steer kept.
    expect(r.result.current.chat.canContinue).toBe(true);
    act(() => r.result.current.chat.continueLast());
    await waitFor(() => expect(streamCalls()).toHaveLength(2));
    const continued = calls("/stream")[1].body as {
      continue_run?: boolean;
      conversation_history: Array<{ role: string; content: string }>;
    };
    expect(continued.continue_run).toBe(true);
    expect(continued.conversation_history.map((m) => m.role)).toEqual([
      "user",
      "assistant",
      "user",
    ]);
    expect(continued.conversation_history[2].content).toBe("Also plot it");
    stream.push(
      sse("result", {
        blocks: [{ type: "text", content: "Plotted.", chart: null }],
        assessment: null,
      }),
    );
    stream.close();
    await waitFor(() => expect(r.result.current.chat.isStreaming).toBe(false));
    expect(r.result.current.chat.messages.map((m) => m.steer?.placement ?? m.role)).toEqual([
      "user",
      "assistant",
      "approximate",
      "assistant",
    ]);
  });

  it("unlocks Continue after a reload once the store says the steer was withdrawn", async () => {
    let r = await mount();
    const { sessionId, requestId } = await stoppedWithUnconfirmedSteer(r);
    statusReply = () =>
      Response.json({
        status: "withdrawn",
        submission_id: "3",
        reason: "aborted",
      });
    r = await reload(r, sessionId);
    await waitFor(() =>
      expect(r.result.current.chat.steers).toMatchObject([{ requestId, status: "withdrawn" }]),
    );
    expect(r.result.current.chat.canContinue).toBe(true);
    expect(stored()).toBeNull();
    expect(steerCalls()).toHaveLength(1);
  });

  it("drops a stored steer already in the saved conversation without asking", async () => {
    let r = await mount();
    const { sessionId, requestId } = await stoppedWithUnconfirmedSteer(r);
    saved[sessionId] = [
      ...saved[sessionId],
      {
        role: "user",
        content: "Also plot it",
        steer: {
          request_id: requestId,
          entry_id: "4",
          placement: "approximate",
        },
      },
    ];
    const asked = statusCalls().length;
    r = await reload(r, sessionId);
    await waitFor(() => expect(r.result.current.chat.messages).toHaveLength(3));
    await waitFor(() => expect(r.result.current.chat.steers).toEqual([]));
    expect(statusCalls()).toHaveLength(asked);
    expect(stored()).toBeNull();
  });

  it("does not offer Continue before the user and their steers are known", async () => {
    let r = await mount();
    const { sessionId } = await stoppedWithUnconfirmedSteer(r);
    statusReply = () =>
      Response.json({
        status: "withdrawn",
        submission_id: "3",
        reason: "aborted",
      });
    // Signed in, but the user is not known yet: nothing restored, nothing offered.
    r.unmount();
    owner = null;
    r = await mount();
    act(() => r.result.current.store.switchSession(sessionId));
    await waitFor(() => expect(r.result.current.chat.messages).toHaveLength(2));
    expect(r.result.current.store.steersReady).toBe(false);
    expect(r.result.current.chat.steers).toEqual([]);
    expect(r.result.current.chat.canContinue).toBe(false);
    owner = "alice";
    r.rerender();
    await waitFor(() =>
      expect(r.result.current.chat.steers).toMatchObject([{ status: "withdrawn" }]),
    );
    expect(r.result.current.chat.canContinue).toBe(true);
  });

  it("never restores one user's steers for another, and forgets them on sign-out", async () => {
    let r = await mount();
    const { sessionId } = await stoppedWithUnconfirmedSteer(r);
    expect(stored("alice")).not.toBeNull();
    r.unmount();
    // Another user in the same tab, even with the same session ID listed.
    owner = "bob";
    r = await mount();
    act(() => r.result.current.store.switchSession(sessionId));
    await waitFor(() => expect(r.result.current.store.steersReady).toBe(true));
    expect(r.result.current.chat.steers).toEqual([]);
    expect(stored("alice")).toBeNull();
    expect(JSON.stringify(Object.values(sessionStorage))).not.toContain("Also plot it");
    r.unmount();

    // Alice again, signing out while mounted: shown and stored steers go.
    owner = "alice";
    r = await mount();
    const second = await stoppedWithUnconfirmedSteerAgain(r);
    expect(stored("alice")![second]).toHaveLength(1);
    owner = null;
    r.rerender();
    await waitFor(() => expect(r.result.current.chat.steers).toEqual([]));
    expect(stored("alice")).toBeNull();
  });

  it("forgets a stored steer of a session the user's list no longer holds, and of a deleted session", async () => {
    let r = await mount();
    const { sessionId } = await stoppedWithUnconfirmedSteer(r);
    listed = [];
    r.unmount();
    r = await mount();
    await waitFor(() => expect(r.result.current.store.steersReady).toBe(true));
    expect(r.result.current.store.steers).toEqual({});
    expect(stored()).toBeNull();
    r.unmount();

    r = await mount();
    const other = await stoppedWithUnconfirmedSteerAgain(r);
    expect(stored()![other]).toHaveLength(1);
    act(() => r.result.current.store.deleteSession(other));
    expect(stored()).toBeNull();
    expect(r.result.current.store.steers).toEqual({});
    void sessionId;
  });

  it("still sends a steer when the tab's storage refuses it", async () => {
    const setItem = Storage.prototype.setItem;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      key: string,
      value: string,
    ) {
      if (key.startsWith(STORE_PREFIX)) throw new DOMException("full", "QuotaExceededError");
      setItem.call(this, key, value);
    });
    const r = await mount();
    act(() => r.result.current.chat.send("Long job"));
    await waitFor(() => expect(r.result.current.chat.isStreaming).toBe(true));
    act(() => {
      expect(r.result.current.chat.steer("Also plot it")).toBe(true);
    });
    await waitFor(() => expect(r.result.current.chat.steers[0]?.status).toBe("queued"));
    expect(steerCalls()).toHaveLength(1);
  });
});

describe("saving the conversation a steer was placed in", () => {
  it("keeps the steer's receipt when the save fails, so a reload places it again", async () => {
    let r = await mount();
    const { sessionId, requestId } = await stoppedWithUnconfirmedSteer(r);
    const before = saved[sessionId];
    // Every save fails from here on.
    patchReply = async () => new Response("unavailable", { status: 503 });
    statusReply = () => Response.json({ status: "applied", entry_id: "4", submission_id: "3" });
    act(() => r.result.current.chat.checkSteer(requestId));
    await waitFor(() =>
      expect(r.result.current.chat.messages.some((m) => m.steer?.requestId === requestId)).toBe(
        true,
      ),
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(
          ([url, init]) =>
            String(url).endsWith(`/sessions/${sessionId}`) && init?.method === "PATCH",
        ).length,
      ).toBeGreaterThan(0),
    );
    // Shown in place, not listed as pending, and Continue is not held back by it.
    expect(r.result.current.chat.steers).toMatchObject([{ requestId, saving: true }]);
    expect(r.result.current.chat.canContinue).toBe(true);
    // The save failed: the server does not have it, and the receipt is kept for a reload.
    expect(saved[sessionId]).toEqual(before);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(stored()![sessionId]).toEqual([
      expect.objectContaining({ requestId, status: "delivered", entryId: "4" }),
    ]);

    // Reloaded with saves working again: placed from the receipt, once, and saved.
    patchReply = null;
    r = await reload(r, sessionId);
    await waitFor(() => expect(r.result.current.chat.steers).toEqual([]));
    expect(
      r.result.current.chat.messages.filter((m) => m.steer?.requestId === requestId),
    ).toHaveLength(1);
    expect(
      saved[sessionId].filter(
        (m) => (m.steer as { request_id?: string } | undefined)?.request_id === requestId,
      ),
    ).toHaveLength(1);
    expect(stored()).toBeNull();
    expect(steerCalls()).toHaveLength(1);
  });

  it("sends one save at a time per session, the newest snapshot last", async () => {
    listed = [{ session_id: "s1" }];
    saved.s1 = [
      { role: "user", content: "Q" },
      {
        role: "assistant",
        content: JSON.stringify({
          blocks: [{ type: "text", content: "A", chart: null }],
        }),
      },
    ];
    const held: Array<{ body: { messages?: Message[] }; release: () => void }> = [];
    patchReply = (sessionId, body) =>
      new Promise<Response>((resolve) => {
        held.push({
          body,
          release: () => {
            if (body.messages) saved[sessionId] = body.messages;
            resolve(Response.json({}));
          },
        });
      });
    const r = await mount();
    act(() => r.result.current.store.switchSession("s1"));
    await waitFor(() => expect(r.result.current.chat.messages).toHaveLength(2));
    const feedbackOf = (body: { messages?: Message[] }) =>
      (JSON.parse(String(body.messages![1].content)) as { feedback?: string }).feedback;

    act(() => r.result.current.store.setMessageFeedback("s1", 1, "up"));
    act(() => r.result.current.store.setMessageFeedback("s1", 1, "down"));
    act(() => r.result.current.store.setMessageFeedback("s1", 1, "up"));
    await waitFor(() => expect(held).toHaveLength(1));
    // The later snapshots wait for the first save; the middle one is never sent.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(held).toHaveLength(1);
    expect(feedbackOf(held[0].body)).toBe("up");
    await act(async () => held[0].release());
    await waitFor(() => expect(held).toHaveLength(2));
    expect(feedbackOf(held[1].body)).toBe("up");
    // The newest snapshot commits last, whatever order the server would finish them in.
    act(() => r.result.current.store.setMessageFeedback("s1", 1, "down"));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(held).toHaveLength(2);
    await act(async () => held[1].release());
    await waitFor(() => expect(held).toHaveLength(3));
    await act(async () => held[2].release());
    expect(feedbackOf({ messages: saved.s1 })).toBe("down");
  });

  it("never sends a session's waiting save under another user's sign-in", async () => {
    listed = [{ session_id: "s1" }];
    saved.s1 = [
      { role: "user", content: "Q" },
      {
        role: "assistant",
        content: JSON.stringify({
          blocks: [{ type: "text", content: "A", chart: null }],
        }),
      },
    ];
    let releaseFirst!: () => void;
    let patches = 0;
    patchReply = () => {
      patches += 1;
      return new Promise<Response>((resolve) => (releaseFirst = () => resolve(Response.json({}))));
    };
    const r = await mount();
    act(() => r.result.current.store.switchSession("s1"));
    await waitFor(() => expect(r.result.current.chat.messages).toHaveLength(2));
    act(() => r.result.current.store.setMessageFeedback("s1", 1, "up"));
    act(() => r.result.current.store.setMessageFeedback("s1", 1, "down"));
    await waitFor(() => expect(patches).toBe(1));
    // Alice signs out while her second save waits.
    owner = null;
    r.rerender();
    await act(async () => releaseFirst());
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(patches).toBe(1);
  });
});

/** Like stoppedWithUnconfirmedSteer, in a new session of an already mounted provider. */
async function stoppedWithUnconfirmedSteerAgain(r: Rendered) {
  stream = controllableStream();
  act(() => {
    r.result.current.store.createNewSession(null);
  });
  await waitFor(() => expect(r.result.current.chat.session).not.toBeNull());
  const before = steerCalls().length;
  act(() => r.result.current.chat.send("Second job"));
  await waitFor(() => expect(r.result.current.chat.isStreaming).toBe(true));
  act(() => {
    r.result.current.chat.steer("Again");
  });
  await waitFor(() => expect(steerCalls()).toHaveLength(before + 1));
  await waitFor(() => expect(r.result.current.chat.steers[0]?.status).toBe("queued"));
  act(() => r.result.current.chat.stop());
  await waitFor(() => expect(r.result.current.chat.isStreaming).toBe(false));
  await waitFor(() =>
    expect(r.result.current.chat.steers[0]).toMatchObject({
      status: "unconfirmed",
      checking: false,
    }),
  );
  return r.result.current.chat.session!.id;
}

describe("the start of a turn's own message", () => {
  it("adds nothing on a normal second turn: the answer before it is already shown", async () => {
    const r = await mount();
    const turn = async (text: string, answer: string) => {
      stream = controllableStream();
      act(() => r.result.current.chat.send(text));
      await waitFor(() => expect(r.result.current.chat.isStreaming).toBe(true));
      // The runtime reports only an answer given since the turn's stream started: none.
      stream.push(sse("turn_start", { result: { blocks: [], assessment: null } }));
      stream.push(sse("delta", { text: answer }));
      stream.push(
        sse("result", {
          blocks: [{ type: "text", content: answer, chart: null }],
          assessment: null,
        }),
      );
      stream.close();
      await waitFor(() => expect(r.result.current.chat.isStreaming).toBe(false));
    };
    await turn("First", "A1");
    await turn("Second", "A2");
    const summary = r.result.current.chat.messages.map((m) =>
      m.role === "user"
        ? `user:${m.content}`
        : `assistant:${(JSON.parse(m.content) as { blocks: Array<{ content?: string }> }).blocks
            .map((b) => b.content ?? "")
            .join("")}`,
    );
    expect(summary).toEqual(["user:First", "assistant:A1", "user:Second", "assistant:A2"]);
  });
});

describe("a steer a recovered run placed before the new message", () => {
  it("goes into the turn it was sent to, approximately, never after the new message as exact", async () => {
    let r = await mount();
    const { sessionId, requestId } = await stoppedWithUnconfirmedSteer(r);
    // The runtime died with the steer queued; the store keeps saying queued.
    statusReply = () => Response.json({ status: "queued", submission_id: "3" });
    r = await reload(r, sessionId);
    await waitFor(() => expect(r.result.current.chat.messages).toHaveLength(2));
    await waitFor(() =>
      expect(r.result.current.chat.steers[0]).toMatchObject({
        status: "unconfirmed",
      }),
    );
    expect(r.result.current.chat.canContinue).toBe(false);

    // The user sends a new message. Opening the conversation recovers the run,
    // which places the steer before the new message, and reports it so.
    act(() => r.result.current.chat.send("New question"));
    await waitFor(() => expect(r.result.current.chat.isStreaming).toBe(true));
    // What the recovered run streamed before placing the steer: its tool round's text.
    stream.push(
      sse("steer", {
        request_id: requestId,
        status: "applied",
        entry_id: "4",
        text: "Also plot it",
        result: {
          blocks: [{ type: "text", content: "Calibrated.", chart: null }],
          assessment: null,
        },
        before_turn: true,
      }),
    );
    // Another steer the chat never knew of (sent from elsewhere), also before the turn.
    stream.push(
      sse("steer", {
        request_id: "unknown-1",
        status: "applied",
        entry_id: "6",
        text: "From another tab",
        result: { blocks: [], assessment: null },
        before_turn: true,
      }),
    );
    // The recovered run answers the steers, then this turn's own message is placed.
    stream.push(sse("delta", { text: "Plotted." }));
    stream.push(
      sse("turn_start", {
        result: {
          blocks: [{ type: "text", content: "Plotted.", chart: null }],
          assessment: null,
        },
      }),
    );
    stream.push(sse("delta", { text: "Answer." }));
    stream.push(
      sse("result", {
        blocks: [{ type: "text", content: "Answer.", chart: null }],
        assessment: null,
      }),
    );
    stream.close();
    await waitFor(() => expect(r.result.current.chat.isStreaming).toBe(false));

    const messages = r.result.current.chat.messages;
    const textOf = (content: string) =>
      (JSON.parse(content) as { blocks: Array<{ content?: string | null }> }).blocks
        .map((b) => b.content ?? "")
        .join("");
    const summary = messages.map((m) =>
      m.steer
        ? `steer:${m.content}:${m.steer.placement}`
        : m.role === "user"
          ? `user:${m.content}`
          : m.content.startsWith("{")
            ? `assistant:${textOf(m.content)}`
            : "assistant:?",
    );
    // The recovered answer stays with the turn whose steer it answered, before
    // the new question; the new question's own answer follows it.
    expect(summary).toEqual([
      "user:Long job",
      "assistant:Working",
      "assistant:Calibrated.",
      "steer:Also plot it:approximate",
      "steer:From another tab:approximate",
      "assistant:Plotted.",
      "user:New question",
      "assistant:Answer.",
    ]);
    expect(messages.filter((m) => m.steer?.requestId === requestId)).toHaveLength(1);
    expect(r.result.current.chat.steers).toEqual([]);
    expect(stored()).toBeNull();
    expect(steerCalls()).toHaveLength(1);
  });

  it("keeps a steer of the turn itself exact, after its message", async () => {
    const r = await mount();
    act(() => r.result.current.chat.send("Long job"));
    await waitFor(() => expect(r.result.current.chat.isStreaming).toBe(true));
    act(() => {
      r.result.current.chat.steer("Also plot it");
    });
    await waitFor(() => expect(r.result.current.chat.steers[0]?.status).toBe("queued"));
    const requestId = steerCalls()[0].body.request_id as string;
    stream.push(
      sse("steer", {
        request_id: requestId,
        status: "applied",
        entry_id: "3",
        text: "Also plot it",
        result: { blocks: [], assessment: null },
      }),
    );
    stream.push(
      sse("result", {
        blocks: [{ type: "text", content: "Done.", chart: null }],
        assessment: null,
      }),
    );
    stream.close();
    await waitFor(() => expect(r.result.current.chat.isStreaming).toBe(false));
    const messages = r.result.current.chat.messages;
    expect(messages.map((m) => m.steer?.placement ?? m.role)).toEqual([
      "user",
      "exact",
      "assistant",
    ]);
    expect(stored()).toBeNull();
  });
});
