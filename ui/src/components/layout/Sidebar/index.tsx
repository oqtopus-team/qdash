"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { BsListTask, BsGrid, BsCpu } from "react-icons/bs";
import { FaCode } from "react-icons/fa";
import { FaBolt } from "react-icons/fa6";
import { FiChevronLeft, FiChevronRight, FiX } from "react-icons/fi";
import { GoWorkflow } from "react-icons/go";
import { IoMdSettings } from "react-icons/io";
import { IoAnalytics } from "react-icons/io5";
import { MdAdminPanelSettings } from "react-icons/md";
import { SiSwagger } from "react-icons/si";
import { VscFiles } from "react-icons/vsc";

import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { useSidebar } from "@/contexts/SidebarContext";

const PREFECT_URL =
  process.env.NEXT_PUBLIC_PREFECT_URL || "http://127.0.0.1:4200";

function Sidebar() {
  const pathname = usePathname();
  const { isOpen, isMobileOpen, toggleSidebar, setMobileSidebarOpen } =
    useSidebar();
  const { canEdit } = useProject();
  const { user } = useAuth();
  const isAdmin = user?.system_role === "admin";
  const isActive = (path: string) => {
    return pathname === path;
  };

  // Close mobile sidebar when clicking a link
  const handleLinkClick = () => {
    if (isMobileOpen) {
      setMobileSidebarOpen(false);
    }
  };

  const sidebarContent = (
    <>
      <ul className="menu p-4 py-0">
        {(isOpen || isMobileOpen) && (
          <div className="flex justify-center items-center p-4">
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
        <li>
          <Link
            href="/metrics"
            className={`py-4 ${
              isOpen || isMobileOpen ? "px-4 mx-10" : "px-2 mx-0 justify-center"
            } my-2 text-base font-bold flex items-center ${
              isActive("/metrics")
                ? "bg-neutral text-neutral-content"
                : "text-base-content"
            }`}
            title="Metrics"
            onClick={handleLinkClick}
          >
            <BsGrid />
            {(isOpen || isMobileOpen) && <span className="ml-2">Metrics</span>}
          </Link>
        </li>
        <li>
          <Link
            href="/chip"
            className={`py-4 ${
              isOpen || isMobileOpen ? "px-4 mx-10" : "px-2 mx-0 justify-center"
            } my-2 text-base font-bold flex items-center ${
              isActive("/chip")
                ? "bg-neutral text-neutral-content"
                : "text-base-content"
            }`}
            title="Chip"
            onClick={handleLinkClick}
          >
            <BsCpu />
            {(isOpen || isMobileOpen) && <span className="ml-2">Chip</span>}
          </Link>
        </li>
        {canEdit && (
          <li>
            <Link
              href="/flow"
              className={`py-4 ${
                isOpen || isMobileOpen
                  ? "px-4 mx-10"
                  : "px-2 mx-0 justify-center"
              } my-2 text-base font-bold flex items-center ${
                pathname.startsWith("/flow")
                  ? "bg-neutral text-neutral-content"
                  : "text-base-content"
              }`}
              title="Editor"
              onClick={handleLinkClick}
            >
              <FaCode />
              {(isOpen || isMobileOpen) && <span className="ml-2">Editor</span>}
            </Link>
          </li>
        )}
        <li>
          <Link
            href="/execution"
            className={`py-4 ${
              isOpen || isMobileOpen ? "px-4 mx-10" : "px-2 mx-0 justify-center"
            } my-2 text-base font-bold flex items-center ${
              isActive("/execution")
                ? "bg-neutral text-neutral-content"
                : "text-base-content"
            }`}
            title="Execution"
            onClick={handleLinkClick}
          >
            <FaBolt />
            {(isOpen || isMobileOpen) && (
              <span className="ml-2">Execution</span>
            )}
          </Link>
        </li>
        <li>
          <Link
            href="/analysis"
            className={`py-4 ${
              isOpen || isMobileOpen ? "px-4 mx-10" : "px-2 mx-0 justify-center"
            } my-2 text-base font-bold flex items-center ${
              isActive("/analysis")
                ? "bg-neutral text-neutral-content"
                : "text-base-content"
            }`}
            title="Analysis"
            onClick={handleLinkClick}
          >
            <IoAnalytics />
            {(isOpen || isMobileOpen) && <span className="ml-2">Analysis</span>}
          </Link>
        </li>
        {canEdit && (
          <li>
            <Link
              href="/tasks"
              className={`py-4 ${
                isOpen || isMobileOpen
                  ? "px-4 mx-10"
                  : "px-2 mx-0 justify-center"
              } my-2 text-base font-bold flex items-center ${
                isActive("/tasks")
                  ? "bg-neutral text-neutral-content"
                  : "text-base-content"
              }`}
              title="Tasks"
              onClick={handleLinkClick}
            >
              <BsListTask />
              {(isOpen || isMobileOpen) && <span className="ml-2">Tasks</span>}
            </Link>
          </li>
        )}
        {canEdit && (
          <li>
            <Link
              href="/files"
              className={`py-4 ${
                isOpen || isMobileOpen
                  ? "px-4 mx-10"
                  : "px-2 mx-0 justify-center"
              } my-2 text-base font-bold flex items-center ${
                pathname.startsWith("/files")
                  ? "bg-neutral text-neutral-content"
                  : "text-base-content"
              }`}
              title="Files"
              onClick={handleLinkClick}
            >
              <VscFiles />
              {(isOpen || isMobileOpen) && <span className="ml-2">Files</span>}
            </Link>
          </li>
        )}

        <li>
          <Link
            href="/setting"
            className={`py-4 ${
              isOpen || isMobileOpen ? "px-4 mx-10" : "px-2 mx-0 justify-center"
            } my-2 text-base font-bold flex items-center ${
              isActive("/setting")
                ? "bg-neutral text-neutral-content"
                : "text-base-content"
            }`}
            title="Settings"
            onClick={handleLinkClick}
          >
            <IoMdSettings />
            {(isOpen || isMobileOpen) && <span className="ml-2">Settings</span>}
          </Link>
        </li>
        {isAdmin && (
          <li>
            <Link
              href="/admin"
              className={`py-4 ${
                isOpen || isMobileOpen
                  ? "px-4 mx-10"
                  : "px-2 mx-0 justify-center"
              } my-2 text-base font-bold flex items-center ${
                isActive("/admin")
                  ? "bg-neutral text-neutral-content"
                  : "text-base-content"
              }`}
              title="Admin"
              onClick={handleLinkClick}
            >
              <MdAdminPanelSettings />
              {(isOpen || isMobileOpen) && <span className="ml-2">Admin</span>}
            </Link>
          </li>
        )}
        {canEdit && (
          <>
            <div className="divider"></div>
            <li>
              <a
                href={`${PREFECT_URL}/dashboard`}
                target="_blank"
                rel="noopener noreferrer"
                className={`py-4 ${
                  isOpen || isMobileOpen
                    ? "px-4 mx-10"
                    : "px-2 mx-0 justify-center"
                } my-2 text-base font-bold flex items-center`}
                title="Workflow"
                onClick={handleLinkClick}
              >
                <GoWorkflow />
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
                className={`py-4 ${
                  isOpen || isMobileOpen
                    ? "px-4 mx-10"
                    : "px-2 mx-0 justify-center"
                } my-2 text-base font-bold flex items-center`}
                title="API Docs"
                onClick={handleLinkClick}
              >
                <SiSwagger />
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

  return (
    <>
      {/* Desktop Sidebar */}
      <aside
        className={`bg-base-200 min-h-screen transition-all duration-300 hidden lg:block ${
          isOpen ? "w-80" : "w-20"
        }`}
      >
        <div className="flex justify-end p-2">
          <button
            onClick={toggleSidebar}
            className="btn btn-ghost btn-sm btn-square"
            aria-label={isOpen ? "Collapse sidebar" : "Expand sidebar"}
          >
            {isOpen ? (
              <FiChevronLeft size={20} />
            ) : (
              <FiChevronRight size={20} />
            )}
          </button>
        </div>
        {sidebarContent}
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
        className={`fixed top-0 left-0 h-full w-80 bg-base-200 z-50 transform transition-transform duration-300 lg:hidden ${
          isMobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex justify-end p-2">
          <button
            onClick={() => setMobileSidebarOpen(false)}
            className="btn btn-ghost btn-sm btn-square"
            aria-label="Close menu"
          >
            <FiX size={20} />
          </button>
        </div>
        {sidebarContent}
      </aside>
    </>
  );
}

export default Sidebar;
