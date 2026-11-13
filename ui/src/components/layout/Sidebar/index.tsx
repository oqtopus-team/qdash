"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { ReactElement, ReactNode } from "react";

import {
  BookOpen,
  LogOut,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Sun,
  Workflow,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { useTheme } from "@/contexts/ThemeContext";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { useSidebar } from "@/contexts/SidebarContext";
import { DARK_THEMES } from "@/constants/themes";
import { getNavigationSections } from "@/components/layout/navigation";
import type { NavItem, NavSection } from "@/components/layout/navigation";

/**
 * Controlled open state for one rail tooltip. `open` is already false whenever
 * the tooltip is disabled (expanded rail, mobile drawer) or its context is stale.
 */
type RailTooltipControl = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/**
 * Rail motion. Width, the header padding, and the section-heading heights share one
 * duration and curve so the rail reads as a single movement; reversing mid-flight
 * simply retargets the CSS transitions. Reduced motion drops every transition.
 */
const RAIL_MOTION_MS = 240;
const RAIL_GEOMETRY_MOTION =
  "duration-[240ms] ease-[cubic-bezier(0.2,0,0,1)] motion-reduce:transition-none";

/**
 * Fade for content that only fits the expanded rail (labels, logo, headings). It
 * leaves quickly before the rail narrows, and returns after the rail has started
 * to widen so text never appears squeezed. The element stays mounted either way.
 */
function railFadeClass(visible: boolean): string {
  return `transition-opacity ease-out motion-reduce:transition-none motion-reduce:delay-0 ${
    visible ? "opacity-100 duration-[160ms] delay-[80ms]" : "opacity-0 duration-[100ms] delay-0"
  }`;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true
  );
}

/** Scrolls the current route's row into view only when it is clipped. */
function revealActiveRow(navigation: HTMLElement | null) {
  navigation?.querySelector('[aria-current="page"]')?.scrollIntoView({ block: "nearest" });
}

/** Compact, high-contrast label shown to the right of an icon-only rail control. */
const RAIL_TOOLTIP_CLASS =
  "border-neutral bg-neutral px-2 py-1 text-xs font-medium text-neutral-content shadow-md";

/**
 * Wraps one sidebar control in a right-side tooltip. The trigger is always
 * rendered through the tooltip, even while it stays closed, so toggling the rail
 * does not remount the control and drop its keyboard focus. The content is
 * portalled, so the scrolling nav cannot clip it.
 */
