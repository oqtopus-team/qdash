import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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
const projectState = vi.hoisted(() => ({ canEdit: false }));

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
  useProject: () => ({ canEdit: projectState.canEdit }),
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
    projectState.canEdit = false;
  });

  it("narrows the mobile drawer to w-56 and drops w-72", () => {
    const { container } = render(<Sidebar />);

    const { mobile } = getAsides(container);

    expect(mobile.className).toContain("w-56");
    expect(mobile.className).not.toContain("w-72");
  });

  it("makes the menu rows fill the drawer or rail instead of the widest label", () => {
    const { container } = render(<Sidebar />);

    for (const aside of Object.values(getAsides(container))) {
      const menu = aside.querySelector("nav ul.menu");
      const stack = aside.querySelector("nav > div");

      expect(stack?.className).toContain("w-full");
      expect(stack?.className).not.toContain("w-fit");
      expect(menu?.className).toContain("w-full");
      expect(menu?.className).toContain("flex-nowrap");
      expect(menu?.className).toContain("[&>li]:flex-nowrap");
    }
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

    expect(header.getByRole("link", { name: "QDash home" }).textContent).toBe("QDash");
    expect(header.getByRole("button", { name: "Close menu" })).toBeTruthy();
  });

  it("pairs the logo and product name with the collapse button on the expanded rail", () => {
    const { container } = render(<Sidebar />);

    const { desktop } = getAsides(container);
    const header = desktop.querySelector('[data-testid="sidebar-desktop-header"]') as HTMLElement;
    const home = within(header).getByRole("link", { name: "QDash home" });

    expect(header.className).toContain("h-16");
    expect(home.textContent).toBe("QDash");
    expect(home.querySelector("img")?.getAttribute("alt")).toBe("");
    expect(within(header).getByRole("button", { name: "Collapse sidebar" })).toBeTruthy();
  });

  it("shows only the expand button in the collapsed rail header", () => {
    sidebarState.isOpen = false;
    const { container } = render(<Sidebar />);

    const { desktop } = getAsides(container);
    const header = desktop.querySelector('[data-testid="sidebar-desktop-header"]') as HTMLElement;

    expect(header.className).toContain("h-16");
    expect(within(header).queryByRole("link", { name: "QDash home" })).toBeNull();
    expect(within(header).getByRole("button", { name: "Expand sidebar" })).toBeTruthy();
  });

  it("renders exactly one home logo per sidebar and none inside the nav", () => {
    const { container } = render(<Sidebar />);

    const { desktop, mobile } = getAsides(container);

    for (const aside of [desktop, mobile]) {
      expect(aside.querySelectorAll('a[aria-label="QDash home"]')).toHaveLength(1);
      expect(aside.querySelector('nav a[aria-label="QDash home"]')).toBeNull();
    }
  });

  it("closes the mobile drawer when the home logo is clicked", () => {
    sidebarState.isMobileOpen = true;
    const { container } = render(<Sidebar />);

    const { mobile } = getAsides(container);
    fireEvent.click(within(mobile as HTMLElement).getByRole("link", { name: "QDash home" }));

    expect(setMobileSidebarOpen).toHaveBeenCalledWith(false);
  });

  it("closes the mobile drawer when a nav link is clicked", () => {
    sidebarState.isMobileOpen = true;
    const { container } = render(<Sidebar />);

    const { mobile } = getAsides(container);
    fireEvent.click(within(mobile as HTMLElement).getByRole("link", { name: "Home" }));

    expect(setMobileSidebarOpen).toHaveBeenCalledWith(false);
  });

  it("links Prefect to the same-origin /prefect/dashboard path", () => {
    projectState.canEdit = true;
    const { container } = render(<Sidebar />);

    const { desktop } = getAsides(container);
    const prefectLink = within(desktop as HTMLElement).getByRole("link", { name: "Prefect" });

    expect(prefectLink.getAttribute("href")).toBe("/prefect/dashboard");
  });

  describe("desktop rail toggle and tooltips", () => {
    afterEach(() => {
      vi.useRealTimers();
    });

    /** Focuses `element` the way keyboard navigation does, flushing Radix updates. */
    function focus(element: HTMLElement) {
      act(() => element.focus());
    }

    function getDesktop(container: HTMLElement) {
      return within(getAsides(container).desktop as HTMLElement);
    }

    it("uses a panel toggle that reports the rail state it controls", () => {
      sidebarState.isOpen = false;
      const { container, rerender } = render(<Sidebar />);

      const { desktop } = getAsides(container);
      const expand = within(desktop as HTMLElement).getByRole("button", {
        name: "Expand sidebar",
      });
      expect(expand.getAttribute("aria-expanded")).toBe("false");
      expect(expand.getAttribute("aria-controls")).toBe(desktop.id);
      expect(expand.querySelector("svg.lucide-panel-left-open")).not.toBeNull();

      fireEvent.click(expand);
      expect(toggleSidebar).toHaveBeenCalledTimes(1);

      sidebarState.isOpen = true;
      rerender(<Sidebar />);
      const collapse = getDesktop(container).getByRole("button", { name: "Collapse sidebar" });
      expect(collapse.getAttribute("aria-expanded")).toBe("true");
      expect(collapse.querySelector("svg.lucide-panel-left-close")).not.toBeNull();
    });

    it("animates the rail width only when motion is allowed", () => {
      const { container } = render(<Sidebar />);

      const { desktop } = getAsides(container);

      expect(desktop.className).toContain("transition-[width]");
      expect(desktop.className).toContain("motion-reduce:transition-none");
      expect(desktop.className).toContain("overflow-hidden");
    });

    it("drops native title tooltips from every sidebar control", () => {
      projectState.canEdit = true;
      sidebarState.isOpen = false;
      const { container } = render(<Sidebar />);

      expect(container.querySelectorAll("aside [title]")).toHaveLength(0);
    });

    it("names collapsed icon rows and shows a right-side tooltip on keyboard focus", () => {
      sidebarState.isOpen = false;
      const { container } = render(<Sidebar />);

      const { desktop } = getAsides(container);
      const home = within(desktop as HTMLElement).getByRole("link", { name: "Home" });
      focus(home);

      const tooltip = screen.getByRole("tooltip");
      expect(tooltip.textContent).toBe("Home");
      expect(home.getAttribute("aria-describedby")).toBe(tooltip.id);
      // Portalled out of the scrolling nav, so the rail cannot clip it.
      expect(desktop.contains(tooltip)).toBe(false);
      expect(tooltip.getAttribute("data-side")).toBe("right");
      expect(tooltip.className).toContain("bg-neutral");
      expect(tooltip.className).toContain("text-neutral-content");
    });

    it("opens a collapsed row tooltip on hover after the shared delay", () => {
      vi.useFakeTimers();
      sidebarState.isOpen = false;
      const { container } = render(<Sidebar />);

      const docs = getDesktop(container).getByRole("link", { name: "Docs" });
      fireEvent.pointerMove(docs, { pointerType: "mouse" });
      expect(screen.queryByRole("tooltip")).toBeNull();
      act(() => vi.advanceTimersByTime(350));

      expect(screen.getByRole("tooltip").textContent).toBe("Docs");

      fireEvent.pointerLeave(docs, { pointerType: "mouse" });
      expect(screen.queryByRole("tooltip")).toBeNull();
    });

    it("labels the collapsed profile button and gives it a tooltip", () => {
      sidebarState.isOpen = false;
      const { container } = render(<Sidebar />);

      focus(getDesktop(container).getByRole("button", { name: "Open user profile" }));

      expect(screen.getByRole("tooltip").textContent).toBe("tester");
    });

    it("keeps row tooltips off while labels are visible", () => {
      const { container } = render(<Sidebar />);

      focus(getDesktop(container).getByRole("link", { name: "Home" }));

      expect(screen.queryByRole("tooltip")).toBeNull();
    });

    it("never shows rail tooltips inside the mobile drawer", () => {
      sidebarState.isOpen = false;
      sidebarState.isMobileOpen = true;
      const { container } = render(<Sidebar />);

      const { mobile } = getAsides(container);
      focus(within(mobile as HTMLElement).getByRole("link", { name: "Home" }));

      expect(screen.queryByRole("tooltip")).toBeNull();
    });

    it("explains the toggle in a tooltip and dismisses it once the rail toggles", () => {
      sidebarState.isOpen = false;
      const { container, rerender } = render(<Sidebar />);

      const expand = getDesktop(container).getByRole("button", { name: "Expand sidebar" });
      focus(expand);
      expect(screen.getByRole("tooltip").textContent).toBe("Expand sidebar");

      sidebarState.isOpen = true;
      rerender(<Sidebar />);

      expect(screen.queryByRole("tooltip")).toBeNull();
      // The toggle stays mounted, so keyboard focus survives the width change.
      expect(document.activeElement).toBe(
        getDesktop(container).getByRole("button", { name: "Collapse sidebar" }),
      );
    });

    it("holds tooltips back while the rail is still moving", () => {
      const now = vi.spyOn(performance, "now").mockReturnValue(1000);
      sidebarState.isOpen = false;
      const { container, rerender } = render(<Sidebar />);

      sidebarState.isOpen = true;
      rerender(<Sidebar />);
      sidebarState.isOpen = false;
      rerender(<Sidebar />);

      const expand = getDesktop(container).getByRole("button", { name: "Expand sidebar" });
      focus(expand);
      expect(screen.queryByRole("tooltip")).toBeNull();

      act(() => expand.blur());
      now.mockReturnValue(1000 + 240);
      focus(expand);
      expect(screen.getByRole("tooltip").textContent).toBe("Expand sidebar");
    });

    it("shows tooltips straight after a toggle when motion is reduced", () => {
      vi.spyOn(performance, "now").mockReturnValue(1000);
      vi.spyOn(window, "matchMedia").mockImplementation(
        (query: string) =>
          ({
            matches: query === "(prefers-reduced-motion: reduce)",
            media: query,
            addEventListener: () => undefined,
            removeEventListener: () => undefined,
          }) as unknown as MediaQueryList,
      );
      sidebarState.isOpen = true;
      const { container, rerender } = render(<Sidebar />);

      sidebarState.isOpen = false;
      rerender(<Sidebar />);

      focus(getDesktop(container).getByRole("button", { name: "Expand sidebar" }));
      expect(screen.getByRole("tooltip").textContent).toBe("Expand sidebar");
    });

    it("dismisses a stale row tooltip after navigation", () => {
      sidebarState.isOpen = false;
      const { container, rerender } = render(<Sidebar />);

      focus(getDesktop(container).getByRole("link", { name: "Metrics" }));
      expect(screen.getByRole("tooltip").textContent).toBe("Metrics");

      mockPathname.mockReturnValue("/metrics");
      rerender(<Sidebar />);

      expect(screen.queryByRole("tooltip")).toBeNull();
    });
  });

  describe("rail motion", () => {
    function getDesktopAside(container: HTMLElement) {
      return getAsides(container).desktop as HTMLElement;
    }

    function toggleRail(rerender: (ui: React.ReactElement) => void) {
      sidebarState.isOpen = !sidebarState.isOpen;
      rerender(<Sidebar />);
    }

    it("keeps rows, labels, headings, logo, and toggle mounted across rapid toggles", () => {
      const { container, rerender } = render(<Sidebar />);
      const desktop = getDesktopAside(container);
      const toggle = within(desktop).getByRole("button", { name: "Collapse sidebar" });
      const home = within(desktop).getByRole("link", { name: "Home" });
      const label = within(home).getByText("Home");
      const logo = desktop.querySelector('a[aria-label="QDash home"]');
      const heading = desktop.querySelector('[data-testid="sidebar-section-header"]');
      act(() => toggle.focus());

      for (let i = 0; i < 5; i += 1) toggleRail(rerender);

      // Odd number of toggles: the rail ends collapsed, with every node reused.
      expect(toggle.getAttribute("aria-label")).toBe("Expand sidebar");
      expect(document.activeElement).toBe(toggle);
      expect(desktop.contains(home) && home.contains(label)).toBe(true);
      expect(desktop.querySelector('a[aria-label="QDash home"]')).toBe(logo);
      expect(desktop.querySelector('[data-testid="sidebar-section-header"]')).toBe(heading);

      toggleRail(rerender);
      expect(toggle.getAttribute("aria-label")).toBe("Collapse sidebar");
      expect(document.activeElement).toBe(toggle);
    });

    it("fades labels and headings out while keeping the row names", () => {
      const { container, rerender } = render(<Sidebar />);
      const desktop = getDesktopAside(container);
      const label = within(desktop).getByText("Home");
      const heading = desktop.querySelector('[data-testid="sidebar-section-header"]');

      expect(label.className).toContain("opacity-100");
      expect(heading?.className).toContain("grid-rows-[1fr]");

      toggleRail(rerender);

      const home = within(desktop).getByRole("link", { name: "Home" });
      expect(home.hasAttribute("aria-label")).toBe(false);
      expect(home.textContent).toBe("Home");
      expect(label.className).toContain("opacity-0");
      expect(heading?.className).toContain("grid-rows-[0fr]");
      expect(heading?.getAttribute("data-state")).toBe("hidden");
    });

    it("names each section list by its heading in both rail states", () => {
      const { container, rerender } = render(<Sidebar />);
      const desktop = getDesktopAside(container);
      const overview = within(desktop).getByRole("list", { name: "Overview" });

      toggleRail(rerender);

      expect(within(desktop).getByRole("list", { name: "Overview" })).toBe(overview);
      for (const heading of desktop.querySelectorAll('[data-testid="sidebar-section-header"]')) {
        expect(heading.getAttribute("aria-hidden")).toBe("true");
      }
    });

    it("keeps the row geometry identical so icons hold their x position", () => {
      const { container, rerender } = render(<Sidebar />);
      const desktop = getDesktopAside(container);
      const home = within(desktop).getByRole("link", { name: "Home" });
      const expandedClass = home.className;

      toggleRail(rerender);

      expect(home.className).toBe(expandedClass);
      expect(home.className).toContain("px-2.75");
      expect(home.className).not.toContain("justify-center");
    });

    it("makes the hidden logo and profile details inert to focus and assistive tech", () => {
      sidebarState.isOpen = false;
      const { container } = render(<Sidebar />);
      const desktop = getDesktopAside(container);
      const logoSlot = desktop.querySelector('[data-testid="sidebar-desktop-logo"]');
      const details = desktop.querySelector('[data-testid="sidebar-profile-details"]');

      expect(logoSlot?.hasAttribute("inert")).toBe(true);
      expect(logoSlot?.getAttribute("aria-hidden")).toBe("true");
      expect(within(desktop).queryByRole("link", { name: "QDash home" })).toBeNull();
      expect(details?.getAttribute("aria-hidden")).toBe("true");
      expect(within(desktop).getAllByRole("button", { name: "Open user profile" })).toHaveLength(1);
    });

    it("keeps the profile avatar one size across rail states", () => {
      const { container, rerender } = render(<Sidebar />);
      const desktop = getDesktopAside(container);
      const avatarWidth = () => desktop.querySelector("button img")?.getAttribute("width");
      const expanded = avatarWidth();

      toggleRail(rerender);

      expect(expanded).toBe("32");
      expect(avatarWidth()).toBe(expanded);
    });

    it("coordinates rail geometry and drops all motion when reduced", () => {
      const { container } = render(<Sidebar />);
      const desktop = getDesktopAside(container);
      const header = desktop.querySelector('[data-testid="sidebar-desktop-header"]');
      const heading = desktop.querySelector('[data-testid="sidebar-section-header"]');
      const geometry = [desktop, header, heading];

      for (const element of geometry) {
        expect(element?.className).toContain("duration-[240ms]");
        expect(element?.className).toContain("ease-[cubic-bezier(0.2,0,0,1)]");
        expect(element?.className).toContain("motion-reduce:transition-none");
      }
      const faded = [
        within(desktop).getByText("Home"),
        desktop.querySelector('[data-testid="sidebar-desktop-logo"]'),
        desktop.querySelector('[data-testid="sidebar-profile-details"]'),
      ];
      for (const element of faded) {
        expect(element?.className).toContain("transition-opacity");
        expect(element?.className).toContain("motion-reduce:transition-none");
        expect(element?.className).toContain("motion-reduce:delay-0");
      }
    });

    it("pins the active pill with insets so it tracks the rail width", () => {
      const { container } = render(<Sidebar />);
      const { indicator } = getSectionIndicator(getDesktopAside(container), "/dashboard");
      const style = (indicator as HTMLElement).style;

      expect(style.left).not.toBe("");
      expect(style.right).not.toBe("");
      expect(style.width).toBe("");
      expect(style.transform).toMatch(/^translateY\(/);
    });

    it("reveals the active row after the rail settles, not when it toggles", () => {
      const scroll = vi.spyOn(HTMLElement.prototype, "scrollIntoView");
      const { container, rerender } = render(<Sidebar />);
      const nav = getDesktopAside(container).querySelector("nav") as HTMLElement;
      scroll.mockClear();

      toggleRail(rerender);
      expect(scroll).not.toHaveBeenCalled();

      const opacityEnd = new Event("transitionend", { bubbles: true });
      Object.defineProperty(opacityEnd, "propertyName", { value: "opacity" });
      nav.querySelector("li a span")?.dispatchEvent(opacityEnd);
      expect(scroll).not.toHaveBeenCalled();

      const settled = new Event("transitionend", { bubbles: true });
      Object.defineProperty(settled, "propertyName", { value: "grid-template-rows" });
      nav.querySelector('[data-testid="sidebar-section-header"]')?.dispatchEvent(settled);
      expect(scroll).toHaveBeenCalledTimes(1);
      expect(scroll.mock.contexts[0]).toBe(within(nav).getByRole("link", { name: "Dashboard" }));
    });

    it("still reveals the active row on navigation", () => {
      const scroll = vi.spyOn(HTMLElement.prototype, "scrollIntoView");
      const { rerender } = render(<Sidebar />);
      scroll.mockClear();

      mockPathname.mockReturnValue("/metrics");
      rerender(<Sidebar />);

      expect(scroll).toHaveBeenCalledWith({ block: "nearest" });
    });
  });
});
