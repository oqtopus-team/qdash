"use client";

import { Folder, FolderLock } from "lucide-react";

import { EnvironmentBadge } from "@/components/ui/EnvironmentBadge";
import { useProject } from "@/contexts/ProjectContext";
import { useSidebar } from "@/contexts/SidebarContext";

function HiddenIcon() {
  const { toggleMobileSidebar } = useSidebar();

  return (
    <div className="flex items-center gap-2 lg:hidden">
      <button
        onClick={toggleMobileSidebar}
        className="btn btn-ghost btn-square"
        aria-label="Open menu"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
          className="w-6 h-6"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"
          />
        </svg>
      </button>
    </div>
  );
}

function ProjectSelector() {
  const { currentProject, projects, loading, switchProject } = useProject();

  if (loading) {
    return (
      <div className="flex items-center gap-2">
        <span className="loading loading-spinner loading-sm"></span>
      </div>
    );
  }

  return (
    <>
      <div className="dropdown dropdown-bottom">
        <div tabIndex={0} role="button" className="btn btn-ghost btn-sm gap-2">
          {currentProject ? (
            <Folder size={16} aria-hidden="true" />
          ) : (
            <FolderLock size={16} aria-hidden="true" />
          )}
          <span className="max-w-32 truncate">{currentProject?.name ?? "No projects"}</span>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
            className="w-3 h-3"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
          </svg>
        </div>
        <ul
          tabIndex={0}
          className="dropdown-content z-[1] menu p-2 shadow bg-base-100 rounded-box w-64 max-h-80 overflow-y-auto"
        >
          {projects.length === 0 && (
            <li>
              <span className="menu-disabled flex flex-col items-start">
                <span className="font-medium">No projects available</span>
                <span className="text-xs opacity-60">Ask an owner or admin for an invitation.</span>
              </span>
            </li>
          )}
          {projects.map((project) => (
            <li key={project.project_id}>
              <button
                className={`flex flex-col items-start ${
                  currentProject?.project_id === project.project_id ? "active" : ""
                }`}
                onClick={() => {
                  switchProject(project.project_id);
                  (document.activeElement as HTMLElement)?.blur();
                }}
              >
                <span className="font-medium truncate w-full text-left">{project.name}</span>
                {project.description && (
                  <span className="text-xs opacity-60 truncate w-full text-left">
                    {project.description}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}

export function Navbar() {
  return (
    <nav className="navbar w-full">
      <div className="flex flex-1 md:gap-1 lg:gap-2 items-center">
        <HiddenIcon />
        <ProjectSelector />
        <EnvironmentBadge className="badge-sm sm:badge-md" />
      </div>
    </nav>
  );
}
