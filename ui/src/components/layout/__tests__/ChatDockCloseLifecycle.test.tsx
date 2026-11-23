import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppLayout } from "@/components/layout/AppLayout";
import { useChatDock } from "@/contexts/ChatDockContext";
import { useCopilotChatSessionContext } from "@/contexts/CopilotChatSessionContext";

/*
 * The production composition of the in-app chat: the real AppLayout with its real
 * CopilotChatSessionProvider, ChatDockProvider, ChatNotifier, ChatSidebar, MiniChatWindow,
 * DockedChatPanel, and ChatThread. Only the route, the signed-in user, the navigation chrome,
 * and the network are stubbed. Closing a surface with its X must hide it and nothing else.
 */

const nav = vi.hoisted(() => ({ pathname: "/execution" }));
const toasts = vi.hoisted(() => ({
  calls: [] as Array<{ title: string; id?: string }>,
  /** When set, the toast library throws for this title, as a renderer failure would. */
  failOn: null as string | null,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { username: "alice", system_role: "user" },
    username: "alice",
    logout: vi.fn(),
  }),
}));
vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({
    canEdit: true,
    currentProject: { project_id: "p1", name: "Lab" },
    projectId: "p1",
    projects: [{ project_id: "p1", name: "Lab" }],
    loading: false,
    switchProject: vi.fn(),
  }),
}));
vi.mock("@/client/copilot/copilot", () => ({
  useGetCopilotConfig: () => ({ data: undefined }),
  useGetCopilotPreferences: () => ({ data: undefined }),
  useListCopilotSkills: () => ({ data: undefined }),
}));
vi.mock("@/hooks/useChatSuggestions", () => ({ useChatSuggestions: () => [] }));
vi.mock("sonner", () => {
  const record = (title: string, options?: { id?: string }) => {
    toasts.calls.push({ title, id: options?.id });
    if (toasts.failOn === title) throw new Error("toast renderer failed");
  };
  return {
    toast: Object.assign(record, {
      success: record,
      error: record,
      warning: record,
      info: record,
      dismiss: vi.fn(),
    }),
    Toaster: () => null,
  };
});
// Navigation chrome, unrelated to the chat lifecycle under test.
vi.mock("@/components/layout/Navbar", () => ({ Navbar: () => null }));
vi.mock("@/components/layout/Sidebar", () => ({ Sidebar: () => null }));
vi.mock("@/components/layout/MobileTabBar", () => ({
  MobileTabBar: () => null,
}));
vi.mock("@/components/features/first-calibration/FirstCalibrationBanner", () => ({
  FirstCalibrationBanner: () => null,
}));
vi.mock("@/components/features/first-calibration/FirstCalibrationCoachmarks", () => ({
  FirstCalibrationCoachmarks: () => null,
}));

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
interface Call {
  url: string;
  method: string;
  body: Record<string, unknown>;
}

let streams: Stream[];
let calls: Call[];
let aborts: unknown[];
let saved: Record<string, Array<{ role: string; content: string }>>;

beforeEach(() => {
  nav.pathname = "/execution";
  toasts.calls = [];
  toasts.failOn = null;
  streams = [];
  calls = [];
  aborts = [];
  saved = {};
  localStorage.setItem("qdash_current_project_id", "p1");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      const method = init?.method ?? "GET";
      calls.push({ url, method, body });
      if (url.endsWith("/copilot/chat/stream")) {
        const stream = controllableStream();
        streams.push(stream);
        init?.signal?.addEventListener("abort", () => {
          aborts.push(init.signal!.reason);
          stream.abort(init.signal!.reason);
        });
        return new Response(stream.body, { status: 200 });
      }
      if (url.endsWith("/copilot/chat/sessions") && method === "GET") {
        return Response.json({ sessions: [] });
      }
      if (url.endsWith("/copilot/chat/sessions") && method === "POST") {
        return Response.json({});
      }
      const match = /\/copilot\/chat\/sessions\/([^/]+)$/.exec(url);
      if (match && method === "PATCH") {
        if (body.messages) saved[match[1]] = body.messages;
        return Response.json({});
      }
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
      return Response.json({});
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

let dock: ReturnType<typeof useChatDock>;
let store: ReturnType<typeof useCopilotChatSessionContext>;

/** Reads the real dock and session store from inside the real layout. */
function Probe() {
  dock = useChatDock();
  store = useCopilotChatSessionContext();
  return null;
}

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <AppLayout>
          <Probe />
          <div data-testid="page">Page</div>
        </AppLayout>
      </QueryClientProvider>
    </StrictMode>,
  );
}

