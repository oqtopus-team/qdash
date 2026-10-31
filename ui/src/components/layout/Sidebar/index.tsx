"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  FileJson2,
  LogOut,
  Moon,
  Settings,
  Sun,
  Workflow,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { useTheme } from "@/contexts/ThemeContext";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { useSidebar } from "@/contexts/SidebarContext";
import { DARK_THEMES } from "@/constants/themes";
import { getNavigationSections } from "@/components/layout/navigation";
import type { NavItem, NavSection } from "@/components/layout/navigation";

const PREFECT_URL = process.env.NEXT_PUBLIC_PREFECT_URL || "http://127.0.0.1:4200";

type ExternalNavItem = {
  href: string;
  label: string;
  title?: string;
  icon: LucideIcon;
  visible?: boolean;
};

/**
 * QDash home link shared by both sidebars.
 * `lg` is the in-nav logo on the expanded desktop rail; `sm` is the compact one
 * that sits beside the close button in the mobile drawer header.
 */
function SidebarLogo({ size, onClick }: { size: "sm" | "lg"; onClick: () => void }) {
  const isLarge = size === "lg";

  return (
    <Link
      href="/"
      className={`flex items-center justify-center rounded-xl ${isLarge ? "min-h-16" : ""}`}
      aria-label="QDash home"
      onClick={onClick}
    >
      <Image
        src="/oqtopus_logo.png"
        alt="Oqtopus Logo"
        width={72}
        height={72}
        className={`object-contain ${isLarge ? "h-16 w-16" : "h-10 w-10"}`}
        priority
      />
    </Link>
  );
}

/**
 * Renders a navigation section label, or nothing while the sidebar is collapsed
 * to the icon-only desktop rail and there is no room for one.
 */
function SectionHeader({ label, visible }: { label: string; visible: boolean }) {
  if (!visible) return null;
  return (
    <li className="menu-title px-3 pb-2 pt-5 text-xs font-medium text-base-content/50">{label}</li>
  );
}

const MENU_CLASS = "menu w-full max-lg:flex-nowrap max-lg:[&>li]:flex-nowrap p-2 py-0";

/** Resolves whether `item` owns the current route, honouring its `match` mode. */
function isNavItemActive(item: NavItem, pathname: string): boolean {
  return item.match === "prefix" ? pathname.startsWith(item.href) : pathname === item.href;
}

type IndicatorPlacement = {
  top: number;
  left: number;
  width: number;
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
  width: 0,
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
          width: rect.width,
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

  return (
    <div ref={containerRef} className="relative">
      <span
        aria-hidden="true"
        data-testid="sidebar-active-indicator"
        data-state={placement.visible ? "visible" : "hidden"}
        data-motion={placement.slide ? "slide" : "fade"}
        className={`pointer-events-none absolute left-0 top-0 rounded-lg bg-primary/12 duration-200 ease-out motion-reduce:transition-none before:absolute before:inset-y-2 before:left-0 before:w-1 before:rounded-r-full before:bg-primary ${
          placement.slide ? "transition-[transform,width,height,opacity]" : "transition-opacity"
        }`}
        style={{
          transform: `translate(${placement.left}px, ${placement.top}px)`,
          width: placement.width,
          height: placement.height,
          opacity: placement.visible ? 1 : 0,
        }}
      />
      <ul className={`${MENU_CLASS} relative`}>
        <SectionHeader visible={headerVisible} label={label} />
        {children}
      </ul>
    </div>
  );
}

/**
 * One in-app navigation row. Marks itself active from `pathname` (exact or
 * prefix match per `item.match`), truncates its label so a long entry cannot
 * widen the row, and closes the mobile drawer through `onClick`. The active
 * background is drawn by the enclosing `SidebarNavSection`, not by the row.
 */
function SidebarNavItem({
  item,
  isMobileOpen,
  isOpen,
  pathname,
  linkClass,
  desktopLinkClass,
  onClick,
}: {
  item: NavItem;
  isMobileOpen: boolean;
  isOpen: boolean;
  pathname: string;
  linkClass: (active: boolean) => string;
  desktopLinkClass: (active: boolean) => string;
  onClick: () => void;
}) {
  const Icon = item.icon;
  const active = isNavItemActive(item, pathname);
  const showLabel = isOpen || isMobileOpen;

  return (
    <li>
      <Link
        href={item.href}
        className={isMobileOpen ? linkClass(active) : desktopLinkClass(active)}
        title={item.title ?? item.label}
        aria-current={active ? "page" : undefined}
        onClick={onClick}
      >
        <Icon size={18} />
        {showLabel && <span className="ml-2 truncate">{item.label}</span>}
      </Link>
    </li>
  );
}

/**
 * One external-link navigation row (Docs, Prefect, API Docs). Opens in a new tab
 * and is never marked active, since the current route never matches it.
 */
