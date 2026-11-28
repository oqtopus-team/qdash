import { cleanup, render, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PageContainer } from "@/components/ui/PageContainer";
import { AGENT_TAB_WIDTH, ChatSidebar, useAgentTabShown } from "../ChatSidebar";

const mocks = vi.hoisted(() => ({
  pathname: "/dashboards/dash-1",
  isOpen: false,
  runs: {} as Record<string, { connection?: { state: string } }>,
  detachedTurns: {} as Record<string, { reason: string }>,
}));

vi.mock("next/navigation", () => ({ usePathname: () => mocks.pathname }));
vi.mock("@/contexts/ChatDockContext", () => ({
  useChatDock: () => ({
    isOpen: mocks.isOpen,
    openGeneralChat: vi.fn(),
    closeSidebar: vi.fn(),
  }),
}));
vi.mock("@/contexts/AgentChatSessionContext", () => ({
  useAgentChatSessionContext: () => ({ runs: mocks.runs, detachedTurns: mocks.detachedTurns }),
}));
vi.mock("@/components/features/chat/DockedChatPanel", () => ({
  DockedChatPanel: () => <div data-testid="docked-chat" />,
}));

afterEach(() => {
  cleanup();
  mocks.pathname = "/dashboards/dash-1";
  mocks.isOpen = false;
  mocks.runs = {};
  mocks.detachedTurns = {};
});

describe("the Ask Agent tab", () => {
  it("has the width the layout reserves for it", () => {
    render(<ChatSidebar />);
    const tab = screen.getByRole("button", { name: "Ask Agent" });
    expect(tab.style.width).toBe(AGENT_TAB_WIDTH);
  });

  it("says when an answer is running or being reattached, from the chat's actual turns", () => {
    mocks.runs = { s1: { connection: { state: "live" } } };
    const { unmount } = render(<ChatSidebar />);
    expect(screen.getByRole("button", { name: "Ask Agent, an answer is running" })).toHaveAttribute(
      "data-activity",
      "working",
    );
    unmount();
    // A turn restored after a reload, not streaming yet: reconnecting, not idle.
    mocks.runs = {};
    mocks.detachedTurns = { s1: { reason: "restoring" } };
    render(<ChatSidebar />);
    expect(
      screen.getByRole("button", { name: "Ask Agent, reconnecting to an answer" }),
    ).toHaveAttribute("data-activity", "reconnecting");
  });

  it("is shown only while the sidebar is closed, and never on the chat page", () => {
    expect(renderHook(() => useAgentTabShown()).result.current).toBe(true);
    mocks.isOpen = true;
    expect(renderHook(() => useAgentTabShown()).result.current).toBe(false);
    mocks.isOpen = false;
    mocks.pathname = "/chat";
    expect(renderHook(() => useAgentTabShown()).result.current).toBe(false);
  });
});

describe("PageContainer beside the tab", () => {
  it("widens its right gutter to the tab inset instead of adding to it", () => {
    const { container } = render(<PageContainer>Page</PageContainer>);
    const classes = (container.firstChild as HTMLElement).className.split(" ");
    expect(classes).toContain("pr-[max(1rem,var(--agent-tab-inset,0px))]");
    expect(classes).toContain("md:pr-[max(1.5rem,var(--agent-tab-inset,0px))]");
    expect(classes).not.toContain("px-4");
  });
});
