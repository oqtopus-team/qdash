import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatNotifier } from "@/components/features/chat/ChatNotifier";
import { ToastContainer } from "@/components/ui/Toast";
import type { ChatTurnEvent } from "@/types/copilotChat";

// Unlike ChatNotifier.test.tsx, Sonner is real here: chat toasts must render, update, stay, and
// close in the app's own toaster.
const state = vi.hoisted(() => ({
  listeners: new Set<(event: ChatTurnEvent) => void>(),
  switchSession: vi.fn(),
  openSidebar: vi.fn(),
}));

vi.mock("next/navigation", () => ({ usePathname: () => "/execution" }));
vi.mock("@/contexts/ThemeContext", () => ({ useTheme: () => ({ theme: "light" }) }));
vi.mock("@/contexts/CopilotChatSessionContext", () => ({
  useCopilotChatSessionContext: () => ({
    subscribeChatEvents: (listener: (event: ChatTurnEvent) => void) => {
      state.listeners.add(listener);
      return () => state.listeners.delete(listener);
    },
    activeSessionId: null,
    switchSession: state.switchSession,
    hasSession: () => true,
  }),
}));
vi.mock("@/contexts/ChatDockContext", () => ({
  useChatDock: () => ({
    isOpen: false,
    miniChat: { isOpen: false },
    openSidebar: state.openSidebar,
  }),
}));

const event = (over: Partial<ChatTurnEvent> = {}): ChatTurnEvent => ({
  kind: "answer",
  sessionId: "s1",
  requestId: "r1",
  owner: "alice",
  projectId: "p1",
  chatTitle: "Calibrate Q0",
  ...over,
});

// Sonner hands a new toast to its toaster on a timer, so let it run.
const emit = (e: ChatTurnEvent) =>
  act(() => {
    state.listeners.forEach((l) => l(e));
    vi.advanceTimersByTime(0);
  });

function renderApp() {
  return render(
    <>
      <ToastContainer />
      <ChatNotifier owner="alice" project="p1" />
    </>,
  );
}

beforeEach(() => {
  vi.useFakeTimers();
  state.listeners.clear();
  state.switchSession.mockClear();
  state.openSidebar.mockClear();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("chat notifications in the app toaster", () => {
  it("shows the chat and opens it from the toast", () => {
    renderApp();
    emit(event({ detail: "T1 fit done" }));

    expect(screen.getByText("Answer ready")).toBeInTheDocument();
    expect(screen.getByText("Calibrate Q0: T1 fit done")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));
    act(() => vi.advanceTimersByTime(1000));

    expect(state.switchSession).toHaveBeenCalledWith("s1");
    expect(state.openSidebar).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Answer ready")).not.toBeInTheDocument();
  });

  it("updates a repeated moment in place instead of stacking another toast", () => {
    renderApp();
    emit(event());
    emit(event());

    expect(screen.getAllByText("Answer ready")).toHaveLength(1);
  });

  it("keeps toasts that need input until dismissed, while an answer goes on its own", () => {
    renderApp();
    emit(event({ kind: "approval" }));
    emit(event({ requestId: "r2", kind: "failed" }));
    emit(event({ requestId: "r3" }));

    act(() => vi.advanceTimersByTime(60_000));

    expect(screen.getByText("Approval needed")).toBeInTheDocument();
    expect(screen.getByText("The answer failed")).toBeInTheDocument();
    expect(screen.queryByText("Answer ready")).not.toBeInTheDocument();
  });
});
