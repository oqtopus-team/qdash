"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Fragment, useCallback, useRef } from "react";

import {
  BarChart3,
  BookMarked,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Code,
  Cpu,
  Download,
  FileJson2,
  Files,
  GitBranch,
  Inbox,
  LayoutDashboard,
  LayoutGrid,
  Snowflake,
  ListTodo,
  LogOut,
  Brain,
  CircleDot,
  MessagesSquare,
  Moon,
  Settings,
  ShieldCheck,
  Bot,
  ClipboardCheck,
  Sun,
  Workflow,
  X,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { useTheme } from "@/contexts/ThemeContext";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { useSidebar } from "@/contexts/SidebarContext";
import { useUnreadNotificationCount } from "@/hooks/useNotifications";
import { DARK_THEMES } from "@/constants/themes";

const PREFECT_URL = process.env.NEXT_PUBLIC_PREFECT_URL || "http://127.0.0.1:4200";

type NavItem = {
  href: string;
  label: string;
  title?: string;
  icon: LucideIcon;
  match?: "exact" | "prefix";
  badge?: number;
  visible?: boolean;
};

type ExternalNavItem = {
  href: string;
  label: string;
  title?: string;
  icon: LucideIcon;
  visible?: boolean;
};

type NavSection = {
  label: string;
  items: NavItem[];
};

function SectionHeader({ label, visible }: { label: string; visible: boolean }) {
  if (!visible) return null;
  return (
    <li className="menu-title text-xs font-semibold text-base-content/50 uppercase tracking-wider px-3 pt-3 pb-1">
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
        onClick={onClick}
      >
        <Icon size={18} />
        {showLabel && <span className="ml-2">{item.label}</span>}
        {badge > 0 && (
          <span className="badge badge-primary badge-xs ml-auto">{badge > 99 ? "99+" : badge}</span>
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
        {(isOpen || isMobileOpen) && <span className="ml-2">{item.label}</span>}
      </a>
    </li>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const modalRef = useRef<HTMLDialogElement>(null);
  const { isOpen, isMobileOpen, toggleSidebar, setMobileSidebarOpen } = useSidebar();
  const { canEdit } = useProject();
  const { user, logout: authLogout } = useAuth();
  const { theme, setTheme } = useTheme();
  const { data: unreadNotificationsResponse } = useUnreadNotificationCount();
  const unreadNotifications = unreadNotificationsResponse?.data.unread_count ?? 0;
  const isAdmin = user?.system_role === "admin";
  const isDarkTheme = DARK_THEMES.includes(theme as (typeof DARK_THEMES)[number]);

  const handleLogout = useCallback(async () => {
    await authLogout();
  }, [authLogout]);

  const openProfileModal = useCallback(() => {
    if (modalRef.current) {
      modalRef.current.showModal();
    }
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(isDarkTheme ? "light" : "dark");
  }, [isDarkTheme, setTheme]);

  const handleSettingsClick = useCallback(() => {
    modalRef.current?.close();
    if (isMobileOpen) {
      setMobileSidebarOpen(false);
    }
    router.push("/settings");
  }, [isMobileOpen, setMobileSidebarOpen, router]);

  const handleModalLogout = useCallback(async () => {
    modalRef.current?.close();
    await handleLogout();
  }, [handleLogout]);

  // Close mobile sidebar when clicking a link
  const handleLinkClick = () => {
    if (isMobileOpen) {
      setMobileSidebarOpen(false);
    }
  };

  // Mobile sidebar style
  const linkClass = (active: boolean) =>
    `py-2.5 px-3 mx-1 my-0.5 text-sm font-medium flex items-center rounded-lg transition-colors ${
      active ? "bg-neutral text-neutral-content" : "text-base-content hover:bg-base-300"
    }`;

  // Desktop sidebar style
  const desktopLinkClass = (active: boolean) =>
    `py-2.5 ${isOpen ? "px-3 mx-1" : "px-2 mx-1 justify-center"} my-0.5 text-sm font-medium flex items-center rounded-lg transition-colors ${
      active ? "bg-neutral text-neutral-content" : "text-base-content hover:bg-base-300"
    }`;

  const sectionHeaderVisible = isOpen || isMobileOpen;
  const navSections: NavSection[] = [
    {
      label: "Overview",
      items: [
        {
          href: "/inbox",
          label: "Inbox",
          icon: Inbox,
          badge: unreadNotifications,
        },
        { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
        { href: "/metrics", label: "Metrics", icon: LayoutGrid },
        { href: "/chip", label: "Chip", icon: Cpu },
        { href: "/analysis", label: "Analysis", icon: BarChart3 },
        { href: "/chat", label: "AI Chat", icon: Bot },
        {
          href: "/provenance",
          label: "Provenance",
          icon: GitBranch,
        },
      ],
    },
    {
      label: "Operate",
      items: [
        {
          href: "/workflow",
          label: "Workflow",
          icon: Code,
          match: "prefix",
          visible: canEdit,
        },
        { href: "/execution", label: "Execution", icon: Zap },
        {
          href: "/tasks",
          label: "Tasks",
          icon: ListTodo,
          visible: canEdit,
        },
        { href: "/cryo", label: "Cryo", icon: Snowflake },
        { href: "/import", label: "Import", icon: Download },
      ],
    },
    {
      label: "Collaborate",
      items: [
        { href: "/issues", label: "Issues", icon: CircleDot, match: "prefix" },
        {
          href: "/forum",
          label: "Forum",
          icon: MessagesSquare,
          match: "prefix",
        },
        {
          href: "/issue-knowledge",
          label: "Knowledge",
          icon: Brain,
          match: "prefix",
        },
        {
          href: "/ai-reviews",
          label: "AI Reviews",
          icon: ClipboardCheck,
          match: "prefix",
        },
        {
          href: "/task-knowledge",
          label: "Task Knowledge",
          icon: BookMarked,
          match: "prefix",
        },
      ],
    },
    {
      label: "Manage",
      items: [
        {
          href: "/files",
          label: "Files",
          icon: Files,
          match: "prefix",
          visible: canEdit,
        },
        { href: "/settings", label: "Settings", icon: Settings },
        {
          href: "/admin",
          label: "Admin",
          icon: ShieldCheck,
          visible: isAdmin,
        },
      ],
    },
  ];
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
      <ul className="menu p-2 py-0">
        {(isOpen || isMobileOpen) && (
          <div className="flex justify-center items-center p-3">
            <Link href="/" className="flex items-center" onClick={handleLinkClick}>
              <Image
                src="/oqtopus_logo.png"
                alt="Oqtopus Logo"
                width={100}
                height={25}
                className="object-contain"
                style={{ width: "auto", height: "auto" }}
                priority
              />
            </Link>
          </div>
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
    <dialog ref={modalRef} className="modal modal-bottom sm:modal-middle">
      <div className="modal-box w-full sm:w-96 sm:max-w-sm">
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
            onClick={handleSettingsClick}
            className="btn btn-ghost w-full justify-start gap-3 h-12"
          >
            <Settings size={18} />
            <span>Settings</span>
          </button>

          {/* Logout */}
          <button
            onClick={handleModalLogout}
            className="btn btn-ghost w-full justify-start gap-3 h-12 text-error"
          >
            <LogOut size={18} />
            <span>Logout</span>
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  );

  return (
    <>
      {/* Desktop Sidebar */}
      <aside
        className={`bg-base-200 h-full transition-all duration-300 hidden lg:flex lg:flex-col ${
          isOpen ? "w-44" : "w-16"
        }`}
      >
        <div className="flex justify-end p-2">
          <button
            onClick={toggleSidebar}
            className="btn btn-ghost btn-sm btn-square"
            aria-label={isOpen ? "Collapse sidebar" : "Expand sidebar"}
          >
            {isOpen ? <ChevronLeft size={20} /> : <ChevronRight size={20} />}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">{sidebarContent}</div>
        {userSection}
      </aside>

      {/* Mobile Sidebar Overlay */}
      {isMobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}

      {/* Mobile Sidebar Drawer */}
      <aside
        className={`fixed top-0 left-0 h-full w-48 bg-base-200 z-50 transform transition-transform duration-300 lg:hidden flex flex-col ${
          isMobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex justify-end p-2 flex-shrink-0">
          <button
            onClick={() => setMobileSidebarOpen(false)}
            className="btn btn-ghost btn-sm btn-square"
            aria-label="Close menu"
          >
            <X size={20} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">{sidebarContent}</div>
        {userSection}
      </aside>

      {/* User Modal - Rendered outside sidebar for proper z-index stacking */}
      {userModal}
    </>
  );
}
