import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MobileTabBar } from "@/components/layout/MobileTabBar";

const mockPathname = vi.hoisted(() => vi.fn(() => "/overview"));
const projectState = vi.hoisted(() => ({ canEdit: true }));

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname(),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ canEdit: projectState.canEdit }),
}));

const authState = vi.hoisted(() => ({ role: "user" }));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { username: "tester", system_role: authState.role } }),
}));

const sidebarState = vi.hoisted(() => ({ isMobileOpen: false }));
const toggleMobileSidebar = vi.hoisted(() => vi.fn());
vi.mock("@/contexts/SidebarContext", () => ({
  useSidebar: () => ({
    isMobileOpen: sidebarState.isMobileOpen,
    toggleMobileSidebar,
  }),
}));

function getMore() {
  return within(getTabBar()).getByRole("button", { name: "More" });
}

function isHighlighted(item: HTMLElement) {
  return within(item).getByTestId("mobile-tab-icon").className.includes("bg-primary/15");
}

function getTabBar() {
  return screen.getByRole("navigation", { name: "Primary navigation" });
}

describe("MobileTabBar", () => {
  afterEach(() => {
    cleanup();
    mockPathname.mockReturnValue("/overview");
    projectState.canEdit = true;
    authState.role = "user";
    sidebarState.isMobileOpen = false;
    toggleMobileSidebar.mockClear();
  });

  it("renders four labeled route links followed by a More button", () => {
    render(<MobileTabBar />);

    const links = within(getTabBar()).getAllByRole("link");

    expect(links.map((link) => link.textContent)).toEqual([
      "Overview",
      "Workflow",
      "Execution",
      "Agent",
    ]);
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/overview",
      "/workflow",
      "/execution",
      "/chat",
    ]);
    for (const link of links) {
      expect(link.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
    }

    // Every other destination sits behind More, the last dock item.
    const dock = getTabBar().querySelector(".dock") as HTMLElement;
    expect(dock.children).toHaveLength(5);
    expect(dock.lastElementChild).toBe(getMore());
    expect(within(getTabBar()).getAllByRole("button")).toHaveLength(1);
    expect(getMore().querySelector('svg[aria-hidden="true"]')).not.toBeNull();
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

    for (const link of [...within(getTabBar()).getAllByRole("link"), getMore()]) {
      expect(link.className).toContain("min-w-11");
      expect(link.className).toContain("focus-visible:outline-2");
      expect(link.className).toContain("after:hidden");
      expect(link.className).not.toContain("dock-active");
    }
  });

  it.each([
    ["/overview", "Overview"],
    ["/workflow/new", "Workflow"],
    ["/workflow/calibrate-all", "Workflow"],
    ["/execution/chip-1/exec-1", "Execution"],
    ["/executions/exec-1", "Execution"],
    ["/calibration-sessions", "Execution"],
    ["/calibration-sessions/cs-1", "Execution"],
    ["/chat", "Agent"],
    ["/chat/session-1", "Agent"],
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

  it.each(["/metrics", "/task-results/abc", "/settings", "/dashboards/d1"])(
    "highlights only More on the overflow route %s",
    (pathname) => {
      mockPathname.mockReturnValue(pathname);
      render(<MobileTabBar />);

      for (const link of within(getTabBar()).getAllByRole("link")) {
        expect(link.hasAttribute("aria-current")).toBe(false);
        expect(isHighlighted(link)).toBe(false);
      }
      expect(isHighlighted(getMore())).toBe(true);
      expect(getMore()).toHaveAttribute("data-active", "true");
    },
  );

  it("leaves More plain on a tab route and on an unlisted route", () => {
    render(<MobileTabBar />);
    expect(isHighlighted(getMore())).toBe(false);
    expect(getMore().hasAttribute("data-active")).toBe(false);
    cleanup();

    mockPathname.mockReturnValue("/admin");
    render(<MobileTabBar />);
    // Admin is hidden from members, so its route does not belong to More.
    expect(isHighlighted(getMore())).toBe(false);
  });

  it("highlights More on the Admin route for system admins", () => {
    authState.role = "admin";
    mockPathname.mockReturnValue("/admin");
    render(<MobileTabBar />);

    expect(isHighlighted(getMore())).toBe(true);
  });

  it("toggles the More sheet and reports it as a collapsed dialog trigger", () => {
    render(<MobileTabBar />);

    const more = getMore();
    expect(more).toHaveAttribute("type", "button");
    expect(more).toHaveAttribute("aria-haspopup", "dialog");
    expect(more).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(more);
    expect(toggleMobileSidebar).toHaveBeenCalledTimes(1);
  });

  it("moves the highlight to More while the sheet is open", () => {
    sidebarState.isMobileOpen = true;
    render(<MobileTabBar />);

    const overview = within(getTabBar()).getByRole("link", { name: "Overview" });
    // The route stays current for assistive technology; only the highlight moves.
    expect(overview).toHaveAttribute("aria-current", "page");
    expect(isHighlighted(overview)).toBe(false);
    expect(getMore()).toHaveAttribute("aria-expanded", "true");
    expect(isHighlighted(getMore())).toBe(true);
  });

  it("hides the Workflow tab from members who cannot edit", () => {
    projectState.canEdit = false;
    render(<MobileTabBar />);

    expect(
      within(getTabBar())
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Overview", "Execution", "Agent"]);
  });
});
