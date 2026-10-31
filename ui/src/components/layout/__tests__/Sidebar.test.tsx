import { cleanup, fireEvent, render, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Sidebar } from "@/components/layout/Sidebar";

const push = vi.fn();
const mockPathname = vi.hoisted(() => vi.fn(() => "/dashboard"));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => mockPathname(),
}));

const setMobileSidebarOpen = vi.fn();
const toggleSidebar = vi.fn();
const sidebarState = vi.hoisted(() => ({ isOpen: true, isMobileOpen: false }));

vi.mock("@/contexts/SidebarContext", () => ({
  useSidebar: () => ({
    isOpen: sidebarState.isOpen,
    isMobileOpen: sidebarState.isMobileOpen,
    toggleSidebar,
    setSidebarOpen: vi.fn(),
    toggleMobileSidebar: vi.fn(),
    setMobileSidebarOpen,
  }),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { username: "tester", system_role: "user" },
    logout: vi.fn(),
  }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ canEdit: false }),
}));

vi.mock("@/contexts/ThemeContext", () => ({
  useTheme: () => ({ theme: "light", setTheme: vi.fn() }),
}));

/**
 * Pulls the desktop and mobile navigation asides out of a render. Both carry the
 * same aria-label, so they are told apart by their `lg:` visibility class.
 * Throws when either is missing so a broken render fails here, not on undefined.
 */
function getAsides(container: HTMLElement) {
  const asides = container.querySelectorAll('aside[aria-label="Primary navigation"]');
  const desktop = Array.from(asides).find((aside) => aside.className.includes("lg:flex"));
  const mobile = Array.from(asides).find((aside) => aside.className.includes("lg:hidden"));
  if (!desktop || !mobile) {
    throw new Error("Expected both desktop and mobile Primary navigation asides");
  }
  return { desktop, mobile };
}

/** Returns the shared active-row pill of the section that contains `href`. */
function getSectionIndicator(aside: Element, href: string) {
  const link = aside.querySelector(`a[href="${href}"]`);
  const indicator = link
    ?.closest("ul")
    ?.parentElement?.querySelector('[data-testid="sidebar-active-indicator"]');
  if (!link || !indicator) {
    throw new Error(`Expected a section indicator around ${href}`);
  }
  return { link, indicator };
}

