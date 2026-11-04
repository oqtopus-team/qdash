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

const EXECUTION_ONLY: InvestigationTarget = { executionId: "exec-1", chipId: "64Q" };
const TASK: InvestigationTarget = {
  executionId: "exec-1",
  taskId: "task-9",
  taskName: "CheckRabi",
  qid: "3",
  chipId: "64Q",
};

let storedSessions: unknown[];
let fetchMock: ReturnType<typeof vi.fn>;

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

beforeEach(() => {
  storedSessions = [];
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/stream")) {
      return new Response(sse("result", { blocks: [], assessment: null }), { status: 200 });
    }
    if (url.endsWith("/copilot/chat/sessions") && !init?.method) {
      return Response.json({ sessions: storedSessions });
    }
    return Response.json({ session_id: "x", title: "", context: null, messages: [] });
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
    expect(body.investigation).toEqual({ execution_id: "exec-1", chip_id: "64Q" });
    expect(body.task).toBeUndefined();
    expect(body.message).toMatch(/why execution exec-1 failed/);
    expect(body.page).toEqual({ path: "/execution", title: expect.any(String) });

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
    const { result } = await renderDock();
    expect(result.current.store.sessions[0].context).toBeNull();

    act(() => result.current.dock.investigate(EXECUTION_ONLY));
    expect(result.current.store.activeSessionId).toBe("saved");
    expect(streamBodies()).toHaveLength(0);
    expect(calls("/copilot/chat/sessions", "POST")).toHaveLength(0);
  });
});
