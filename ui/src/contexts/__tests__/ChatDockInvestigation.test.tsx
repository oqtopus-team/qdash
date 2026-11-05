import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatDockProvider, useChatDock } from "../ChatDockContext";
import {
  CopilotChatSessionProvider,
  useCopilotChatSessionContext,
} from "../CopilotChatSessionContext";
import type { InvestigationTarget } from "@/types/copilotChat";

vi.mock("next/navigation", () => ({ usePathname: () => "/execution" }));

const wrapper = ({ children }: { children: ReactNode }) => (
  <CopilotChatSessionProvider>
    <ChatDockProvider>{children}</ChatDockProvider>
  </CopilotChatSessionProvider>
);

const EXECUTION_ONLY: InvestigationTarget = {
  executionId: "exec-1",
  chipId: "64Q",
};
const TASK: InvestigationTarget = {
  executionId: "exec-1",
  taskId: "task-9",
  taskName: "CheckRabi",
  qid: "3",
  chipId: "64Q",
};

let storedSessions: unknown[];
let storedMessages: Record<string, unknown[]>;
let fetchMock: ReturnType<typeof vi.fn>;

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

beforeEach(() => {
  storedSessions = [];
  storedMessages = {};
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/stream")) {
      return new Response(sse("result", { blocks: [], assessment: null }), {
        status: 200,
      });
    }
    if (url.endsWith("/copilot/chat/sessions") && !init?.method) {
      return Response.json({ sessions: storedSessions });
    }
    const id = decodeURIComponent(String(url).split("/").pop() ?? "");
    return Response.json({
      session_id: id,
      title: "",
      context: null,
      messages: storedMessages[id] ?? [],
    });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function useDockAndStore() {
  return { dock: useChatDock(), store: useCopilotChatSessionContext() };
}

async function renderDock() {
  const rendered = renderHook(useDockAndStore, { wrapper });
  await waitFor(() => expect(rendered.result.current.store.isLoadingSessions).toBe(false));
  return rendered;
}

function calls(suffix: string, method?: string) {
  return fetchMock.mock.calls.filter(
    ([url, init]) => String(url).endsWith(suffix) && (init?.method ?? "GET") === (method ?? "GET"),
  );
}

const ANSWER = {
  role: "assistant",
  content: '{"blocks":[],"assessment":null}',
};

/** What the dock's New chat button does: leave the active chat for a blank one. */
function newChatFromDock(rendered: Awaited<ReturnType<typeof renderDock>>) {
  const { dock, store } = rendered.result.current;
  act(() => {
    dock.endInvestigation(store.activeSessionId);
    store.createNewSession(store.activeSession?.context ?? null);
  });
}

function streamBodies() {
  return calls("/stream", "POST").map(([, init]) => JSON.parse(String(init.body)));
}

describe("ChatDock investigations", () => {
  it("sends an execution-only investigation once, without a task", async () => {
    const { result, rerender } = await renderDock();

    act(() => result.current.dock.investigate(EXECUTION_ONLY));
    await waitFor(() => expect(streamBodies()).toHaveLength(1));
    rerender();

    const [body] = streamBodies();
    expect(body.investigation).toEqual({
      execution_id: "exec-1",
      chip_id: "64Q",
    });
    expect(body.task).toBeUndefined();
    expect(body.message).toMatch(/why execution exec-1 failed/);
    expect(body.page).toEqual({
      path: "/execution",
      title: expect.any(String),
    });

    const [, createInit] = calls("/copilot/chat/sessions", "POST")[0];
    const created = JSON.parse(String(createInit.body));
    expect(created.title).toBe("Investigate execution exec-1");
    expect(created.context).toEqual({ investigation: EXECUTION_ONLY });

    const session = result.current.store.activeSession;
    expect(session?.context).toBeNull();
    expect(session?.investigation).toEqual(EXECUTION_ONLY);
    expect(result.current.dock.isOpen).toBe(true);
    await waitFor(() => expect(result.current.store.runs).toEqual({}));
    expect(streamBodies()).toHaveLength(1);
  });

  it("resumes the same chat on a repeated click instead of sending again", async () => {
    const { result } = await renderDock();

    act(() => {
      result.current.dock.investigate(TASK, "mini");
      result.current.dock.investigate(TASK, "mini");
    });
    await waitFor(() => expect(streamBodies()).toHaveLength(1));
    const first = result.current.store.activeSessionId;
    act(() => result.current.dock.investigate(TASK, "mini"));

    expect(calls("/copilot/chat/sessions", "POST")).toHaveLength(1);
    expect(result.current.store.activeSessionId).toBe(first);
    expect(result.current.dock.miniChat.isOpen).toBe(true);
    expect(result.current.dock.isOpen).toBe(false);
    expect(streamBodies()[0].investigation).toEqual({
      execution_id: "exec-1",
      task_id: "task-9",
      task_name: "CheckRabi",
      qid: "3",
      chip_id: "64Q",
    });

    // A different task of the same execution is a different investigation.
    act(() => result.current.dock.investigate(EXECUTION_ONLY));
    await waitFor(() => expect(streamBodies()).toHaveLength(2));
    expect(result.current.store.activeSessionId).not.toBe(first);
  });

  it("omits investigation on follow-ups and retains it when retrying the first turn", async () => {
    const { result } = await renderDock();
    act(() => result.current.dock.investigate(TASK));
    await waitFor(() => expect(result.current.store.activeSession?.messages).toHaveLength(2));
    const sessionId = result.current.store.activeSessionId!;

    act(() => {
      result.current.store.sendMessage("Which line raised it?", { sessionId });
    });
    await waitFor(() => expect(streamBodies()).toHaveLength(2));
    const followUp = streamBodies()[1];
    expect(followUp.session_id).toBe(sessionId);
    expect(followUp.investigation).toBeUndefined();
    expect(followUp.conversation_history).toHaveLength(2);
    await waitFor(() => expect(result.current.store.runs).toEqual({}));
    act(() => {
      result.current.store.sendMessage("Retry the investigation", { sessionId, history: [] });
    });
    await waitFor(() => expect(streamBodies()).toHaveLength(3));
    expect(streamBodies()[2].investigation.task_id).toBe("task-9");
    expect(streamBodies()[2].conversation_history).toEqual([]);
  });

  it("keeps ordinary chats free of investigation context", async () => {
    const { result } = await renderDock();
    act(() => result.current.dock.investigate(EXECUTION_ONLY));
    await waitFor(() => expect(streamBodies()).toHaveLength(1));
    const investigationId = result.current.store.activeSessionId;

    act(() => result.current.dock.openGeneralChat());
    const generalId = result.current.store.activeSessionId!;
    expect(generalId).not.toBe(investigationId);
    act(() => {
      result.current.store.sendMessage("hello", { sessionId: generalId });
    });
    await waitFor(() => expect(streamBodies()).toHaveLength(2));
    expect(streamBodies()[1].investigation).toBeUndefined();
    expect(streamBodies()[1].task).toBeUndefined();
  });

  it("resumes an investigation stored before a reload", async () => {
    storedSessions = [
      {
        session_id: "saved",
        title: "Investigate execution exec-1",
        context: { investigation: EXECUTION_ONLY },
        message_count: 2,
        created_at: "2026-11-04T00:00:00Z",
        updated_at: "2026-11-04T00:01:00Z",
      },
    ];
    storedMessages = {
      saved: [{ role: "user", content: "Investigate" }, ANSWER],
    };
    const { result } = await renderDock();
    expect(result.current.store.sessions[0].context).toBeNull();

    act(() => result.current.dock.investigate(EXECUTION_ONLY));
    expect(result.current.store.activeSessionId).toBe("saved");
    await waitFor(() => expect(result.current.store.activeSession?.messages).toHaveLength(2));
    expect(streamBodies()).toHaveLength(0);
    expect(calls("/copilot/chat/sessions", "POST")).toHaveLength(0);
  });

  it("starts a fresh investigation after New chat, keeping the old one", async () => {
    const rendered = await renderDock();
    const { result } = rendered;
    act(() => result.current.dock.investigate(TASK));
    await waitFor(() => expect(result.current.store.activeSession?.messages).toHaveLength(2));
    const first = result.current.store.activeSessionId!;

    newChatFromDock(rendered);
    act(() => result.current.dock.investigate(TASK));
    await waitFor(() => expect(streamBodies()).toHaveLength(2));

    const second = result.current.store.activeSessionId!;
    expect(second).not.toBe(first);
    expect(streamBodies()[1].session_id).toBe(second);
    expect(streamBodies()[1].conversation_history).toEqual([]);
    expect(streamBodies()[1].investigation.task_id).toBe("task-9");
    expect(result.current.store.sessions.some((s) => s.id === first)).toBe(true);
    await waitFor(() => expect(result.current.store.activeSession?.messages).toHaveLength(2));

    // The fresh run is now the one a click resumes, double click included.
    act(() => {
      result.current.dock.investigate(TASK);
      result.current.dock.investigate(TASK);
    });
    expect(result.current.store.activeSessionId).toBe(second);
    expect(streamBodies()).toHaveLength(2);
  });

  it("dedups a double click right after New chat", async () => {
    const rendered = await renderDock();
    const { result } = rendered;
    act(() => result.current.dock.investigate(TASK));
    await waitFor(() => expect(streamBodies()).toHaveLength(1));

    newChatFromDock(rendered);
    act(() => {
      result.current.dock.investigate(TASK);
      result.current.dock.investigate(TASK);
    });
    await waitFor(() => expect(streamBodies()).toHaveLength(2));
    expect(
      calls("/copilot/chat/sessions", "POST").filter(([, init]) =>
        String(init.body).includes("investigation"),
      ),
    ).toHaveLength(2);
  });

  it("starts fresh after the chat page's New chat", async () => {
    const { result } = await renderDock();
    act(() => result.current.dock.investigate(EXECUTION_ONLY));
    await waitFor(() => expect(streamBodies()).toHaveLength(1));
    const first = result.current.store.activeSessionId;

    act(() => {
      result.current.dock.endInvestigation(result.current.store.activeSessionId);
      result.current.store.switchSession(null);
    });
    act(() => result.current.dock.investigate(EXECUTION_ONLY));
    await waitFor(() => expect(streamBodies()).toHaveLength(2));
    expect(result.current.store.activeSessionId).not.toBe(first);
  });

  it("resumes after closing or leaving for another chat without New chat", async () => {
    const rendered = await renderDock();
    const { result } = rendered;
    act(() => result.current.dock.investigate(TASK));
    await waitFor(() => expect(streamBodies()).toHaveLength(1));
    const first = result.current.store.activeSessionId;

    act(() => result.current.dock.closeSidebar());
    act(() => result.current.dock.investigate(TASK));
    expect(result.current.store.activeSessionId).toBe(first);

    // New chat from an ordinary chat does not end the investigation.
    act(() => result.current.dock.openGeneralChat());
    newChatFromDock(rendered);
    act(() => result.current.dock.investigate(TASK));
    expect(result.current.store.activeSessionId).toBe(first);
    expect(streamBodies()).toHaveLength(1);
  });

  it("keeps an ended investigation that the user reopened", async () => {
    const rendered = await renderDock();
    const { result } = rendered;
    act(() => result.current.dock.investigate(TASK));
    await waitFor(() => expect(streamBodies()).toHaveLength(1));
    const first = result.current.store.activeSessionId!;

    newChatFromDock(rendered);
    act(() => result.current.store.switchSession(first));
    act(() => result.current.dock.investigate(TASK));
    expect(result.current.store.activeSessionId).toBe(first);
    expect(streamBodies()).toHaveLength(1);
  });

  it("starts fresh once the investigation chat is deleted", async () => {
    const { result } = await renderDock();
    act(() => result.current.dock.investigate(TASK));
    await waitFor(() => expect(streamBodies()).toHaveLength(1));
    const first = result.current.store.activeSessionId!;

    act(() => result.current.store.deleteSession(first));
    act(() => result.current.dock.investigate(TASK));
    await waitFor(() => expect(streamBodies()).toHaveLength(2));
    expect(result.current.store.activeSessionId).not.toBe(first);
    expect(result.current.store.sessions.some((s) => s.id === first)).toBe(false);
  });

  it("resumes the newest investigation after a reload", async () => {
    const summary = (id: string, updated: string) => ({
      session_id: id,
      title: "Investigate execution exec-1",
      context: { investigation: EXECUTION_ONLY },
      message_count: 2,
      created_at: "2026-11-04T00:00:00Z",
      updated_at: updated,
    });
    // The API lists the most recently updated first.
    storedSessions = [
      summary("rerun", "2026-11-04T00:05:00Z"),
      summary("old", "2026-11-04T00:01:00Z"),
    ];
    storedMessages = {
      rerun: [{ role: "user", content: "Investigate" }, ANSWER],
    };
    const { result } = await renderDock();

    act(() => result.current.dock.investigate(EXECUTION_ONLY));
    expect(result.current.store.activeSessionId).toBe("rerun");
    await waitFor(() => expect(result.current.store.activeSession?.messagesLoaded).toBe(true));
    expect(streamBodies()).toHaveLength(0);
  });

  it.each(["reset", "delete"])(
    "starts fresh after %s with multiple historical runs",
    async (action) => {
      storedSessions = ["newest", "older"].map((id) => ({
        session_id: id,
        title: "Investigate execution exec-1",
        context: { investigation: EXECUTION_ONLY },
        message_count: 2,
        created_at: "2026-11-04T00:00:00Z",
        updated_at: "2026-11-04T00:01:00Z",
      }));
      storedMessages = { newest: [{ role: "user", content: "Investigate" }, ANSWER] };
      const { result } = await renderDock();
      act(() => result.current.dock.investigate(EXECUTION_ONLY));
      await waitFor(() => expect(result.current.store.activeSession?.messages).toHaveLength(2));
      act(() => {
        if (action === "reset") {
          result.current.dock.endInvestigation("newest");
          result.current.store.switchSession(null);
        } else {
          result.current.store.deleteSession("newest");
        }
      });
      act(() => result.current.dock.investigate(EXECUTION_ONLY));
      await waitFor(() => expect(streamBodies()).toHaveLength(1));
      expect(result.current.store.activeSessionId).not.toBe("newest");
      expect(result.current.store.activeSessionId).not.toBe("older");
      expect(streamBodies()[0].conversation_history).toEqual([]);
    },
  );

  it("starts fresh when reset and investigation happen before a render", async () => {
    const { result } = await renderDock();
    act(() => result.current.dock.investigate(TASK));
    await waitFor(() => expect(result.current.store.activeSession?.messages).toHaveLength(2));
    const first = result.current.store.activeSessionId!;
    act(() => {
      result.current.dock.endInvestigation(first);
      result.current.store.switchSession(null);
      result.current.dock.investigate(TASK);
      result.current.dock.investigate(TASK);
    });
    await waitFor(() => expect(streamBodies()).toHaveLength(2));
    expect(result.current.store.activeSessionId).not.toBe(first);
    expect(streamBodies()[1].conversation_history).toEqual([]);
  });

  it("keeps a reset through an unrelated render before switching sessions", async () => {
    const { result } = await renderDock();
    act(() => result.current.dock.investigate(TASK));
    await waitFor(() => expect(result.current.store.activeSession?.messages).toHaveLength(2));
    const first = result.current.store.activeSessionId!;
    act(() => {
      result.current.dock.endInvestigation(first);
      result.current.dock.closeSidebar();
    });
    act(() => {
      result.current.store.switchSession(null);
      result.current.dock.investigate(TASK);
    });
    await waitFor(() => expect(streamBodies()).toHaveLength(2));
    expect(result.current.store.activeSessionId).not.toBe(first);
    expect(streamBodies()[1].conversation_history).toEqual([]);
  });

  it("asks again in a stored investigation that holds no turn", async () => {
    storedSessions = [
      {
        session_id: "empty",
        title: "Investigate execution exec-1",
        context: { investigation: EXECUTION_ONLY },
        message_count: 0,
        created_at: "2026-11-04T00:00:00Z",
        updated_at: "2026-11-04T00:01:00Z",
      },
    ];
    const { result } = await renderDock();

    act(() => result.current.dock.investigate(EXECUTION_ONLY));
    await waitFor(() => expect(streamBodies()).toHaveLength(1));
    expect(streamBodies()[0].session_id).toBe("empty");
    expect(streamBodies()[0].investigation).toEqual({
      execution_id: "exec-1",
      chip_id: "64Q",
    });
    expect(calls("/copilot/chat/sessions", "POST")).toHaveLength(0);
    await waitFor(() => expect(result.current.store.activeSession?.messages).toHaveLength(2));

    act(() => result.current.dock.investigate(EXECUTION_ONLY));
    expect(streamBodies()).toHaveLength(1);
  });

  it("never shows the docked sidebar and the floating window at once", async () => {
    const { result } = await renderDock();
    const surfaces = () => [result.current.dock.isOpen, result.current.dock.miniChat.isOpen];

    act(() => result.current.dock.investigate(EXECUTION_ONLY, "sidebar"));
    expect(surfaces()).toEqual([true, false]);
    act(() => result.current.dock.investigate(EXECUTION_ONLY, "mini"));
    expect(surfaces()).toEqual([false, true]);
    act(() => result.current.dock.openGeneralChat());
    expect(surfaces()).toEqual([true, false]);
    act(() =>
      result.current.dock.openMiniChat({
        taskName: "CheckRabi",
        chipId: "64Q",
        qid: "3",
        executionId: "exec-1",
        taskId: "task-9",
      }),
    );
    expect(surfaces()).toEqual([false, true]);
  });
});
