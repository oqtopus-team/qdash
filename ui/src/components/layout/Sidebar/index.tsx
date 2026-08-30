"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";

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
import { useUnreadNotificationCount } from "@/hooks/useNotifications";
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

function SectionHeader({ label, visible }: { label: string; visible: boolean }) {
  if (!visible) return null;
  return (
    <li className="menu-title px-3 pb-1 pt-2 text-[0.6875rem] font-semibold uppercase tracking-[0.12em] text-base-content/50">
      {label}
    </li>
  );
}

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
  const active = item.match === "prefix" ? pathname.startsWith(item.href) : pathname === item.href;
  const showLabel = isOpen || isMobileOpen;
  const badge = item.badge ?? 0;

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
        {badge > 0 && (
          <span className="badge badge-primary badge-xs ml-auto shrink-0">
            {badge > 99 ? "99+" : badge}
          </span>
        )}
      </Link>
    </li>
  );
}

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
  const { data: unreadNotificationsResponse } = useUnreadNotificationCount();
  const unreadNotifications = unreadNotificationsResponse?.data.unread_count ?? 0;
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
    `relative min-h-10 px-3 mx-1 my-0.5 text-sm font-medium flex items-center rounded-lg transition-colors ${
      active
        ? "bg-primary/12 text-primary before:absolute before:inset-y-2 before:left-0 before:w-1 before:rounded-r-full before:bg-primary"
        : "text-base-content/75 hover:bg-base-300 hover:text-base-content"
    }`;

  // Desktop sidebar style
  const desktopLinkClass = (active: boolean) =>
    `relative min-h-9 ${isOpen ? "px-3 mx-1" : "px-2 mx-1 justify-center"} my-0.5 text-sm font-medium flex items-center rounded-lg transition-colors ${
      active
        ? "bg-primary/12 text-primary before:absolute before:inset-y-2 before:left-0 before:w-1 before:rounded-r-full before:bg-primary"
        : "text-base-content/75 hover:bg-base-300 hover:text-base-content"
    }`;

  const sectionHeaderVisible = isOpen || isMobileOpen;
  const navSections: NavSection[] = getNavigationSections({
    canEdit,
    isAdmin,
    unreadNotifications,
  });
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

  const sidebarContent = (
    <>
      <ul className="menu max-lg:w-full max-lg:flex-nowrap max-lg:[&>li]:flex-nowrap p-2 py-0">
        {isOpen && (
          <li className="mb-1 hidden lg:block">
            <SidebarLogo size="lg" onClick={handleLinkClick} />
          </li>
        )}

        {navSections.map((section) => {
          const visibleItems = section.items.filter((item) => item.visible !== false);
          if (visibleItems.length === 0) return null;

          return (
            <Fragment key={section.label}>
              <SectionHeader visible={sectionHeaderVisible} label={section.label} />
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
            </Fragment>
          );
        })}

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
    </>
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
          <h2 className="text-lg font-bold">{user?.username}</h2>
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
        className={`hidden h-full border-r border-base-300 bg-base-200 transition-all duration-300 lg:flex lg:flex-col ${
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