const streamCalls = () => calls.filter((c) => c.url.endsWith("/copilot/chat/stream"));
const stopCalls = () => calls.filter((c) => c.url.endsWith("/copilot/chat/stop"));
const freshPosts = () => streamCalls().filter((c) => c.body.reattach !== true);

async function startTurnInSidebar() {
  renderApp();
  await waitFor(() => expect(store.isLoadingSessions).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "Ask Agent" }));
  const panel = await screen.findByRole("complementary", { name: "Agent" });
  const box = within(panel).getByRole("textbox");
  fireEvent.change(box, { target: { value: "Calibrate Q0" } });
  fireEvent.keyDown(box, { key: "Enter" });
  await waitFor(() => expect(streams).toHaveLength(1));
  const sessionId = store.activeSessionId!;
  await act(async () => {
    streams[0].push(sse("delta", { text: "Working on " }));
  });
  await waitFor(() => expect(store.runs[sessionId]?.turn?.steps.length).toBeGreaterThan(0));
  return { sessionId, panel };
}

async function closeSidebarWithX(panel: HTMLElement) {
  fireEvent.click(within(panel).getByRole("button", { name: "Close" }));
  await waitFor(() =>
    expect(screen.queryByRole("complementary", { name: "Agent" })).not.toBeInTheDocument(),
  );
}

const assistantText = (sessionId: string) =>
  JSON.stringify(store.sessions.find((s) => s.id === sessionId)?.messages ?? []);

