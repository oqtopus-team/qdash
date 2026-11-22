"use client";

import { ChevronDown, Folder, FolderLock } from "lucide-react";
import { Suspense } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import { EnvironmentBadge } from "@/components/ui/EnvironmentBadge";
import { useProject } from "@/contexts/ProjectContext";
import { GlobalCommandPalette } from "@/components/layout/GlobalCommandPalette";
import { GlobalExecutionIndicator } from "@/components/layout/GlobalExecutionIndicator";
import { NotificationsMenu } from "@/components/layout/NotificationsMenu";

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
        <button type="button" className="btn btn-ghost btn-sm">
          {currentProject ? (
            <Folder data-icon="inline-start" aria-hidden="true" />
          ) : (
            <FolderLock data-icon="inline-start" aria-hidden="true" />
          )}
          <span className="max-w-32 truncate">{currentProject?.name ?? "No projects"}</span>
          <ChevronDown data-icon="inline-end" aria-hidden="true" />
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
    <nav className="navbar z-20 min-h-14 w-full border-b border-base-300 bg-base-100/95 px-3 backdrop-blur-sm sm:px-4">
      <div className="flex flex-1 md:gap-1 lg:gap-2 items-center">
        <ProjectSelector />
        <EnvironmentBadge className="badge-sm sm:badge-md" />
        <Suspense fallback={null}>
          <GlobalCommandPalette />
        </Suspense>
        <div className="ml-auto flex items-center gap-1">
          <GlobalExecutionIndicator />
          <NotificationsMenu />
        </div>
      </div>
    </nav>
  );
}