describe("Sidebar", () => {
  beforeEach(() => {
    // jsdom has no layout, so give every element a distinct box derived from its
    // document order; the shared indicator only moves when the active box changes.
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (
      this: Element,
    ) {
      const top = Array.from(document.querySelectorAll("*")).indexOf(this) * 36;
      return {
        x: 0,
        y: top,
        top,
        left: 0,
        width: 150,
        height: 36,
        right: 150,
        bottom: top + 36,
        toJSON: () => ({}),
      } as DOMRect;
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.clearAllMocks();
    mockPathname.mockReturnValue("/dashboard");
    sidebarState.isOpen = true;
    sidebarState.isMobileOpen = false;
  });

  it("narrows the mobile drawer to w-56 and drops w-72", () => {
    const { container } = render(<Sidebar />);

    const { mobile } = getAsides(container);

    expect(mobile.className).toContain("w-56");
    expect(mobile.className).not.toContain("w-72");
  });

  it("makes the mobile menu rows fill the drawer instead of the widest label", () => {
    const { container } = render(<Sidebar />);

    const menu = getAsides(container).mobile.querySelector("nav ul.menu");
    const stack = menu?.parentElement?.closest("nav > div");

    expect(stack?.className).toContain("w-fit");
    expect(stack?.className).toContain("max-lg:w-full");
    expect(menu?.className).toContain("w-full");
    expect(menu?.className).toContain("max-lg:flex-nowrap");
    expect(menu?.className).toContain("max-lg:[&>li]:flex-nowrap");
  });

  it("shows the active-row indicator only in the section that owns the route", () => {
    const { container } = render(<Sidebar />);

    const { desktop } = getAsides(container);
    const visible = desktop.querySelectorAll(
      '[data-testid="sidebar-active-indicator"][data-state="visible"]',
    );
    const { link, indicator } = getSectionIndicator(desktop, "/dashboard");

    expect(link.getAttribute("aria-current")).toBe("page");
    expect(visible).toHaveLength(1);
    expect(visible[0]).toBe(indicator);
    expect(indicator.getAttribute("data-motion")).toBe("fade");
  });

  it("slides the indicator when the route moves within a section", () => {
    const { container, rerender } = render(<Sidebar />);

    mockPathname.mockReturnValue("/metrics");
    rerender(<Sidebar />);

    const { desktop } = getAsides(container);
    const { link, indicator } = getSectionIndicator(desktop, "/metrics");

    expect(link.getAttribute("aria-current")).toBe("page");
    expect(indicator.getAttribute("data-state")).toBe("visible");
    expect(indicator.getAttribute("data-motion")).toBe("slide");
  });

  it("fades between sections instead of sliding across them", () => {
    const { container, rerender } = render(<Sidebar />);

    mockPathname.mockReturnValue("/execution");
    rerender(<Sidebar />);

    const { desktop } = getAsides(container);
    const overview = getSectionIndicator(desktop, "/dashboard").indicator;
    const { link, indicator: operate } = getSectionIndicator(desktop, "/execution");

    expect(link.getAttribute("aria-current")).toBe("page");
    expect(overview.getAttribute("data-state")).toBe("hidden");
    expect(overview.getAttribute("data-motion")).toBe("fade");
    expect(operate.getAttribute("data-state")).toBe("visible");
    expect(operate.getAttribute("data-motion")).toBe("fade");
  });

  it("truncates a nav label instead of letting it grow the row", () => {
    sidebarState.isMobileOpen = true;
    const { container } = render(<Sidebar />);

    const { mobile } = getAsides(container);
    const label = within(mobile as HTMLElement).getByText("Knowledge");

    expect(label.className).toContain("truncate");
  });

  it("keeps the desktop sidebar at w-48 when expanded", () => {
    sidebarState.isOpen = true;
    const { container } = render(<Sidebar />);

    const { desktop } = getAsides(container);

    expect(desktop.className).toContain("w-48");
    expect(desktop.className).not.toContain("w-16");
  });

  it("collapses the desktop sidebar to w-16 when closed", () => {
    sidebarState.isOpen = false;
    const { container } = render(<Sidebar />);

    const { desktop } = getAsides(container);

    expect(desktop.className).toContain("w-16");
    expect(desktop.className).not.toContain("w-48");
  });

  it("closes the mobile drawer from the Close menu button", () => {
    sidebarState.isMobileOpen = true;
    const { container } = render(<Sidebar />);

    const { mobile } = getAsides(container);
    fireEvent.click(within(mobile as HTMLElement).getByRole("button", { name: "Close menu" }));

    expect(setMobileSidebarOpen).toHaveBeenCalledWith(false);
  });

  it("pairs the logo with the close button in the mobile drawer header", () => {
    sidebarState.isMobileOpen = true;
    const { container } = render(<Sidebar />);

    const { mobile } = getAsides(container);
    const header = within(mobile.firstElementChild as HTMLElement);

    expect(header.getByRole("link", { name: "QDash home" })).toBeTruthy();
    expect(header.getByRole("button", { name: "Close menu" })).toBeTruthy();
  });

  it("keeps the in-nav logo out of the mobile drawer", () => {
    const { container } = render(<Sidebar />);

    const { mobile } = getAsides(container);
    const navLogo = mobile.querySelector('nav a[aria-label="QDash home"]');

    expect(navLogo?.closest("li")?.className).toContain("hidden lg:block");
  });

  it("closes the mobile drawer when a nav link is clicked", () => {
    sidebarState.isMobileOpen = true;
    const { container } = render(<Sidebar />);

    const { mobile } = getAsides(container);
    fireEvent.click(within(mobile as HTMLElement).getByRole("link", { name: "Home" }));

    expect(setMobileSidebarOpen).toHaveBeenCalledWith(false);
  });
});