function RailTooltip({
  label,
  control,
  children,
}: {
  label: string;
  control: RailTooltipControl;
  children: ReactElement;
}) {
  return (
    <Tooltip open={control.open} onOpenChange={control.onOpenChange} disableHoverableContent>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="right" sideOffset={8} className={RAIL_TOOLTIP_CLASS}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

type ExternalNavItem = {
  href: string;
  label: string;
  title?: string;
  icon: LucideIcon;
  visible?: boolean;
};

/**
 * QDash home link shared by the desktop rail and the mobile drawer header: the
 * OQTOPUS mark beside the product name. Its left inset matches the nav rows below
 * so the mark lines up with their icons. `min-w-max` keeps the mark and name at
 * full size while the collapsing rail clips them, instead of squeezing them.
 */
function SidebarLogo({ onClick }: { onClick: () => void }) {
  return (
    <Link
      href="/"
      className="mx-1 flex min-w-max flex-1 items-center gap-2 rounded-lg px-3 py-1"
      aria-label="QDash home"
      onClick={onClick}
    >
      <Image
        src="/oqtopus_logo.png"
        alt=""
        width={36}
        height={36}
        className="h-9 w-9 shrink-0 object-contain"
        priority
      />
      <span className="truncate text-lg font-semibold tracking-tight text-base-content">QDash</span>
    </Link>
  );
}

/**
 * Navigation section label. It stays mounted on the icon-only rail, where its row
 * collapses to zero height in step with the rail width and the text fades, so the
 * rows below glide up instead of jumping. The list is named by this label through
 * `aria-labelledby`, so the label itself is hidden from assistive technology and
 * the name stays the same in both rail states.
 */
function SectionHeader({ id, label, visible }: { id: string; label: string; visible: boolean }) {
  return (
    <div
      aria-hidden="true"
      data-testid="sidebar-section-header"
      data-state={visible ? "visible" : "hidden"}
      className={`grid transition-[grid-template-rows] ${RAIL_GEOMETRY_MOTION} ${
        visible ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
      }`}
    >
      <div className="min-h-0 overflow-hidden">
        <div
          id={id}
          className={`menu-title whitespace-nowrap px-5 pb-2 pt-5 text-xs font-medium text-base-content/50 ${railFadeClass(visible)}`}
        >
          {label}
        </div>
      </div>
    </div>
  );
}

// Rows fill the rail width (no wrapping), so they track it while it animates.
const MENU_CLASS = "menu w-full flex-nowrap [&>li]:flex-nowrap p-2 py-0";

/** Resolves whether `item` owns the current route, honouring its `match` mode. */
function isNavItemActive(item: NavItem, pathname: string): boolean {
  return item.match === "prefix" ? pathname.startsWith(item.href) : pathname === item.href;
}

type IndicatorPlacement = {
  top: number;
  /** Horizontal insets from the section edges, so the pill follows a resizing rail in CSS. */
  left: number;
  right: number;
  height: number;
  /** False once the active route has left this section; the pill fades out in place. */
  visible: boolean;
  /**
   * True only when the pill was already showing in this section, so a move to a
   * sibling row slides. Entering a section from elsewhere snaps into place and
   * fades in instead, which keeps every slide short.
   */
  slide: boolean;
};

/**
 * Every section mounts its pill hidden at zero size, so the first time a section
 * becomes active the pill already exists and its opacity can transition in.
 */
const HIDDEN_PLACEMENT: IndicatorPlacement = {
  top: 0,
  left: 0,
  right: 0,
  height: 0,
  visible: false,
  slide: false,
};

/**
 * One navigation section with a single shared active-row highlight. The highlight
 * is an absolutely positioned pill measured against the active link, so it can
 * animate between rows: it slides within the section and fades when the active
 * route crosses into another section. Row text colour still changes per link.
 */
function SidebarNavSection({
  label,
  headerVisible,
  activeHref,
  layoutKey,
  children,
}: {
  label: string;
  headerVisible: boolean;
  activeHref: string | null;
  /** Changes whenever the rail geometry changes, so the pill is re-measured. */
  layoutKey: string;
  children: ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const headerId = useId();
  const previousHrefRef = useRef<string | null>(activeHref);
  const [placement, setPlacement] = useState<IndicatorPlacement>(HIDDEN_PLACEMENT);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const measure = (allowSlide: boolean) => {
      const active = container.querySelector<HTMLElement>('a[aria-current="page"]');
      setPlacement((previous) => {
        if (!active) {
          return previous.visible ? { ...previous, visible: false, slide: false } : previous;
        }
        const containerRect = container.getBoundingClientRect();
        const rect = active.getBoundingClientRect();
        const box = {
          top: rect.top - containerRect.top,
          left: rect.left - containerRect.left,
          right: containerRect.right - rect.right,
          height: rect.height,
        };
        // A re-measure that lands on the same box (such as the ResizeObserver's
        // initial notification) must not touch `slide`, or it would cut short a
        // slide that is still in flight.
        const sameBox = (Object.keys(box) as (keyof typeof box)[]).every(
          (key) => previous[key] === box[key],
        );
        if (sameBox && previous.visible) return previous;
        return { ...box, visible: true, slide: allowSlide && previous.visible };
      });
    };

    // Only a route change inside the section may slide; geometry changes
    // (expand/collapse, font load, row visibility) reposition instantly.
    const hrefChanged = previousHrefRef.current !== activeHref;
    previousHrefRef.current = activeHref;
    measure(hrefChanged);

    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => measure(false));
    observer.observe(container);
    return () => observer.disconnect();
  }, [activeHref, layoutKey]);

  // The heading sits outside the measured container, so its height animation moves
  // the rows and their pill together without re-measuring every frame.
  return (
    <div>
      <SectionHeader id={headerId} visible={headerVisible} label={label} />
      <div ref={containerRef} className="relative">
        <span
          aria-hidden="true"
          data-testid="sidebar-active-indicator"
          data-state={placement.visible ? "visible" : "hidden"}
          data-motion={placement.slide ? "slide" : "fade"}
          className={`pointer-events-none absolute top-0 rounded-lg bg-primary/12 duration-200 ease-out motion-reduce:transition-none before:absolute before:inset-y-2 before:left-0 before:w-1 before:rounded-r-full before:bg-primary ${
            placement.slide ? "transition-[transform,height,opacity]" : "transition-opacity"
          }`}
          style={{
            transform: `translateY(${placement.top}px)`,
            left: placement.left,
            right: placement.right,
            height: placement.height,
            opacity: placement.visible ? 1 : 0,
          }}
        />
        <ul className={`${MENU_CLASS} relative`} aria-labelledby={headerId}>
          {children}
        </ul>
      </div>
    </div>
  );
}

