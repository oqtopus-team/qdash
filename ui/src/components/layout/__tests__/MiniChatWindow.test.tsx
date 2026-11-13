import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MiniChatWindow } from "../MiniChatWindow";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock("@/contexts/ChatDockContext", () => ({
  useChatDock: () => ({ miniChat: { isOpen: true } }),
}));
vi.mock("@/contexts/CopilotChatSessionContext", () => ({
  useCopilotChatSessionContext: () => ({ runs: {}, activeSession: null }),
}));
vi.mock("@/components/features/chat/ChatThread", () => ({ ChatThread: () => null }));
vi.mock("@/components/features/chat/ChatSurfaceControls", () => ({
  RecentChatsMenu: () => null,
  SurfaceButton: ({ label, onClick }: { label: string; onClick: () => void }) => (
    <button onClick={onClick}>{label}</button>
  ),
  SurfaceTitle: () => null,
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("keeps chat above the measured safe-area dock and refits after viewport resize", () => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  vi.stubGlobal("innerWidth", 390);
  vi.stubGlobal("innerHeight", 844);
  const dock = document.createElement("nav");
  dock.id = "mobile-tab-bar";
  document.body.append(dock);
  const rect = vi.spyOn(dock, "getBoundingClientRect");
  rect.mockReturnValue({ top: 746, height: 98 } as DOMRect);
  render(<MiniChatWindow />);
  const chat = screen.getByRole("dialog", { name: "AI chat" });
  expect(parseFloat(chat.style.top) + parseFloat(chat.style.height)).toBe(730);
  vi.stubGlobal("innerWidth", 320);
  vi.stubGlobal("innerHeight", 568);
  rect.mockReturnValue({ top: 470, height: 98 } as DOMRect);
  act(() => window.dispatchEvent(new Event("resize")));
  expect(parseFloat(chat.style.width)).toBe(288);
  expect(parseFloat(chat.style.top) + parseFloat(chat.style.height)).toBe(454);
  dock.remove();
});

it("preserves minimization on resize and fits within an offset visual viewport", () => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  const viewport = Object.assign(new EventTarget(), {
    width: 390,
    height: 300,
    offsetTop: 300,
    offsetLeft: 20,
  });
  vi.stubGlobal("visualViewport", viewport);
  render(<MiniChatWindow />);
  const chat = screen.getByRole("dialog", { name: "AI chat" });
  expect(parseFloat(chat.style.top)).toBe(316);
  expect(parseFloat(chat.style.height)).toBe(268);
  expect(parseFloat(chat.style.left)).toBe(36);
  fireEvent.click(screen.getByRole("button", { name: "Minimize chat" }));
  act(() => viewport.dispatchEvent(new Event("resize")));
  expect(screen.getByRole("button", { name: "Expand chat" })).toBeTruthy();
  viewport.offsetTop = 400;
  act(() => viewport.dispatchEvent(new Event("scroll")));
  expect(parseFloat(chat.style.top)).toBe(416);
  expect(screen.getByRole("button", { name: "Expand chat" })).toBeTruthy();
});
