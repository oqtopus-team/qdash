"use client";

import { ChevronDown, Folder, FolderLock } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
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
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className="btn btn-ghost btn-sm gap-2">
          {currentProject ? (
            <Folder size={16} aria-hidden="true" />
          ) : (
            <FolderLock size={16} aria-hidden="true" />
          )}
          <span className="max-w-32 truncate">{currentProject?.name ?? "No projects"}</span>
          <ChevronDown className="h-3 w-3" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-80 w-64">
        {projects.length === 0 && (
          <DropdownMenuLabel className="flex flex-col items-start gap-0.5 py-2">
            <span className="font-medium text-base-content">No projects available</span>
            <span className="font-normal text-base-content/60">
              Ask an owner or admin for an invitation.
            </span>
          </DropdownMenuLabel>
        )}
        {projects.map((project) => (
          <DropdownMenuItem
            key={project.project_id}
            className={`flex-col items-start gap-0.5 ${
              currentProject?.project_id === project.project_id ? "bg-primary/10 text-primary" : ""
            }`}
            onSelect={() => switchProject(project.project_id)}
          >
            <span className="font-medium truncate w-full text-left">{project.name}</span>
            {project.description && (
              <span className="text-xs opacity-60 truncate w-full text-left">
                {project.description}
              </span>
            )}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
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
