"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";

import type { User } from "@/schemas";

import { useAuth } from "@/app/contexts/AuthContext";
import { useProject } from "@/app/contexts/ProjectContext";
import { useLogout } from "@/client/auth/auth";
import {
  useCreateProject,
  useUpdateProject,
  useDeleteProject,
  useListProjectMembers,
  useInviteProjectMember,
  useUpdateProjectMember,
  useRemoveProjectMember,
} from "@/client/projects/projects";
import type { ProjectResponse, ProjectRole, MemberResponse } from "@/schemas";

function HiddenIcon() {
  return (
    <div className="flex items-center gap-2 lg:hidden">
      <a
        href="/"
        aria-current="page"
        aria-label="daisyUI"
        className="flex-0 btn btn-ghost gap-1 px-2 md:gap-2"
      >
        {/* Logo can be added here using Next.js Image component */}
      </a>
    </div>
  );
}

function CreateProjectModal({
  modalRef,
  onCreated,
}: {
  modalRef: React.RefObject<HTMLDialogElement>;
  onCreated: (projectId: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const createProject = useCreateProject();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError("Project name is required");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const response = await createProject.mutateAsync({
        data: {
          name: name.trim(),
          description: description.trim() || null,
          tags: [],
        },
      });
      setName("");
      setDescription("");
      modalRef.current?.close();
      onCreated(response.data.project_id);
    } catch (err) {
      setError("Failed to create project");
      console.error("Failed to create project:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <dialog ref={modalRef} className="modal">
      <div className="modal-box w-96">
        <h3 className="font-bold text-lg mb-4">Create New Project</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-control mb-4">
            <label className="label">
              <span className="label-text">Project Name</span>
            </label>
            <input
              type="text"
              placeholder="My Project"
              className="input input-bordered w-full"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isSubmitting}
            />
          </div>
          <div className="form-control mb-4">
            <label className="label">
              <span className="label-text">Description (optional)</span>
            </label>
            <textarea
              placeholder="Project description..."
              className="textarea textarea-bordered w-full"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isSubmitting}
              rows={3}
            />
          </div>
          {error && (
            <div className="text-error text-sm mb-4">{error}</div>
          )}
          <div className="modal-action">
            <button
              type="button"
              className="btn"
              onClick={() => modalRef.current?.close()}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <span className="loading loading-spinner loading-sm"></span>
              ) : (
                "Create"
              )}
            </button>
          </div>
        </form>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  );
}

