"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useRef } from "react";

import {
  BarChart3,
  BookMarked,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Code,
  Cpu,
  FileJson2,
  Files,
  GitBranch,
  Inbox,
  LayoutGrid,
  ListTodo,
  LogOut,
  Brain,
  CircleDot,
  Moon,
  Settings,
  ShieldCheck,
  Bot,
  Sun,
  Workflow,
  X,
  Zap,
} from "lucide-react";

import { useTheme } from "@/contexts/ThemeContext";
import { useLogout } from "@/client/auth/auth";
import { FluentEmoji, getAvatarEmoji } from "@/components/ui/FluentEmoji";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { useSidebar } from "@/contexts/SidebarContext";
import { DARK_THEMES } from "@/constants/themes";

const PREFECT_URL =
  process.env.NEXT_PUBLIC_PREFECT_URL || "http://127.0.0.1:4200";

function SectionHeader({
  label,
  visible,
}: {
  label: string;
  visible: boolean;
}) {
  if (!visible) return null;
  return (
    <li className="menu-title text-xs font-semibold text-base-content/50 uppercase tracking-wider px-3 pt-3 pb-1">
      {label}
    </li>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const modalRef = useRef<HTMLDialogElement>(null);
  const { isOpen, isMobileOpen, toggleSidebar, setMobileSidebarOpen } =
    useSidebar();
  const { canEdit } = useProject();
  const { user, logout: authLogout } = useAuth();
  const { theme, setTheme } = useTheme();
  const isAdmin = user?.system_role === "admin";
  const isDarkTheme = DARK_THEMES.includes(
    theme as (typeof DARK_THEMES)[number],
  );

  const logoutMutation = useLogout();
  const handleLogout = useCallback(async () => {
    try {
      await logoutMutation.mutateAsync();
      authLogout();
      router.push("/login");
    } catch (error) {
      console.error("Logout failed:", error);
    }
  }, [logoutMutation, authLogout, router]);

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

  const isActive = (path: string) => {
    return pathname === path;
  };

  // Close mobile sidebar when clicking a link
  const handleLinkClick = () => {
    if (isMobileOpen) {
      setMobileSidebarOpen(false);
    }
  };

  // Mobile sidebar style
  const linkClass = (active: boolean) =>
    `py-2.5 px-3 mx-1 my-0.5 text-sm font-medium flex items-center rounded-lg transition-colors ${
      active
        ? "bg-neutral text-neutral-content"
        : "text-base-content hover:bg-base-300"
    }`;

  // Desktop sidebar style
  const desktopLinkClass = (active: boolean) =>
    `py-2.5 ${isOpen ? "px-3 mx-1" : "px-2 mx-1 justify-center"} my-0.5 text-sm font-medium flex items-center rounded-lg transition-colors ${
      active
        ? "bg-neutral text-neutral-content"
        : "text-base-content hover:bg-base-300"
    }`;

  const sectionHeaderVisible = isOpen || isMobileOpen;

  const sidebarContent = (
    <>
      <ul className="menu p-2 py-0">
        {(isOpen || isMobileOpen) && (
          <div className="flex justify-center items-center p-3">
            <Link
              href="/"
              className="flex items-center"
              onClick={handleLinkClick}
            >
              <Image
                src="/oqtopus_logo.png"
                alt="Oqtopus Logo"
                width={100}
                height={25}
                className="object-contain"
                priority
              />
            </Link>
          </div>
        )}

        {/* Data & Monitoring Section */}
        <SectionHeader visible={sectionHeaderVisible} label="Data" />
        <li>
          <Link
            href="/inbox"
            className={
              isMobileOpen
                ? linkClass(isActive("/inbox"))
                : desktopLinkClass(isActive("/inbox"))
            }
            title="Inbox"
            onClick={handleLinkClick}
          >
            <Inbox size={18} />
            {(isOpen || isMobileOpen) && <span className="ml-2">Inbox</span>}
          </Link>
        </li>
        <li>
          <Link
            href="/metrics"
            className={
              isMobileOpen
                ? linkClass(isActive("/metrics"))
                : desktopLinkClass(isActive("/metrics"))
            }
            title="Metrics"
            onClick={handleLinkClick}
          >
            <LayoutGrid size={18} />
            {(isOpen || isMobileOpen) && <span className="ml-2">Metrics</span>}
          </Link>
        </li>
        <li>
          <Link
            href="/chip"
            className={
              isMobileOpen
                ? linkClass(isActive("/chip"))
                : desktopLinkClass(isActive("/chip"))
            }
            title="Chip"
            onClick={handleLinkClick}
          >
            <Cpu size={18} />
            {(isOpen || isMobileOpen) && <span className="ml-2">Chip</span>}
          </Link>
        </li>
        <li>
          <Link
            href="/analysis"
            className={
              isMobileOpen
                ? linkClass(isActive("/analysis"))
                : desktopLinkClass(isActive("/analysis"))
            }
            title="Analysis"
            onClick={handleLinkClick}
          >
            <BarChart3 size={18} />
            {(isOpen || isMobileOpen) && <span className="ml-2">Analysis</span>}
          </Link>
        </li>
        <li>
          <Link
            href="/chat"
            className={
              isMobileOpen
                ? linkClass(isActive("/chat"))
                : desktopLinkClass(isActive("/chat"))
            }
            title="AI Chat"
            onClick={handleLinkClick}
          >
            <Bot size={18} />
            {(isOpen || isMobileOpen) && <span className="ml-2">AI Chat</span>}
          </Link>
        </li>
        <li>
          <Link
            href="/provenance"
            className={
              isMobileOpen
                ? linkClass(isActive("/provenance"))
                : desktopLinkClass(isActive("/provenance"))
            }
            title="Provenance"
            onClick={handleLinkClick}
          >
            <GitBranch size={18} />
            {(isOpen || isMobileOpen) && (
              <span className="ml-2">Provenance</span>
            )}
          </Link>
        </li>

        <li>
          <Link
            href="/task-knowledge"
            className={
              isMobileOpen
                ? linkClass(pathname.startsWith("/task-knowledge"))
                : desktopLinkClass(pathname.startsWith("/task-knowledge"))
            }
            title="Task Knowledge"
            onClick={handleLinkClick}
          >
            <BookMarked size={18} />
            {(isOpen || isMobileOpen) && (
              <span className="ml-2">Task Knowledge</span>
            )}
          </Link>
        </li>

        {/* Operations Section */}
        <SectionHeader visible={sectionHeaderVisible} label="Operations" />
        {canEdit && (
          <li>
            <Link
              href="/workflow"
              className={
                isMobileOpen
                  ? linkClass(pathname.startsWith("/workflow"))
                  : desktopLinkClass(pathname.startsWith("/workflow"))
              }
              title="Workflow"
              onClick={handleLinkClick}
            >
              <Code size={18} />
              {(isOpen || isMobileOpen) && (
                <span className="ml-2">Workflow</span>
              )}
            </Link>
          </li>
        )}
        <li>
          <Link
            href="/execution"
            className={
              isMobileOpen
                ? linkClass(isActive("/execution"))
                : desktopLinkClass(isActive("/execution"))
            }
            title="Execution"
            onClick={handleLinkClick}
          >
            <Zap size={18} />
            {(isOpen || isMobileOpen) && (
              <span className="ml-2">Execution</span>
            )}
          </Link>
        </li>
        <li>
          <Link
            href="/issues"
            className={
              isMobileOpen
                ? linkClass(pathname.startsWith("/issues"))
                : desktopLinkClass(pathname.startsWith("/issues"))
            }
            title="Issues"
            onClick={handleLinkClick}
          >
            <CircleDot size={18} />
            {(isOpen || isMobileOpen) && <span className="ml-2">Issues</span>}
          </Link>
        </li>
        <li>
          <Link
            href="/issue-knowledge"
            className={
              isMobileOpen
                ? linkClass(pathname.startsWith("/issue-knowledge"))
                : desktopLinkClass(pathname.startsWith("/issue-knowledge"))
            }
            title="Knowledge"
            onClick={handleLinkClick}
          >
            <Brain size={18} />
            {(isOpen || isMobileOpen) && (
              <span className="ml-2">Knowledge</span>
            )}
          </Link>
        </li>
        {canEdit && (
          <li>
            <Link
              href="/tasks"
              className={
                isMobileOpen
                  ? linkClass(isActive("/tasks"))
                  : desktopLinkClass(isActive("/tasks"))
              }
              title="Tasks"
              onClick={handleLinkClick}
            >
              <ListTodo size={18} />
              {(isOpen || isMobileOpen) && <span className="ml-2">Tasks</span>}
            </Link>
          </li>
        )}

        {/* Management Section */}
        <SectionHeader visible={sectionHeaderVisible} label="Manage" />
        {canEdit && (
          <li>
            <Link
              href="/files"
              className={
                isMobileOpen
                  ? linkClass(pathname.startsWith("/files"))
                  : desktopLinkClass(pathname.startsWith("/files"))
              }
              title="Files"
              onClick={handleLinkClick}
            >
              <Files size={18} />
              {(isOpen || isMobileOpen) && <span className="ml-2">Files</span>}
            </Link>
          </li>
        )}
        <li>
          <Link
            href="/settings"
            className={
              isMobileOpen
                ? linkClass(isActive("/settings"))
                : desktopLinkClass(isActive("/settings"))
            }
            title="Settings"
            onClick={handleLinkClick}
          >
            <Settings size={18} />
            {(isOpen || isMobileOpen) && <span className="ml-2">Settings</span>}
          </Link>
        </li>
        {isAdmin && (
          <li>
            <Link
              href="/admin"
              className={
                isMobileOpen
                  ? linkClass(isActive("/admin"))
                  : desktopLinkClass(isActive("/admin"))
              }
              title="Admin"
              onClick={handleLinkClick}
            >
              <ShieldCheck size={18} />
              {(isOpen || isMobileOpen) && <span className="ml-2">Admin</span>}
            </Link>
          </li>
        )}

        {/* External Links Section */}
        <div className={`divider ${isMobileOpen ? "my-1" : "my-0"}`}></div>
        <li>
          <a
            href="https://oqtopus-team.github.io/qdash/"
            target="_blank"
            rel="noopener noreferrer"
            className={
              isMobileOpen ? linkClass(false) : desktopLinkClass(false)
            }
            title="Docs"
            onClick={handleLinkClick}
          >
            <BookOpen size={18} />
            {(isOpen || isMobileOpen) && <span className="ml-2">Docs</span>}
          </a>
        </li>
        {canEdit && (
          <>
            <li>
              <a
                href={`${PREFECT_URL}/dashboard`}
                target="_blank"
                rel="noopener noreferrer"
                className={
                  isMobileOpen ? linkClass(false) : desktopLinkClass(false)
                }
                title="Workflow"
                onClick={handleLinkClick}
              >
                <Workflow size={18} />
                {(isOpen || isMobileOpen) && (
                  <span className="ml-2">Workflow</span>
                )}
              </a>
            </li>
            <li>
              <a
                href="/api/docs"
                target="_blank"
                rel="noopener noreferrer"
                className={
                  isMobileOpen ? linkClass(false) : desktopLinkClass(false)
                }
                title="API Docs"
                onClick={handleLinkClick}
              >
                <FileJson2 size={18} />
                {(isOpen || isMobileOpen) && (
                  <span className="ml-2">API Docs</span>
                )}
              </a>
            </li>
          </>
        )}
      </ul>
    </>
  );

  const avatarEmoji = getAvatarEmoji(user?.username || "");

  const userSection = (
    <div
      className={`border-t border-base-300 ${isMobileOpen ? "p-2" : isOpen ? "p-2 mx-2" : "p-1"}`}
    >
      <button
        onClick={openProfileModal}
        className={`btn btn-ghost w-full ${isOpen || isMobileOpen ? "justify-start gap-3" : "justify-center p-0"} h-auto py-2`}
      >
        <div className="flex items-center justify-center">
          <FluentEmoji
            name={avatarEmoji}
            size={isOpen || isMobileOpen ? 28 : 40}
          />
        </div>
        {(isOpen || isMobileOpen) && (
          <div className="flex-1 text-left min-w-0">
            <div className="text-sm font-medium truncate">
              {user?.username || "User"}
            </div>
            <div className="text-xs opacity-60 truncate">
              {user?.full_name || ""}
            </div>
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
            <FluentEmoji name={avatarEmoji} size={64} />
          </div>
          <h2 className="text-lg font-bold">{user?.username}</h2>
          {user?.full_name && (
            <p className="text-sm text-base-content/60">{user?.full_name}</p>
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
              type="checkbox"
              className="toggle toggle-sm"
              checked={isDarkTheme}
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
