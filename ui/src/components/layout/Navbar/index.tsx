"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef } from "react";

import type { User } from "@/schemas";

import { useLogout } from "@/client/auth/auth";
import { EnvironmentBadge } from "@/components/ui/EnvironmentBadge";
import { useAuth } from "@/contexts/AuthContext";
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

function ProfileModal({
  modalRef,
  user,
}: {
  modalRef: React.RefObject<HTMLDialogElement>;
  user: User | null;
}) {
  return (
    <dialog ref={modalRef} className="modal modal-bottom sm:modal-middle">
      <div className="modal-box w-full sm:w-96 sm:max-w-sm">
        <div className="card">
          <figure className="relative w-full h-32 sm:h-64">
            <div className="bg-gray-200 w-full h-full flex items-center justify-center">
              <span className="text-3xl sm:text-4xl">
                {user?.username?.[0]?.toUpperCase()}
              </span>
            </div>
          </figure>
          <div className="card-body py-2 px-2 sm:px-4">
            <h2 className="card-title text-xl sm:text-2xl">{user?.username}</h2>
            <ul className="text-left text-sm sm:text-base">
              <li>Full Name: {user?.full_name}</li>
            </ul>
            <div className="modal-action">
              <form method="dialog">
                <button className="btn btn-sm sm:btn-md">Close</button>
              </form>
            </div>
          </div>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  );
}

function Navbar() {
  const modalRef = useRef<HTMLDialogElement>(null);
  const router = useRouter();
  const { user, logout: authLogout } = useAuth();

  const openModal = useCallback(() => {
    modalRef.current?.showModal();
  }, []);

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

  return (
    <nav className="navbar w-full">
      <div className="flex flex-1 md:gap-1 lg:gap-2 items-center">
        <HiddenIcon />
        <ProjectSelector />
        <EnvironmentBadge className="badge-sm sm:badge-md" />
      </div>
      <div className="dropdown dropdown-end">
        <div
          tabIndex={0}
          role="button"
          className="btn btn-ghost btn-circle avatar btn-sm sm:btn-md"
        >
          <div className="relative w-8 h-8 sm:w-10 sm:h-10 rounded-full shadow overflow-hidden">
            <div className="bg-gray-200 w-full h-full flex items-center justify-center">
              <span className="text-xl sm:text-2xl">
                {user?.username?.[0]?.toUpperCase()}
              </span>
            </div>
          </div>
        </div>
        <ul
          tabIndex={0}
          className="mt-3 z-[1] p-2 shadow menu menu-sm dropdown-content bg-base-100 rounded-box w-52"
        >
          <li>
            <button className="justify-between" onClick={openModal}>
              Profile
            </button>
          </li>
          <li>
            <button onClick={handleLogout}>Logout</button>
          </li>
        </ul>
      </div>
      <ProfileModal modalRef={modalRef} user={user} />
    </nav>
  );
}

export default Navbar;
