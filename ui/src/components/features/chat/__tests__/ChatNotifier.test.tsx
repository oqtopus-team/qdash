import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatNotifier, chatToastId } from "@/components/features/chat/ChatNotifier";
import type { ChatTurnEvent } from "@/types/agentChat";

const state = vi.hoisted(() => ({
  listeners: new Set<(event: ChatTurnEvent) => void>(),
  activeSessionId: null as string | null,
  isOpen: false,
  miniOpen: false,
  pathname: "/execution",
  sessions: new Set(["s1", "s2"]),
  switchSession: vi.fn(),
  openSidebar: vi.fn(),
  sendMessage: vi.fn(),
  shown: [] as Array<{ type: string; title: string; options: Record<string, unknown> }>,
  closed: [] as string[],
}));

vi.mock("next/navigation", () => ({ usePathname: () => state.pathname }));
vi.mock("@/contexts/AgentChatSessionContext", () => ({
  useAgentChatSessionContext: () => ({
    subscribeChatEvents: (listener: (event: ChatTurnEvent) => void) => {
      state.listeners.add(listener);
      return () => state.listeners.delete(listener);
    },
    activeSessionId: state.activeSessionId,
    switchSession: state.switchSession,
    hasSession: (id: string) => state.sessions.has(id),
    sendMessage: state.sendMessage,
  }),
}));
vi.mock("@/contexts/ChatDockContext", () => ({
  useChatDock: () => ({
    isOpen: state.isOpen,
    miniChat: { isOpen: state.miniOpen },
    openSidebar: state.openSidebar,
  }),
}));
vi.mock("@yusufceng1z/ding-react", () => {
  const show = (type: string) => (title: string, options: Record<string, unknown>) => {
    state.shown.push({ type, title, options });
    return options.id;
  };
  return {
    toast: {
      success: show("success"),
      error: show("error"),
      warning: show("warning"),
      info: show("info"),
      close: (id: string) => state.closed.push(id),
    },
  };
});

const event = (over: Partial<ChatTurnEvent> = {}): ChatTurnEvent => ({
  kind: "answer",
  sessionId: "s1",
  requestId: "r1",
  owner: "alice",
  projectId: "p1",
  chatTitle: "Calibrate Q0",
  ...over,
});

const emit = (e: ChatTurnEvent) => act(() => state.listeners.forEach((l) => l(e)));

beforeEach(() => {
  state.listeners.clear();
  state.activeSessionId = null;
  state.isOpen = false;
  state.miniOpen = false;
  state.pathname = "/execution";
  state.shown = [];
  state.closed = [];
  state.switchSession.mockClear();
  state.openSidebar.mockClear();
  state.sendMessage.mockClear();
});
afterEach(cleanup);

describe("chat notifications", () => {
  it("shows one toast per moment of a turn, keyed so a repeat updates it", () => {
    render(<ChatNotifier owner="alice" project="p1" />);
    emit(event());
    emit(event({ kind: "approval" }));
    expect(state.shown.map((t) => [t.type, t.title, t.options.id])).toEqual([
      ["success", "Answer ready", "chat:r1:answer"],
      ["warning", "Approval needed", "chat:r1:approval"],
    ]);
    // Input needed stays until dismissed; a ready answer goes on its own.
    expect(state.shown[1].options.duration).toBe(0);
    expect(state.shown[0].options.duration).toBeGreaterThan(0);
    expect(chatToastId({ requestId: "r1", kind: "answer" })).toBe("chat:r1:answer");
  });

  it("opens the chat the toast is about, and sends nothing", () => {
    render(<ChatNotifier owner="alice" project="p1" />);
    emit(event({ sessionId: "s2", requestId: "r2" }));
    const action = state.shown[0].options.action as { label: string; onClick: () => void };
    expect(action.label).toBe("Open chat");
    act(() => action.onClick());
    expect(state.switchSession).toHaveBeenCalledWith("s2");
    expect(state.openSidebar).toHaveBeenCalledTimes(1);
    expect(state.sendMessage).not.toHaveBeenCalled();
  });

  it("shows nothing for another user, another project, or a chat already on screen", () => {
    const view = render(<ChatNotifier owner="alice" project="p1" />);
    emit(event({ owner: "bob" }));
    emit(event({ projectId: "p2" }));
    state.activeSessionId = "s1";
    state.isOpen = true;
    view.rerender(<ChatNotifier owner="alice" project="p1" />);
    emit(event());
    expect(state.shown).toEqual([]);
  });

  it("does not open a chat after the user changed", () => {
    const view = render(<ChatNotifier owner="alice" project="p1" />);
    emit(event());
    view.rerender(<ChatNotifier owner="bob" project="p1" />);
    const action = state.shown[0].options.action as { onClick: () => void };
    act(() => action.onClick());
    expect(state.switchSession).not.toHaveBeenCalled();
  });

  it("does not open a stale toast after the project changes or becomes unknown", () => {
    const view = render(<ChatNotifier owner="alice" project="p1" />);
    emit(event());
    const action = state.shown[0].options.action as { onClick: () => void };
    for (const project of ["p2", null]) {
      view.rerender(<ChatNotifier owner="alice" project={project} />);
      act(() => action.onClick());
    }
    expect(state.switchSession).not.toHaveBeenCalled();
    expect(state.openSidebar).not.toHaveBeenCalled();
    expect(state.sendMessage).not.toHaveBeenCalled();
  });

  it("takes a chat's toasts away once that chat is on screen", () => {
    const view = render(<ChatNotifier owner="alice" project="p1" />);
    emit(event({ kind: "question" }));
    state.activeSessionId = "s1";
    state.pathname = "/chat";
    view.rerender(<ChatNotifier owner="alice" project="p1" />);
    expect(state.closed).toEqual(["chat:r1:question"]);
  });
});