/**
 * One in-app navigation row. Marks itself active from `pathname` (exact or
 * prefix match per `item.match`), truncates its label so a long entry cannot
 * widen the row, and closes the mobile drawer through `onClick`. The label stays
 * mounted on the collapsed rail, faded and clipped, so it still names the link.
 * The active background is drawn by the enclosing `SidebarNavSection`.
 */
function SidebarNavItem({
  item,
  isMobileOpen,
  isOpen,
  pathname,
  linkClass,
  desktopLinkClass,
  tooltip,
  onClick,
}: {
  item: NavItem;
  isMobileOpen: boolean;
  isOpen: boolean;
  pathname: string;
  linkClass: (active: boolean) => string;
  desktopLinkClass: (active: boolean) => string;
  tooltip: RailTooltipControl;
  onClick: () => void;
}) {
  const Icon = item.icon;
  const active = isNavItemActive(item, pathname);
  const showLabel = isOpen || isMobileOpen;

  return (
    <li>
      <RailTooltip label={item.title ?? item.label} control={tooltip}>
        <Link
          href={item.href}
          className={isMobileOpen ? linkClass(active) : desktopLinkClass(active)}
          aria-current={active ? "page" : undefined}
          onClick={onClick}
        >
          <Icon size={18} className="shrink-0" aria-hidden="true" />
          <span className={`ml-2 truncate ${railFadeClass(showLabel)}`}>{item.label}</span>
        </Link>
      </RailTooltip>
    </li>
  );
}

/**
 * One external-link navigation row (Docs, Prefect). Opens in a new tab
 * and is never marked active, since the current route never matches it.
 */
function SidebarExternalNavItem({
  item,
  isMobileOpen,
  isOpen,
  linkClass,
  desktopLinkClass,
  tooltip,
  onClick,
}: {
  item: ExternalNavItem;
  isMobileOpen: boolean;
  isOpen: boolean;
  linkClass: (active: boolean) => string;
  desktopLinkClass: (active: boolean) => string;
  tooltip: RailTooltipControl;
  onClick: () => void;
}) {
  const Icon = item.icon;
  const showLabel = isOpen || isMobileOpen;

  return (
    <li>
      <RailTooltip label={item.title ?? item.label} control={tooltip}>
        <a
          href={item.href}
          target="_blank"
          rel="noopener noreferrer"
          className={isMobileOpen ? linkClass(false) : desktopLinkClass(false)}
          onClick={onClick}
        >
          <Icon size={18} className="shrink-0" aria-hidden="true" />
          <span className={`ml-2 truncate ${railFadeClass(showLabel)}`}>{item.label}</span>
        </a>
      </RailTooltip>
    </li>
  );
}

/**
 * Primary navigation, rendered as two asides sharing one set of nav rows:
 * a desktop rail that expands to `w-48` and collapses to `w-16`, and a mobile
 * drawer (`w-56`) that slides in over an overlay and closes on navigation.
 */
