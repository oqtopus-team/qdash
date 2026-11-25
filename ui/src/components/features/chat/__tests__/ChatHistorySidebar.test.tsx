import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentSession } from "@/hooks/useAgentChat";
import { ChatSidebar } from "../ChatSidebar";

const NOW = Date.now();

function session(id: string, title: string, minutesAgo: number): AgentSession {
  const ts = NOW - minutesAgo * 60_000;
  return {
    id,
    title,
    context: null,
    messages: [],
    createdAt: ts,
    updatedAt: ts,
    messagesLoaded: true,
  };
}

const sessions = [session("a", "T1 drift on Q05", 5), session("b", "Readout fidelity", 180)];

function renderSidebar(props: Partial<Parameters<typeof ChatSidebar>[0]> = {}) {
  const handlers = {
    onNewChat: vi.fn(),
    onSelect: vi.fn(),
    onRename: vi.fn(),
    onDelete: vi.fn(),
    onClose: vi.fn(),
  };
  render(
    <ChatSidebar
      sessions={sessions}
      activeSessionId="a"
      isLoading={false}
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

afterEach(cleanup);

describe("chat history sidebar", () => {
  it("marks the open chat and keeps each row named by its title alone", () => {
    renderSidebar();
    const history = screen.getByRole("navigation", { name: "Chat history" });
    const active = within(history).getByRole("button", { name: "T1 drift on Q05" });
    expect(active).toHaveAttribute("aria-current", "page");
    expect(within(history).getByRole("button", { name: "Readout fidelity" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("names a chat that is still answering, outside the row's own name", () => {
    renderSidebar({ runningSessionIds: ["b"] });
    expect(screen.getByRole("status", { name: "Readout fidelity is answering" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Readout fidelity" })).toHaveClass(
      "chat-sidebar-item-running",
    );
    expect(screen.getByRole("button", { name: "T1 drift on Q05" })).not.toHaveClass(
      "chat-sidebar-item-running",
    );
  });

  it("starts a new chat from its labeled button", () => {
    const { onNewChat } = renderSidebar();
    fireEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(onNewChat).toHaveBeenCalledOnce();
  });

  it("filters by title and says when nothing matches", () => {
    renderSidebar();
    const search = screen.getByRole("searchbox", { name: "Search chats" });
    fireEvent.change(search, { target: { value: "readout" } });
    expect(screen.queryByRole("button", { name: "T1 drift on Q05" })).toBeNull();
    expect(screen.getByRole("button", { name: "Readout fidelity" })).toBeInTheDocument();
    fireEvent.change(search, { target: { value: "nothing" } });
    expect(screen.getByText("No matching chats")).toBeInTheDocument();
  });

  it("keeps the options menu reachable for every chat", () => {
    renderSidebar();
    expect(screen.getByRole("button", { name: "Options for T1 drift on Q05" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Options for Readout fidelity" }),
    ).toBeInTheDocument();
  });
});
