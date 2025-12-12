"use client";

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
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
            className="w-4 h-4"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z"
            />
          </svg>
          <span className="max-w-32 truncate">
            {currentProject?.name ?? "Select Project"}
          </span>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
            className="w-3 h-3"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="m19.5 8.25-7.5 7.5-7.5-7.5"
            />
          </svg>
        </div>
        <ul
          tabIndex={0}
          className="dropdown-content z-[1] menu p-2 shadow bg-base-100 rounded-box w-64 max-h-80 overflow-y-auto"
        >
          {projects.map((project) => (
            <li key={project.project_id}>
              <button
                className={`flex flex-col items-start ${
                  currentProject?.project_id === project.project_id
                    ? "active"
                    : ""
                }`}
                onClick={() => {
                  switchProject(project.project_id);
                  (document.activeElement as HTMLElement)?.blur();
                }}
              >
                <span className="font-medium truncate w-full text-left">
                  {project.name}
                </span>
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

function Navbar() {
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

export default Navbar;
