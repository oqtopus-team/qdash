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
vi.mock("@/contexts/CopilotChatSessionContext", () => ({
  CopilotChatSessionProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("@/contexts/ChatDockContext", () => ({
  ChatDockProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("@/components/layout/ChatSidebar", () => ({ ChatSidebar: () => null }));
vi.mock("@/components/layout/MiniChatWindow", () => ({ MiniChatWindow: () => null }));
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
    expect(within(tabBar as HTMLElement).getByRole("link", { name: "AI Chat" })).toHaveAttribute(
      "href",
      "/chat",
    );
    // The desktop rail still lists AI Chat; only the mobile menu drops tab destinations.
    expect(within(rail as HTMLElement).getByRole("link", { name: "AI Chat" })).toBeTruthy();
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

  it("opens the header menu, lists the other destinations, and restores focus on Escape", async () => {
    const { container } = renderLayout();

    const tabBar = container.querySelector('nav#mobile-tab-bar[aria-label="Primary navigation"]');
    // The header trigger is the only menu opener; the tab bar holds route links only.
    expect(within(tabBar as HTMLElement).queryByRole("button")).toBeNull();

    const trigger = screen.getByRole("button", { name: "Open menu" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");

    act(() => trigger.focus());
    fireEvent.click(trigger);

    const drawer = screen.getByRole("dialog", { name: "Navigation menu" });
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(drawer.contains(document.activeElement)).toBe(true);

    const nav = within(within(drawer).getByRole("navigation", { name: "Menu navigation" }));
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
    ]) {
      expect(nav.getByRole("link", { name: label })).toBeTruthy();
    }
    for (const label of ["Dashboard", "Workflow", "Execution", "AI Chat"]) {
      expect(nav.queryByRole("link", { name: label })).toBeNull();
    }

    fireEvent.keyDown(drawer, { key: "Escape" });

    expect(screen.queryByRole("dialog", { name: "Navigation menu" })).toBeNull();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    // Radix restores focus to the trigger once the closed scope unmounts.
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("closes the header menu from its close button and returns focus to the trigger", async () => {
    renderLayout();

    const trigger = screen.getByRole("button", { name: "Open menu" });
    act(() => trigger.focus());
    fireEvent.click(trigger);

    const drawer = screen.getByRole("dialog", { name: "Navigation menu" });
    fireEvent.click(within(drawer).getByRole("button", { name: "Close menu" }));

    expect(screen.queryByRole("dialog", { name: "Navigation menu" })).toBeNull();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("closes the header menu after choosing a destination", () => {
    renderLayout();

    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    fireEvent.click(
      within(screen.getByRole("dialog", { name: "Navigation menu" })).getByRole("link", {
        name: "Metrics",
      }),
    );

    expect(screen.queryByRole("dialog", { name: "Navigation menu" })).toBeNull();
  });
});
