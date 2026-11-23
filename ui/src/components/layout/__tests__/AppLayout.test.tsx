import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppLayout } from "@/components/layout/AppLayout";

const mockPathname = vi.hoisted(() => vi.fn(() => "/workflow/new"));

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { username: "tester", system_role: "user" },
    logout: vi.fn(),
  }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({
    canEdit: true,
    currentProject: { project_id: "p1", name: "Lab" },
    projects: [{ project_id: "p1", name: "Lab" }],
    loading: false,
    switchProject: vi.fn(),
  }),
}));

vi.mock("@/contexts/ThemeContext", () => ({
  useTheme: () => ({ theme: "light", setTheme: vi.fn() }),
}));

// Chat and onboarding layers are outside the navigation chrome under test.
vi.mock("@/contexts/AgentChatSessionContext", () => ({
  AgentChatSessionProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("@/contexts/ChatDockContext", () => ({
  ChatDockProvider: ({ children }: { children: ReactNode }) => children,
}));
const mockAgentTabShown = vi.hoisted(() => vi.fn(() => true));
vi.mock("@/components/layout/ChatSidebar", () => ({
  AGENT_TAB_WIDTH: "2rem",
  ChatSidebar: () => null,
  useAgentTabShown: () => mockAgentTabShown(),
}));
vi.mock("@/components/layout/MiniChatWindow", () => ({ MiniChatWindow: () => null }));
vi.mock("@/components/features/chat/ChatNotifier", () => ({ ChatNotifier: () => null }));
vi.mock("@/components/layout/GlobalCommandPalette", () => ({ GlobalCommandPalette: () => null }));
vi.mock("@/components/layout/GlobalExecutionIndicator", () => ({
  GlobalExecutionIndicator: () => null,
}));
vi.mock("@/components/layout/NotificationsMenu", () => ({ NotificationsMenu: () => null }));
vi.mock("@/components/ui/EnvironmentBadge", () => ({ EnvironmentBadge: () => null }));
vi.mock("@/components/features/first-calibration/FirstCalibrationBanner", () => ({
  FirstCalibrationBanner: () => null,
}));
vi.mock("@/components/features/first-calibration/FirstCalibrationCoachmarks", () => ({
  FirstCalibrationCoachmarks: () => null,
}));

function renderLayout() {
  return render(
    <AppLayout>
      <div data-testid="page">Page</div>
    </AppLayout>,
  );
}

describe("AppLayout navigation chrome", () => {
  afterEach(() => {
    cleanup();
    mockPathname.mockReturnValue("/workflow/new");
  });

  it("renders no navigation chrome on the login page", () => {
    mockPathname.mockReturnValue("/login");
    renderLayout();

    expect(screen.getByTestId("page")).toBeTruthy();
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.queryByRole("button", { name: "Open menu" })).toBeNull();
    expect(document.querySelector("main")).toBeNull();
  });

  it("keeps the desktop rail and adds the tab bar after main in the content column", () => {
    const { container } = renderLayout();

    const rail = container.querySelector('aside[aria-label="Primary navigation"]');
    const main = container.querySelector("main") as HTMLElement;
    const tabBar = container.querySelector('nav#mobile-tab-bar[aria-label="Primary navigation"]');

    expect(rail?.className).toContain("hidden");
    expect(rail?.className).toContain("lg:flex");
    expect(tabBar?.className).toContain("lg:hidden");
    // In-flow sibling after main: main shrinks above the bar, so nothing scrolls under it.
    expect(main.nextElementSibling).toBe(tabBar);
    expect(main.className).toContain("flex-1");
    expect(within(tabBar as HTMLElement).getByRole("link", { name: "Workflow" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(tabBar as HTMLElement).getByRole("link", { name: "Agent" })).toHaveAttribute(
      "href",
      "/chat",
    );
    // The desktop rail still lists Agent; only the mobile menu drops tab destinations.
    expect(within(rail as HTMLElement).getByRole("link", { name: "Agent" })).toBeTruthy();
  });

  it("sizes the shell to the visible viewport and pads it by the safe-area insets", () => {
    const { container } = renderLayout();

    const shell = container.firstElementChild as HTMLElement;

    expect(shell.className).toContain("h-dvh");
    expect(shell.className).not.toContain("h-screen");
    expect(shell.className).toContain("pl-[env(safe-area-inset-left)]");
    expect(shell.className).toContain("pr-[env(safe-area-inset-right)]");
    expect(shell.className).toContain("pt-[env(safe-area-inset-top)]");
  });

  it("removes the header hamburger and makes More the last tab bar item", () => {
    const { container } = renderLayout();

    expect(screen.queryByRole("button", { name: "Open menu" })).toBeNull();
    const header = container.querySelector("nav.navbar") as HTMLElement;
    expect(within(header).queryByRole("button", { name: "More" })).toBeNull();

    const tabBar = container.querySelector('nav#mobile-tab-bar[aria-label="Primary navigation"]');
    const dock = (tabBar as HTMLElement).querySelector(".dock") as HTMLElement;
    expect(dock.lastElementChild).toBe(within(dock).getByRole("button", { name: "More" }));
  });

  it("opens the More sheet, lists the other destinations, and restores focus on Escape", async () => {
    const { container } = renderLayout();

    const tabBar = container.querySelector('nav#mobile-tab-bar[aria-label="Primary navigation"]');
    const trigger = within(tabBar as HTMLElement).getByRole("button", { name: "More" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");

    act(() => trigger.focus());
    fireEvent.click(trigger);

    const sheet = screen.getByRole("dialog", { name: "More" });
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(sheet.contains(document.activeElement)).toBe(true);

    const nav = within(within(sheet).getByRole("navigation", { name: "More navigation" }));
    for (const label of [
      "Home",
      "Metrics",
      "Chip",
      "Analysis",
      "Task Results",
      "AI Evaluations",
      "Tasks",
      "Cryo",
      "Calibration DB",
      "Forum",
      "Knowledge",
      "Config",
      "Settings",
      "Docs",
      "Prefect",
    ]) {
      expect(nav.getByRole("link", { name: label })).toBeTruthy();
    }
    // The Beta badge is part of the Dashboards link name.
    expect(nav.getByRole("link", { name: /^Dashboards/ })).toHaveAttribute("href", "/dashboards");
    for (const label of ["Overview", "Workflow", "Execution", "Agent", "Admin"]) {
      expect(nav.queryByRole("link", { name: label })).toBeNull();
    }
    // The profile entry stays in the sheet.
    expect(within(sheet).getByRole("button", { name: /tester/ })).toBeTruthy();

    fireEvent.keyDown(sheet, { key: "Escape" });

    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("closes the More sheet from its close button and returns focus to More", async () => {
    renderLayout();

    const trigger = screen.getByRole("button", { name: "More" });
    act(() => trigger.focus());
    fireEvent.click(trigger);

    const sheet = screen.getByRole("dialog", { name: "More" });
    fireEvent.click(within(sheet).getByRole("button", { name: "Close menu" }));

    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("closes the More sheet after choosing a destination", () => {
    renderLayout();

    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.click(
      within(screen.getByRole("dialog", { name: "More" })).getByRole("link", {
        name: "Metrics",
      }),
    );

    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
  });

  it("closes the More sheet when the viewport widens to the desktop rail", () => {
    renderLayout();

    fireEvent.click(screen.getByRole("button", { name: "More" }));
    expect(screen.getByRole("dialog", { name: "More" })).toBeTruthy();

    const previousWidth = window.innerWidth;
    try {
      act(() => {
        Object.defineProperty(window, "innerWidth", { configurable: true, value: 1280 });
        window.dispatchEvent(new Event("resize"));
      });
      expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
    } finally {
      Object.defineProperty(window, "innerWidth", { configurable: true, value: previousWidth });
    }
  });

  it("highlights More on an overflow route", () => {
    mockPathname.mockReturnValue("/metrics");
    const { container } = renderLayout();

    const tabBar = container.querySelector('nav#mobile-tab-bar[aria-label="Primary navigation"]');
    const more = within(tabBar as HTMLElement).getByRole("button", { name: "More" });
    expect(more).toHaveAttribute("data-active", "true");
  });
});

describe("AppLayout room for the Ask Agent tab", () => {
  afterEach(() => {
    cleanup();
    mockAgentTabShown.mockReturnValue(true);
  });

  it("reserves the tab's width at the page edge while the tab floats over it", () => {
    renderLayout();
    const main = document.querySelector("main")!;
    expect(main.style.getPropertyValue("--agent-tab-inset")).toBe("calc(2rem + 0.25rem)");
  });

  it("reserves nothing while the sidebar is open or on the chat page", () => {
    mockAgentTabShown.mockReturnValue(false);
    renderLayout();
    const main = document.querySelector("main")!;
    expect(main.style.getPropertyValue("--agent-tab-inset")).toBe("");
  });
});