export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [profileOpen, setProfileOpen] = useState(false);
  const [logoutPending, setLogoutPending] = useState(false);
  const desktopNavRef = useRef<HTMLElement>(null);
  const mobileNavRef = useRef<HTMLElement>(null);
  const desktopSidebarId = useId();
  const { isOpen, isMobileOpen, toggleSidebar, setMobileSidebarOpen } = useSidebar();
  const [openTooltip, setOpenTooltip] = useState<{ id: string; context: string } | null>(null);
  // Until this timestamp the rail is still moving, so tooltips must not attach to
  // controls that are sliding under the pointer. A deadline, not a timer.
  const railMotionUntilRef = useRef(0);
  const previousIsOpenRef = useRef(isOpen);
  const { canEdit } = useProject();
  const { user, logout: authLogout } = useAuth();
  const { theme, setTheme } = useTheme();
  const isAdmin = user?.system_role === "admin";
  const isDarkTheme = DARK_THEMES.includes(theme as (typeof DARK_THEMES)[number]);

  // Navigation and opening the drawer reveal the current row straight away.
  useEffect(() => {
    revealActiveRow(isMobileOpen ? mobileNavRef.current : desktopNavRef.current);
  }, [pathname, isMobileOpen]);

  // A rail toggle reveals the current row only once the section headings have
  // settled, so the nav never scrolls against a layout that is still moving.
  useEffect(() => {
    const navigation = desktopNavRef.current;
    if (!navigation) return;
    const handleTransitionEnd = (event: TransitionEvent) => {
      if (event.propertyName === "grid-template-rows") revealActiveRow(navigation);
    };
    navigation.addEventListener("transitionend", handleTransitionEnd);
    return () => navigation.removeEventListener("transitionend", handleTransitionEnd);
  }, []);

  useEffect(() => {
    if (previousIsOpenRef.current === isOpen) return;
    previousIsOpenRef.current = isOpen;
    if (prefersReducedMotion()) {
      // No transitions run, so the final layout is already in place.
      railMotionUntilRef.current = 0;
      revealActiveRow(desktopNavRef.current);
      return;
    }
    railMotionUntilRef.current = performance.now() + RAIL_MOTION_MS;
  }, [isOpen]);

  const handleLogout = useCallback(async () => {
    await authLogout();
  }, [authLogout]);

  const openProfileModal = useCallback(() => {
    setProfileOpen(true);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(isDarkTheme ? "light" : "dark");
  }, [isDarkTheme, setTheme]);

  const handleSettingsClick = useCallback(() => {
    setProfileOpen(false);
    if (isMobileOpen) {
      setMobileSidebarOpen(false);
    }
    router.push("/settings");
  }, [isMobileOpen, setMobileSidebarOpen, router]);

  const handleModalLogout = useCallback(async () => {
    setLogoutPending(true);
    try {
      await handleLogout();
      setProfileOpen(false);
    } finally {
      setLogoutPending(false);
    }
  }, [handleLogout]);

  // A tooltip opened under another route, rail width, or dialog state is stale:
  // it no longer describes what the pointer or focus is on, so it reads as closed.
  const tooltipContext = `${pathname}|${isOpen}|${isMobileOpen}|${profileOpen}`;
  const railTooltip = (id: string, enabled: boolean): RailTooltipControl => ({
    open: enabled && openTooltip?.id === id && openTooltip.context === tooltipContext,
    onOpenChange: (open) => {
      if (open && performance.now() < railMotionUntilRef.current) return;
      setOpenTooltip((current) => {
        if (open) return enabled ? { id, context: tooltipContext } : current;
        return current?.id === id ? null : current;
      });
    },
  });
  // Labels are hidden only on the collapsed desktop rail, so only it needs tooltips.
  const desktopRailTooltips = !isOpen && !isMobileOpen;

  // Close mobile sidebar when clicking a link
  const handleLinkClick = () => {
    if (isMobileOpen) {
      setMobileSidebarOpen(false);
    }
  };

  // Mobile sidebar style
  const linkClass = (active: boolean) =>
    `relative min-h-9 px-3 mx-1 my-0.5 text-sm font-medium flex items-center rounded-lg transition-colors ${
      active ? "text-primary" : "text-base-content/75 hover:bg-base-300 hover:text-base-content"
    }`;

  // Desktop sidebar style
  // One geometry for both rail states: the row spans the rail minus 12px a side
  // (40px on the 64px rail), and its 11px inset centres the 18px icon on the rail
  // at x = 32px whether the rail is open, closed, or moving between the two.
  const desktopLinkClass = (active: boolean) =>
    `relative min-h-9 px-2.75 mx-1 my-0.5 text-sm font-medium flex items-center rounded-lg transition-colors ${
      active ? "text-primary" : "text-base-content/75 hover:bg-base-300 hover:text-base-content"
    }`;

  const sectionHeaderVisible = isOpen || isMobileOpen;
  const indicatorLayoutKey = `${isOpen}:${isMobileOpen}`;
  const navSections: NavSection[] = getNavigationSections({ canEdit, isAdmin });
  const externalItems: ExternalNavItem[] = [
    {
      href: "https://oqtopus-team.github.io/qdash/",
      label: "Docs",
      icon: BookOpen,
    },
    {
      href: "/prefect/dashboard",
      label: "Prefect",
      title: "Prefect",
      icon: Workflow,
      visible: canEdit,
    },
  ];

  // The stack follows the rail width, so every row resizes with it; `min-w-16` keeps
  // the icon column intact if a classic scrollbar narrows the collapsed nav.
  const renderSidebarContent = (railTooltips: boolean) => (
    <div className="flex w-full min-w-16 flex-col">
      {navSections.map((section) => {
        const visibleItems = section.items.filter((item) => item.visible !== false);
        if (visibleItems.length === 0) return null;
        const activeHref =
          visibleItems.find((item) => isNavItemActive(item, pathname))?.href ?? null;

        return (
          <SidebarNavSection
            key={section.label}
            label={section.label}
            headerVisible={sectionHeaderVisible}
            activeHref={activeHref}
            layoutKey={indicatorLayoutKey}
          >
            {visibleItems.map((item) => (
              <SidebarNavItem
                key={item.href}
                item={item}
                isMobileOpen={isMobileOpen}
                isOpen={isOpen}
                pathname={pathname}
                linkClass={linkClass}
                desktopLinkClass={desktopLinkClass}
                tooltip={railTooltip(`nav:${item.href}`, railTooltips)}
                onClick={handleLinkClick}
              />
            ))}
          </SidebarNavSection>
        );
      })}

      <ul className={MENU_CLASS}>
        <div className={`divider ${isMobileOpen ? "my-1" : "my-0"}`} />
        {externalItems
          .filter((item) => item.visible !== false)
          .map((item) => (
            <SidebarExternalNavItem
              key={item.href}
              item={item}
              isMobileOpen={isMobileOpen}
              isOpen={isOpen}
              linkClass={linkClass}
              desktopLinkClass={desktopLinkClass}
              tooltip={railTooltip(`external:${item.href}`, railTooltips)}
              onClick={handleLinkClick}
            />
          ))}
      </ul>
    </div>
  );

  // The desktop profile keeps one layout in both rail states: a 32px avatar centred
  // on the icon column, with its details clipped and faded rather than unmounted.
  const profileDetailsVisible = isOpen || isMobileOpen;
  const renderUserSection = (railTooltips: boolean) => (
    <div className={`border-t border-base-300 ${isMobileOpen ? "p-2" : "mx-2 py-2"}`}>
      <RailTooltip
        label={user?.username || "User profile"}
        control={railTooltip("profile", railTooltips)}
      >
        <button
          type="button"
          onClick={openProfileModal}
          aria-label={profileDetailsVisible ? undefined : "Open user profile"}
          className={`btn btn-ghost h-auto w-full justify-start gap-3 py-2 ${
            isMobileOpen ? "" : "flex-nowrap overflow-hidden px-2"
          }`}
        >
          <div className="flex shrink-0 items-center justify-center">
            <UserAvatar
              username={user?.username || ""}
              size={isMobileOpen ? 28 : 32}
              showTitle={false}
            />
          </div>
          <div
            aria-hidden={profileDetailsVisible ? undefined : true}
            data-testid="sidebar-profile-details"
            className={`min-w-0 flex-1 text-left ${railFadeClass(profileDetailsVisible)}`}
          >
            <div className="text-sm font-medium truncate">{user?.username || "User"}</div>
            <div className="text-xs opacity-60 truncate">{user?.display_name || ""}</div>
            {user?.system_role && (
              <div className="mt-0.5">
                <span
                  className={`badge badge-xs ${user.system_role === "admin" ? "badge-primary" : "badge-ghost"}`}
                >
                  {user.system_role}
                </span>
              </div>
            )}
          </div>
        </button>
      </RailTooltip>
    </div>
  );

  const userModal = (
    <Dialog
      open={profileOpen}
      onOpenChange={(open) => !open && !logoutPending && setProfileOpen(false)}
    >
      <DialogContent className="max-sm:top-auto max-sm:bottom-0 max-sm:translate-y-0 max-sm:rounded-b-none sm:w-96 sm:max-w-sm">
        <DialogTitle className="sr-only">User profile</DialogTitle>
        <DialogDescription className="sr-only">
          Manage theme, account settings, and sign out.
        </DialogDescription>
        {/* Profile Section */}
        <div className="flex flex-col items-center py-4 border-b border-base-300">
          <div className="mb-3">
            <UserAvatar username={user?.username || ""} size={64} />
          </div>
          <h2 className="text-sm font-medium">{user?.username}</h2>
          {user?.display_name && (
            <p className="text-sm text-base-content/60">{user?.display_name}</p>
          )}
          {user?.system_role && (
            <span
              className={`badge badge-sm mt-2 ${user.system_role === "admin" ? "badge-primary" : "badge-ghost"}`}
            >
              {user.system_role}
            </span>
          )}
        </div>

        {/* Menu Section */}
        <div className="py-2">
          {/* Theme Toggle */}
          <label className="flex items-center justify-between w-full px-4 h-12 cursor-pointer hover:bg-base-200 rounded-lg">
            <div className="flex items-center gap-3">
              {isDarkTheme ? <Moon size={18} /> : <Sun size={18} />}
              <span>Dark Mode</span>
            </div>
            <input
              id="sidebar-dark-mode-toggle"
              name="darkMode"
              type="checkbox"
              className="toggle toggle-sm"
              checked={isDarkTheme}
              aria-label="Dark Mode"
              onChange={toggleTheme}
            />
          </label>

          {/* Settings Link */}
          <button
            type="button"
            onClick={handleSettingsClick}
            className="btn btn-ghost w-full justify-start gap-3 h-12"
          >
            <Settings size={18} />
            <span>Settings</span>
          </button>

          {/* Logout */}
          <button
            type="button"
            onClick={handleModalLogout}
            className="btn btn-ghost w-full justify-start gap-3 h-12 text-error"
            disabled={logoutPending}
          >
            <LogOut size={18} />
            <span>{logoutPending ? "Logging out…" : "Logout"}</span>
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );

  return (
    <>
      {/* Desktop Sidebar */}
      <aside
        id={desktopSidebarId}
        aria-label="Primary navigation"
        className={`hidden h-full shrink-0 overflow-hidden border-r border-base-300 bg-base-200 transition-[width] ${RAIL_GEOMETRY_MOTION} lg:flex lg:flex-col ${
          isOpen ? "w-48" : "w-16"
        }`}
      >
        {/* The logo stays mounted and is clipped by its shrinking slot; `inert` takes it
            out of the tab order and the accessibility tree while the rail is closed. The
            right padding eases to 16px so the toggle lands centred on the 64px rail. */}
        <div
          data-testid="sidebar-desktop-header"
          className={`flex h-16 flex-shrink-0 items-center pl-2 transition-[padding] ${RAIL_GEOMETRY_MOTION} ${
            isOpen ? "pr-2" : "pr-4"
          }`}
        >
          <div
            data-testid="sidebar-desktop-logo"
            inert={!isOpen}
            aria-hidden={isOpen ? undefined : true}
            className={`min-w-0 flex-1 overflow-hidden py-1 ${railFadeClass(isOpen)}`}
          >
            <SidebarLogo onClick={handleLinkClick} />
          </div>
          <RailTooltip
            label={isOpen ? "Collapse sidebar" : "Expand sidebar"}
            control={railTooltip("toggle", !isMobileOpen)}
          >
            <button
              type="button"
              onClick={toggleSidebar}
              className="btn btn-ghost btn-sm btn-square shrink-0 text-base-content/70 hover:text-base-content"
              aria-label={isOpen ? "Collapse sidebar" : "Expand sidebar"}
              aria-expanded={isOpen}
              aria-controls={desktopSidebarId}
            >
              {isOpen ? (
                <PanelLeftClose size={18} aria-hidden="true" />
              ) : (
                <PanelLeftOpen size={18} aria-hidden="true" />
              )}
            </button>
          </RailTooltip>
        </div>
        <nav
          ref={desktopNavRef}
          className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-contain"
        >
          {renderSidebarContent(desktopRailTooltips)}
        </nav>
        {renderUserSection(desktopRailTooltips)}
      </aside>

      {/* Mobile Sidebar Overlay */}
      {isMobileOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          aria-label="Close navigation menu"
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}

      {/* Mobile Sidebar Drawer */}
      <aside
        aria-label="Primary navigation"
        className={`fixed left-0 top-0 z-50 flex h-full w-56 flex-col border-r border-base-300 bg-base-200 shadow-2xl transition-transform duration-300 lg:hidden ${
          isMobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-16 flex-shrink-0 items-center gap-1 px-2">
          <SidebarLogo onClick={handleLinkClick} />
          <button
            onClick={() => setMobileSidebarOpen(false)}
            className="btn btn-ghost btn-sm btn-square"
            aria-label="Close menu"
          >
            <X size={20} />
          </button>
        </div>
        <nav ref={mobileNavRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          {renderSidebarContent(false)}
        </nav>
        {renderUserSection(false)}
      </aside>

      {/* User Modal - Rendered outside sidebar for proper z-index stacking */}
      {userModal}
    </>
  );
}
