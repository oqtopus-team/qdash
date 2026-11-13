import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MobileTabBar } from "@/components/layout/MobileTabBar";

const mockPathname = vi.hoisted(() => vi.fn(() => "/dashboard"));
const projectState = vi.hoisted(() => ({ canEdit: true }));

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname(),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ canEdit: projectState.canEdit }),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { username: "tester", system_role: "user" } }),
}));

function getTabBar() {
  return screen.getByRole("navigation", { name: "Primary navigation" });
}

describe("MobileTabBar", () => {
  afterEach(() => {
    cleanup();
    mockPathname.mockReturnValue("/dashboard");
    projectState.canEdit = true;
  });

  it("renders exactly four labeled route links with icons and no menu button", () => {
    render(<MobileTabBar />);

    const links = within(getTabBar()).getAllByRole("link");

    expect(links.map((link) => link.textContent)).toEqual([
      "Dashboard",
      "Workflow",
      "Execution",
      "AI Chat",
    ]);
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/dashboard",
      "/workflow",
      "/execution",
      "/chat",
    ]);
    for (const link of links) {
      expect(link.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
    }

    // Other destinations live in the header menu, so the bar holds only route links.
    expect(within(getTabBar()).queryByRole("button")).toBeNull();
    expect(getTabBar().querySelector(".dock")?.children).toHaveLength(4);
  });

  it("insets a rounded DaisyUI dock inside an in-flow nav below lg", () => {
    render(<MobileTabBar />);

    const nav = getTabBar();
    const dock = nav.firstElementChild as HTMLElement;

    // MiniChatWindow measures this element, so it must own the gap and safe-area reserve.
    expect(nav.id).toBe("mobile-tab-bar");
    expect(nav.className).toContain("lg:hidden");
    expect(nav.className).toContain("shrink-0");
    expect(nav.className).toContain("px-3");
    expect(nav.className).toContain("pb-[calc(0.75rem+env(safe-area-inset-bottom))]");
    expect(nav.children).toHaveLength(1);

    // The dock surface stays in flow instead of DaisyUI's fixed default.
    expect(dock.className).toContain("dock");
    expect(dock.className).toContain("relative");
    expect(dock.className).toContain("rounded-2xl");
  });

  it("gives every tab a 44px minimum width, a focus outline, and no dock underline", () => {
    render(<MobileTabBar />);

    for (const link of within(getTabBar()).getAllByRole("link")) {
      expect(link.className).toContain("min-w-11");
      expect(link.className).toContain("focus-visible:outline-2");
      expect(link.className).toContain("after:hidden");
      expect(link.className).not.toContain("dock-active");
    }
  });

  it.each([
    ["/dashboard", "Dashboard"],
    ["/workflow/new", "Workflow"],
    ["/workflow/calibrate-all", "Workflow"],
    ["/execution/chip-1/exec-1", "Execution"],
    ["/executions/exec-1", "Execution"],
    ["/chat", "AI Chat"],
    ["/chat/session-1", "AI Chat"],
  ])("marks only the owning tab current on %s", (pathname, label) => {
    mockPathname.mockReturnValue(pathname);
    render(<MobileTabBar />);

    const current = within(getTabBar())
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page");

    expect(current.map((link) => link.textContent)).toEqual([label]);

    // Only the current tab's icon sits in the tinted primary circle.
    const tinted = within(getTabBar())
      .getAllByTestId("mobile-tab-icon")
      .filter((icon) => icon.className.includes("bg-primary/15"));
    expect(tinted).toHaveLength(1);
    expect(tinted[0].className).toContain("rounded-full");
    expect(tinted[0].className).toContain("text-primary");
    expect(current[0].contains(tinted[0])).toBe(true);
  });

  it("marks no tab current on a menu destination", () => {
    mockPathname.mockReturnValue("/metrics");
    render(<MobileTabBar />);

    for (const link of within(getTabBar()).getAllByRole("link")) {
      expect(link.hasAttribute("aria-current")).toBe(false);
    }
    for (const icon of within(getTabBar()).getAllByTestId("mobile-tab-icon")) {
      expect(icon.className).not.toContain("bg-primary");
    }
  });

  it("hides the Workflow tab from members who cannot edit", () => {
    projectState.canEdit = false;
    render(<MobileTabBar />);

    expect(
      within(getTabBar())
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Dashboard", "Execution", "AI Chat"]);
  });
});
