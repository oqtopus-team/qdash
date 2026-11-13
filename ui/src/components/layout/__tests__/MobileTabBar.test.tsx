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
    expect(getTabBar().children).toHaveLength(4);
  });

  it("uses the DaisyUI dock below lg and stays in the layout flow", () => {
    render(<MobileTabBar />);

    const className = getTabBar().className;

    expect(className).toContain("dock");
    expect(className).toContain("lg:hidden");
    expect(className).toContain("relative");
    expect(className).toContain("shrink-0");
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
    expect(current[0].className).toContain("text-primary");
  });

  it("marks no tab current on a menu destination", () => {
    mockPathname.mockReturnValue("/metrics");
    render(<MobileTabBar />);

    for (const link of within(getTabBar()).getAllByRole("link")) {
      expect(link.hasAttribute("aria-current")).toBe(false);
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