function ProjectSettingsModal({
  modalRef,
  project,
  onUpdated,
  onDeleted,
}: {
  modalRef: React.RefObject<HTMLDialogElement>;
  project: ProjectResponse | null;
  onUpdated: () => void;
  onDeleted: () => void;
}) {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<"general" | "members">("general");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inviteUsername, setInviteUsername] = useState("");
  const [inviteRole, setInviteRole] = useState<ProjectRole>("viewer");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const updateProject = useUpdateProject();
  const deleteProject = useDeleteProject();
  const inviteMember = useInviteProjectMember();
  const updateMember = useUpdateProjectMember();
  const removeMember = useRemoveProjectMember();

  const { data: membersData, refetch: refetchMembers } = useListProjectMembers(
    project?.project_id ?? "",
    {
      query: {
        enabled: !!project?.project_id,
      },
    }
  );

  const members = membersData?.data?.members ?? [];
  const isOwner = project?.owner_username === user?.username;

  // Reset form when project changes
  const resetForm = useCallback(() => {
    if (project) {
      setName(project.name);
      setDescription(project.description ?? "");
    }
    setError(null);
    setInviteUsername("");
    setInviteRole("viewer");
    setShowDeleteConfirm(false);
  }, [project]);

  // Reset when modal opens
  const handleModalOpen = useCallback(() => {
    resetForm();
    refetchMembers();
  }, [resetForm, refetchMembers]);

  const handleSaveGeneral = async () => {
    if (!project || !name.trim()) return;
    setIsSubmitting(true);
    setError(null);

    try {
      await updateProject.mutateAsync({
        projectId: project.project_id,
        data: {
          name: name.trim(),
          description: description.trim() || null,
        },
      });
      onUpdated();
    } catch (err) {
      setError("Failed to update project");
      console.error(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!project) return;
    setIsSubmitting(true);
    try {
      await deleteProject.mutateAsync({ projectId: project.project_id });
      modalRef.current?.close();
      onDeleted();
    } catch (err) {
      setError("Failed to delete project");
      console.error(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!project || !inviteUsername.trim()) return;
    setIsSubmitting(true);
    setError(null);

    try {
      await inviteMember.mutateAsync({
        projectId: project.project_id,
        data: {
          username: inviteUsername.trim(),
          role: inviteRole,
        },
      });
      setInviteUsername("");
      setInviteRole("viewer");
      refetchMembers();
    } catch (err) {
      setError("Failed to invite member");
      console.error(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRoleChange = async (username: string, newRole: ProjectRole) => {
    if (!project) return;
    try {
      await updateMember.mutateAsync({
        projectId: project.project_id,
        username,
        data: { role: newRole },
      });
      refetchMembers();
    } catch (err) {
      console.error("Failed to update role:", err);
    }
  };

  const handleRemoveMember = async (username: string) => {
    if (!project) return;
    try {
      await removeMember.mutateAsync({
        projectId: project.project_id,
        username,
      });
      refetchMembers();
    } catch (err) {
      console.error("Failed to remove member:", err);
    }
  };

  return (
    <dialog
      ref={modalRef}
      className="modal"
      onClose={resetForm}
      onClick={(e) => {
        if (e.target === modalRef.current) handleModalOpen();
      }}
    >
      <div className="modal-box w-[500px] max-w-[90vw]">
        <h3 className="font-bold text-lg mb-4">Project Settings</h3>

        {/* Tabs */}
        <div className="tabs tabs-boxed mb-4">
          <button
            className={`tab ${activeTab === "general" ? "tab-active" : ""}`}
            onClick={() => setActiveTab("general")}
          >
            General
          </button>
          <button
            className={`tab ${activeTab === "members" ? "tab-active" : ""}`}
            onClick={() => setActiveTab("members")}
          >
            Members
          </button>
        </div>

        {error && <div className="text-error text-sm mb-4">{error}</div>}

        {/* General Tab */}
        {activeTab === "general" && (
          <div>
            <div className="form-control mb-4">
              <label className="label">
                <span className="label-text">Project Name</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={!isOwner || isSubmitting}
              />
            </div>
            <div className="form-control mb-4">
              <label className="label">
                <span className="label-text">Description</span>
              </label>
              <textarea
                className="textarea textarea-bordered w-full"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                disabled={!isOwner || isSubmitting}
                rows={3}
              />
            </div>

            {isOwner && (
              <>
                <button
                  className="btn btn-primary w-full mb-4"
                  onClick={handleSaveGeneral}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <span className="loading loading-spinner loading-sm"></span>
                  ) : (
                    "Save Changes"
                  )}
                </button>

                <div className="divider"></div>

                <div className="text-sm text-base-content/70 mb-2">
                  Danger Zone
                </div>
                {!showDeleteConfirm ? (
                  <button
                    className="btn btn-error btn-outline w-full"
                    onClick={() => setShowDeleteConfirm(true)}
                  >
                    Delete Project
                  </button>
                ) : (
                  <div className="flex gap-2">
                    <button
                      className="btn btn-error flex-1"
                      onClick={handleDelete}
                      disabled={isSubmitting}
                    >
                      Confirm Delete
                    </button>
                    <button
                      className="btn flex-1"
                      onClick={() => setShowDeleteConfirm(false)}
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </>
            )}

            {!isOwner && (
              <div className="text-sm text-base-content/60">
                Only the project owner can edit settings.
              </div>
            )}
          </div>
        )}

        {/* Members Tab */}
        {activeTab === "members" && (
          <div>
            {/* Invite Form */}
            {isOwner && (
              <form onSubmit={handleInvite} className="flex gap-2 mb-4">
                <input
                  type="text"
                  placeholder="Username"
                  className="input input-bordered input-sm flex-1"
                  value={inviteUsername}
                  onChange={(e) => setInviteUsername(e.target.value)}
                  disabled={isSubmitting}
                />
                <select
                  className="select select-bordered select-sm"
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as ProjectRole)}
                  disabled={isSubmitting}
                >
                  <option value="viewer">Viewer</option>
                  <option value="editor">Editor</option>
                </select>
                <button
                  type="submit"
                  className="btn btn-primary btn-sm"
                  disabled={isSubmitting || !inviteUsername.trim()}
                >
                  Invite
                </button>
              </form>
            )}

            {/* Members List */}
            <div className="overflow-x-auto">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Role</th>
                    {isOwner && <th></th>}
                  </tr>
                </thead>
                <tbody>
                  {members.map((member: MemberResponse) => (
                    <tr key={member.username}>
                      <td>
                        <div className="flex items-center gap-2">
                          <div className="avatar placeholder">
                            <div className="bg-neutral text-neutral-content rounded-full w-6">
                              <span className="text-xs">
                                {member.username[0]?.toUpperCase()}
                              </span>
                            </div>
                          </div>
                          <span>{member.username}</span>
                          {member.username === user?.username && (
                            <span className="badge badge-xs">you</span>
                          )}
                        </div>
                      </td>
                      <td>
                        {isOwner && member.role !== "owner" ? (
                          <select
                            className="select select-bordered select-xs"
                            value={member.role}
                            onChange={(e) =>
                              handleRoleChange(
                                member.username,
                                e.target.value as ProjectRole
                              )
                            }
                          >
                            <option value="viewer">Viewer</option>
                            <option value="editor">Editor</option>
                          </select>
                        ) : (
                          <span
                            className={`badge badge-sm ${
                              member.role === "owner"
                                ? "badge-primary"
                                : member.role === "editor"
                                  ? "badge-secondary"
                                  : "badge-ghost"
                            }`}
                          >
                            {member.role}
                          </span>
                        )}
                      </td>
                      {isOwner && (
                        <td>
                          {member.role !== "owner" && (
                            <button
                              className="btn btn-ghost btn-xs text-error"
                              onClick={() => handleRemoveMember(member.username)}
                            >
                              Remove
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="modal-action">
          <form method="dialog">
            <button className="btn">Close</button>
          </form>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  );
}

function ProjectSelector() {
  const { currentProject, projects, loading, switchProject, refreshProjects } =
    useProject();
  const createModalRef = useRef<HTMLDialogElement>(null);
  const settingsModalRef = useRef<HTMLDialogElement>(null);

  const handleProjectCreated = useCallback(
    (projectId: string) => {
      refreshProjects();
      switchProject(projectId);
    },
    [refreshProjects, switchProject]
  );

  const handleProjectUpdated = useCallback(() => {
    refreshProjects();
  }, [refreshProjects]);

  const handleProjectDeleted = useCallback(() => {
    refreshProjects();
    // Switch to first available project
    if (projects.length > 1) {
      const remaining = projects.filter(
        (p) => p.project_id !== currentProject?.project_id
      );
      if (remaining.length > 0) {
        switchProject(remaining[0].project_id);
      }
    }
  }, [refreshProjects, projects, currentProject, switchProject]);

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
        <div
          tabIndex={0}
          role="button"
          className="btn btn-ghost btn-sm gap-2"
        >
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
          <li className="border-t border-base-300 mt-2 pt-2">
            {currentProject && (
              <button
                className="flex items-center gap-2"
                onClick={() => {
                  (document.activeElement as HTMLElement)?.blur();
                  settingsModalRef.current?.showModal();
                }}
              >
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
                    d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
                  />
                </svg>
                Project Settings
              </button>
            )}
          </li>
          <li>
            <button
              className="flex items-center gap-2"
              onClick={() => {
                (document.activeElement as HTMLElement)?.blur();
                createModalRef.current?.showModal();
              }}
            >
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
                  d="M12 4.5v15m7.5-7.5h-15"
                />
              </svg>
              New Project
            </button>
          </li>
        </ul>
      </div>
      <CreateProjectModal
        modalRef={createModalRef}
        onCreated={handleProjectCreated}
      />
      <ProjectSettingsModal
        modalRef={settingsModalRef}
        project={currentProject}
        onUpdated={handleProjectUpdated}
        onDeleted={handleProjectDeleted}
      />
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
    <dialog ref={modalRef} className="modal">
      <div className="modal-box w-96">
        <div className="card">
          <figure className="relative w-full h-64">
            <div className="bg-gray-200 w-full h-full flex items-center justify-center">
              <span className="text-4xl">
                {user?.username?.[0]?.toUpperCase()}
              </span>
            </div>
          </figure>
          <div className="card-body py-2">
            <h2 className="card-title text-2xl">{user?.username}</h2>
            <ul className="text-left">
              <li>Full Name: {user?.full_name}</li>
            </ul>
            <div className="modal-action">
              <form method="dialog">
                <button className="btn">Close</button>
              </form>
            </div>
          </div>
        </div>
      </div>
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
      <div className="flex flex-1 md:gap-1 lg:gap-2">
        <HiddenIcon />
        <ProjectSelector />
      </div>
      <div className="dropdown dropdown-end">
        <div
          tabIndex={0}
          role="button"
          className="btn btn-ghost btn-circle avatar"
        >
          <div className="relative w-10 h-10 rounded-full shadow overflow-hidden">
            <div className="bg-gray-200 w-full h-full flex items-center justify-center">
              <span className="text-2xl">
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