describe("closing a chat surface with X in the production layout", () => {
  it("sidebar X hides the chat while the turn streams on, and reopening shows it uninterrupted", async () => {
    const { sessionId, panel } = await startTurnInSidebar();

    await closeSidebarWithX(panel);

    // Hidden, not stopped: the stream is untouched and no Stop is sent.
    expect(aborts).toEqual([]);
    expect(stopCalls()).toEqual([]);
    expect(store.activeSessionId).toBe(sessionId);
    expect(sessionId in store.runs).toBe(true);
    expect(
      screen.getByRole("button", { name: "Ask Agent, an answer is running" }),
    ).toBeInTheDocument();

    // The turn keeps streaming while hidden.
    await act(async () => {
      streams[0].push(sse("delta", { text: "the qubit" }));
    });

    // Reopen the same chat while the turn is still running.
    fireEvent.click(screen.getByRole("button", { name: "Ask Agent, an answer is running" }));
    const reopened = await screen.findByRole("complementary", {
      name: "Agent",
    });
    expect(store.activeSessionId).toBe(sessionId);
    await waitFor(() => expect(reopened).toHaveTextContent("Working on the qubit"));

    await act(async () => {
      streams[0].push(
        sse("result", {
          blocks: [{ type: "text", content: "Q0 is calibrated." }],
          entry_id: "7",
        }),
      );
      streams[0].close();
    });
    await waitFor(() => expect(sessionId in store.runs).toBe(false));
    await waitFor(() => expect(reopened).toHaveTextContent("Q0 is calibrated."));
    expect(freshPosts()).toHaveLength(1);
    expect(streamCalls()).toHaveLength(1);
    expect(stopCalls()).toEqual([]);
    expect(assistantText(sessionId)).not.toContain('"stopped":true');
  });

  it("finishes while the sidebar is closed and notifies once; reopening shows the final answer", async () => {
    const { sessionId, panel } = await startTurnInSidebar();
    await closeSidebarWithX(panel);

    // An expert wait while hidden, then the answer.
    await act(async () => {
      streams[0].push(sse("tool_start", { id: "w1", tool: WAIT, label: "Wait" }));
    });
    await act(async () => {
      streams[0].push(
        sse("tool_end", {
          id: "w1",
          tool: WAIT,
          label: "Wait",
          is_error: false,
        }),
      );
      streams[0].push(
        sse("result", {
          blocks: [{ type: "text", content: "Done while hidden." }],
          entry_id: "8",
        }),
      );
      streams[0].close();
    });
    await waitFor(() => expect(sessionId in store.runs).toBe(false));
    expect(aborts).toEqual([]);
    expect(stopCalls()).toEqual([]);
    expect(assistantText(sessionId)).toContain("Done while hidden.");
    expect(assistantText(sessionId)).not.toContain('"stopped":true');
    expect(toasts.calls.filter((t) => t.title === "Answer ready")).toHaveLength(1);
    expect(toasts.calls.filter((t) => t.title === "Waiting for the expert's answer")).toHaveLength(
      1,
    );

    fireEvent.click(screen.getByRole("button", { name: "Ask Agent" }));
    const reopened = await screen.findByRole("complementary", {
      name: "Agent",
    });
    expect(store.activeSessionId).toBe(sessionId);
    await waitFor(() => expect(reopened).toHaveTextContent("Done while hidden."));
    expect(freshPosts()).toHaveLength(1);
    expect(streamCalls()).toHaveLength(1);
  });

  it("mini window X hides the chat; the expert wait resumes and finishes while hidden", async () => {
    renderApp();
    await waitFor(() => expect(store.isLoadingSessions).toBe(false));
    const sessionId = store.createNewSession(null);
    act(() => {
      store.sendMessage("Calibrate Q1", { sessionId });
      dock.openMiniChatForSession(sessionId);
    });
    const mini = await screen.findByRole("dialog", { name: "Agent" });
    await waitFor(() => expect(streams).toHaveLength(1));
    await act(async () => {
      streams[0].push(sse("delta", { text: "Asking the expert" }));
      streams[0].push(sse("tool_start", { id: "w1", tool: WAIT, label: "Wait" }));
    });

    fireEvent.click(within(mini).getByRole("button", { name: "Close chat" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Agent" })).not.toBeInTheDocument(),
    );
    expect(aborts).toEqual([]);
    expect(stopCalls()).toEqual([]);
    expect(sessionId in store.runs).toBe(true);
    expect(store.activeSessionId).toBe(sessionId);

    await act(async () => {
      streams[0].push(
        sse("tool_end", {
          id: "w1",
          tool: WAIT,
          label: "Wait",
          is_error: false,
        }),
      );
      streams[0].push(sse("delta", { text: ", the expert answered." }));
    });
    act(() => dock.openMiniChatForSession(sessionId));
    const reopened = await screen.findByRole("dialog", { name: "Agent" });
    await waitFor(() => expect(reopened).toHaveTextContent(", the expert answered."));
    await act(async () => {
      streams[0].push(
        sse("result", {
          blocks: [{ type: "text", content: "Q1 is calibrated." }],
          entry_id: "9",
        }),
      );
      streams[0].close();
    });
    await waitFor(() => expect(reopened).toHaveTextContent("Q1 is calibrated."));
    expect(streamCalls()).toHaveLength(1);
    expect(stopCalls()).toEqual([]);
  });

  it("a failing notification does not end the hidden turn or replace its answer", async () => {
    const { sessionId, panel } = await startTurnInSidebar();
    await closeSidebarWithX(panel);
    // Notifications are shown only while the chat is hidden: this path runs only after X.
    toasts.failOn = "Waiting for the expert's answer";
    const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);

    await act(async () => {
      streams[0].push(sse("tool_start", { id: "w1", tool: WAIT, label: "Wait" }));
    });
    expect(sessionId in store.runs).toBe(true);
    toasts.failOn = "Answer ready";
    await act(async () => {
      streams[0].push(
        sse("tool_end", {
          id: "w1",
          tool: WAIT,
          label: "Wait",
          is_error: false,
        }),
      );
      streams[0].push(
        sse("result", {
          blocks: [{ type: "text", content: "Still answered." }],
          entry_id: "6",
        }),
      );
      streams[0].close();
    });
    await waitFor(() => expect(sessionId in store.runs).toBe(false));
    expect(assistantText(sessionId)).toContain("Still answered.");
    expect(assistantText(sessionId)).not.toContain("Error: ");
    expect(toasts.calls.map((t) => t.title)).not.toContain("The answer failed");
    expect(errors).toHaveBeenCalled();
    expect(aborts).toEqual([]);
    expect(stopCalls()).toEqual([]);
    expect(streamCalls()).toHaveLength(1);
    errors.mockRestore();
  });

  it("Stop is the only control that cancels the turn", async () => {
    const { sessionId, panel } = await startTurnInSidebar();
    fireEvent.click(within(panel).getByRole("button", { name: /stop/i }));
    await waitFor(() => expect(sessionId in store.runs).toBe(false));
    expect(aborts).toContain("stop");
    expect(stopCalls()).toHaveLength(1);
  });
});
