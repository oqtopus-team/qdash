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
    stream.push(
      sse("steer", {
        request_id: requestId,
        status: "applied",
        entry_id: "4",
        text: "Also plot it",
        result: {
          blocks: [{ type: "text", content: "Plotted.", chart: null }],
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
    stream.push(
      sse("result", {
        blocks: [{ type: "text", content: "Answer.", chart: null }],
        assessment: null,
      }),
    );
    stream.close();
    await waitFor(() => expect(r.result.current.chat.isStreaming).toBe(false));

    const messages = r.result.current.chat.messages;
    const summary = messages.map((m) =>
      m.steer
        ? `steer:${m.content}:${m.steer.placement}`
        : `${m.role}:${m.role === "user" ? m.content : ""}`,
    );
    expect(summary).toEqual([
      "user:Long job",
      "assistant:",
      "steer:Also plot it:approximate",
      "steer:From another tab:approximate",
      "user:New question",
      "assistant:",
      "assistant:",
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