function SidebarExternalNavItem({
  item,
  isMobileOpen,
  isOpen,
  linkClass,
  desktopLinkClass,
  onClick,
}: {
  item: ExternalNavItem;
  isMobileOpen: boolean;
  isOpen: boolean;
  linkClass: (active: boolean) => string;
  desktopLinkClass: (active: boolean) => string;
  onClick: () => void;
}) {
  const Icon = item.icon;

  return (
    <li>
      <a
        href={item.href}
        target="_blank"
        rel="noopener noreferrer"
        className={isMobileOpen ? linkClass(false) : desktopLinkClass(false)}
        title={item.title ?? item.label}
        onClick={onClick}
      >
        <Icon size={18} />
        {(isOpen || isMobileOpen) && <span className="ml-2 truncate">{item.label}</span>}
      </a>
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
  const { isOpen, isMobileOpen, toggleSidebar, setMobileSidebarOpen } = useSidebar();
  const { canEdit } = useProject();
  const { user, logout: authLogout } = useAuth();
  const { theme, setTheme } = useTheme();
  const isAdmin = user?.system_role === "admin";
  const isDarkTheme = DARK_THEMES.includes(theme as (typeof DARK_THEMES)[number]);

  useEffect(() => {
    const navigation = isMobileOpen ? mobileNavRef.current : desktopNavRef.current;
    navigation?.querySelector('[aria-current="page"]')?.scrollIntoView({ block: "nearest" });
  }, [pathname, isOpen, isMobileOpen]);

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
  const desktopLinkClass = (active: boolean) =>
    `relative min-h-9 ${isOpen ? "px-3 mx-1" : "px-2 mx-1 justify-center"} my-0.5 text-sm font-medium flex items-center rounded-lg transition-colors ${
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
      href: `${PREFECT_URL}/dashboard`,
      label: "Prefect",
      title: "Prefect",
      icon: Workflow,
      visible: canEdit,
    },
    {
      href: "/api/docs",
      label: "API Docs",
      icon: FileJson2,
      visible: canEdit,
    },
  ];

  // `w-fit` keeps the stacked section lists as wide as the widest row, matching
  // the single fit-content menu they replaced; the drawer stretches them instead.
  const sidebarContent = (
    <div className="flex w-fit flex-col max-lg:w-full">
      {isOpen && (
        <ul className={MENU_CLASS}>
          <li className="mb-1 hidden lg:block">
            <SidebarLogo size="lg" onClick={handleLinkClick} />
          </li>
        </ul>
      )}

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
              onClick={handleLinkClick}
            />
          ))}
      </ul>
    </div>
  );

  const userSection = (
    <div
      className={`border-t border-base-300 ${isMobileOpen ? "p-2" : isOpen ? "p-2 mx-2" : "p-1"}`}
    >
      <button
        onClick={openProfileModal}
        className={`btn btn-ghost w-full ${isOpen || isMobileOpen ? "justify-start gap-3" : "justify-center p-0"} h-auto py-2`}
      >
        <div className="flex items-center justify-center">
          <UserAvatar
            username={user?.username || ""}
            avatarKey={user?.avatar_key}
            size={isOpen || isMobileOpen ? 28 : 40}
          />
        </div>
        {(isOpen || isMobileOpen) && (
          <div className="flex-1 text-left min-w-0">
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
        )}
      </button>
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
            <UserAvatar username={user?.username || ""} avatarKey={user?.avatar_key} size={64} />
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
        aria-label="Primary navigation"
        className={`hidden h-full border-r border-base-300 bg-base-200 transition-colors duration-300 lg:flex lg:flex-col ${
          isOpen ? "w-48" : "w-16"
        }`}
      >
        <div className="flex flex-shrink-0 justify-end p-2 pb-0">
          <button
            onClick={toggleSidebar}
            className="btn btn-ghost btn-sm btn-square"
            aria-label={isOpen ? "Collapse sidebar" : "Expand sidebar"}
          >
            {isOpen ? <ChevronLeft size={20} /> : <ChevronRight size={20} />}
          </button>
        </div>
        <nav ref={desktopNavRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          {sidebarContent}
        </nav>
        {userSection}
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
        <div className="flex flex-shrink-0 items-center justify-between gap-2 p-2">
          <SidebarLogo size="sm" onClick={handleLinkClick} />
          <button
            onClick={() => setMobileSidebarOpen(false)}
            className="btn btn-ghost btn-sm btn-square"
            aria-label="Close menu"
          >
            <X size={20} />
          </button>
        </div>
        <nav ref={mobileNavRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          {sidebarContent}
        </nav>
        {userSection}
      </aside>

      {/* User Modal - Rendered outside sidebar for proper z-index stacking */}
      {userModal}
    </>
  );
}
