"use client";

import { useState } from "react";

import { useQueryClient } from "@tanstack/react-query";
import { Download, FolderPlus, Info, Search, Trash2, Upload, UserPlus, X } from "lucide-react";

import type {
  UserListItem,
  SystemRole,
  ProjectRole,
  ProjectListItem,
  MemberItem,
  BulkUserImportResponse,
} from "@/schemas";

import {
  useListAllUsers,
  useUpdateUserSettings,
  useDeleteUser,
  getListAllUsersQueryKey,
  useListAllProjects,
  useAdminDeleteProject,
  getListAllProjectsQueryKey,
  useListProjectMembersAdmin,
  useAddProjectMemberAdmin,
  useRemoveProjectMemberAdmin,
  useCreateProjectForUser,
  useBulkImportUsers,
} from "@/client/admin/admin";
import { useRegisterUser, useResetPassword } from "@/client/auth/auth";
import { SettingsCard } from "@/components/features/settings/SettingsCard";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { AdminPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useAuth } from "@/contexts/AuthContext";
import { formatDate } from "@/lib/utils/datetime";

export function AdminPageContent() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"users" | "projects" | "system">("users");
  const [selectedUser, setSelectedUser] = useState<UserListItem | null>(null);
  const [selectedProject, setSelectedProject] = useState<ProjectListItem | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isBulkImportModalOpen, setIsBulkImportModalOpen] = useState(false);
  const [isDeleteProjectModalOpen, setIsDeleteProjectModalOpen] = useState(false);
  const [isMembersModalOpen, setIsMembersModalOpen] = useState(false);
  const [selectedUsernames, setSelectedUsernames] = useState<string[]>([]);
  const [userSearch, setUserSearch] = useState("");
  const [userRoleFilter, setUserRoleFilter] = useState<"all" | "admin" | "user">("all");
  const [userProjectFilter, setUserProjectFilter] = useState<"all" | "with" | "without">("all");
  const [bulkDeleteTargets, setBulkDeleteTargets] = useState<UserListItem[]>([]);
  const [bulkAction, setBulkAction] = useState<"delete" | "create-project" | null>(null);
  const [bulkFeedback, setBulkFeedback] = useState<{
    tone: "success" | "warning" | "error";
    message: string;
  } | null>(null);
  const [isAssignProjectModalOpen, setIsAssignProjectModalOpen] = useState(false);

  const { data: usersData, isLoading, error } = useListAllUsers();
  const {
    data: projectsData,
    isLoading: projectsLoading,
    error: projectsError,
  } = useListAllProjects();
  const updateUserMutation = useUpdateUserSettings();
  const deleteUserMutation = useDeleteUser();
  const registerUserMutation = useRegisterUser();
  const bulkImportMutation = useBulkImportUsers();
  const deleteProjectMutation = useAdminDeleteProject();
  const addMemberMutation = useAddProjectMemberAdmin();
  const removeMemberMutation = useRemoveProjectMemberAdmin();
  const createProjectMutation = useCreateProjectForUser();

  const allUsers = usersData?.data?.users ?? [];
  const filteredUsers = allUsers.filter((userItem) => {
    const normalizedSearch = userSearch.trim().toLowerCase();
    const matchesSearch =
      normalizedSearch.length === 0 ||
      userItem.username.toLowerCase().includes(normalizedSearch) ||
      (userItem.display_name ?? "").toLowerCase().includes(normalizedSearch) ||
      (userItem.organization ?? "").toLowerCase().includes(normalizedSearch);
    const matchesRole = userRoleFilter === "all" || userItem.system_role === userRoleFilter;
    const hasDefaultProject = !!userItem.default_project_id;
    const matchesProject =
      userProjectFilter === "all" ||
      (userProjectFilter === "with" && hasDefaultProject) ||
      (userProjectFilter === "without" && !hasDefaultProject);
    return matchesSearch && matchesRole && matchesProject;
  });
  const selectableFilteredUsers = filteredUsers.filter(
    (userItem) => userItem.system_role !== "admin" && userItem.username !== user?.username,
  );
  const selectedUsers = allUsers.filter((userItem) =>
    selectedUsernames.includes(userItem.username),
  );
  const bulkProjectCandidates = selectedUsers.filter((userItem) => !userItem.default_project_id);
  const allSelectableUsersSelected =
    selectableFilteredUsers.length > 0 &&
    selectableFilteredUsers.every((userItem) => selectedUsernames.includes(userItem.username));

  // Check if current user is admin
  if (user?.system_role !== "admin") {
    return (
      <PageContainer>
        <div className="alert alert-error">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="stroke-current shrink-0 h-6 w-6"
            fill="none"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>Access denied. Admin privileges required.</span>
        </div>
      </PageContainer>
    );
  }

  const handleEdit = (userItem: UserListItem) => {
    setSelectedUser(userItem);
    setIsEditModalOpen(true);
  };

  const handleDelete = (userItem: UserListItem) => {
    setSelectedUser(userItem);
    setIsDeleteModalOpen(true);
  };

  const handleToggleUserSelection = (username: string) => {
    setSelectedUsernames((current) =>
      current.includes(username)
        ? current.filter((item) => item !== username)
        : [...current, username],
    );
  };

  const handleToggleSelectAllUsers = () => {
    if (allSelectableUsersSelected) {
      setSelectedUsernames((current) =>
        current.filter(
          (username) => !selectableFilteredUsers.some((userItem) => userItem.username === username),
        ),
      );
      return;
    }

    setSelectedUsernames((current) => {
      const next = new Set(current);
      selectableFilteredUsers.forEach((userItem) => next.add(userItem.username));
      return Array.from(next);
    });
  };

  const clearUserSelection = () => {
    setSelectedUsernames([]);
  };

  const handleUpdateUser = async (updates: {
    organization?: string;
    disabled?: boolean;
    system_role?: SystemRole;
  }) => {
    if (!selectedUser) return;

    try {
      await updateUserMutation.mutateAsync({
        username: selectedUser.username,
        data: updates,
      });
      queryClient.invalidateQueries({ queryKey: getListAllUsersQueryKey() });
      setIsEditModalOpen(false);
      setSelectedUser(null);
    } catch (err) {
      console.error("Failed to update user:", err);
    }
  };

  const handleConfirmDelete = async () => {
    if (!selectedUser) return;

    try {
      await deleteUserMutation.mutateAsync({ username: selectedUser.username });
      queryClient.invalidateQueries({ queryKey: getListAllUsersQueryKey() });
      setIsDeleteModalOpen(false);
      setSelectedUser(null);
    } catch (err) {
      console.error("Failed to delete user:", err);
    }
  };

  const handleBulkDeleteUsers = async () => {
    if (bulkDeleteTargets.length === 0) return;

    setBulkAction("delete");
    const deleted: string[] = [];
    const failed: string[] = [];

    for (const userItem of bulkDeleteTargets) {
      try {
        await deleteUserMutation.mutateAsync({ username: userItem.username });
        deleted.push(userItem.username);
      } catch {
        failed.push(userItem.username);
      }
    }

    await queryClient.invalidateQueries({ queryKey: getListAllUsersQueryKey() });
    await queryClient.invalidateQueries({ queryKey: getListAllProjectsQueryKey() });

    setBulkDeleteTargets([]);
    setSelectedUsernames((current) => current.filter((username) => !deleted.includes(username)));
    setBulkAction(null);

    if (failed.length === 0) {
      setBulkFeedback({
        tone: "success",
        message: `Deleted ${deleted.length} user${deleted.length !== 1 ? "s" : ""}.`,
      });
      return;
    }

    setBulkFeedback({
      tone: deleted.length > 0 ? "warning" : "error",
      message:
        deleted.length > 0
          ? `Deleted ${deleted.length} users. ${failed.length} failed: ${failed.join(", ")}`
          : `Failed to delete selected users: ${failed.join(", ")}`,
    });
  };

  const handleCreateUser = async (userData: {
    username: string;
    display_name?: string;
    organization?: string;
    create_default_project?: boolean;
  }): Promise<string | null> => {
    try {
      const response = await registerUserMutation.mutateAsync({
        data: userData,
      });
      queryClient.invalidateQueries({ queryKey: getListAllUsersQueryKey() });
      queryClient.invalidateQueries({ queryKey: getListAllProjectsQueryKey() });
      return response.data.initial_password ?? null;
    } catch (err) {
      console.error("Failed to create user:", err);
      throw err;
    }
  };

  const handleBulkImportUsers = async (file: File): Promise<BulkUserImportResponse> => {
    const response = await bulkImportMutation.mutateAsync({
      data: { file: file as unknown as string },
    });
    queryClient.invalidateQueries({ queryKey: getListAllUsersQueryKey() });
    queryClient.invalidateQueries({ queryKey: getListAllProjectsQueryKey() });
    return response.data;
  };

  const handleDeleteProject = (project: ProjectListItem) => {
    setSelectedProject(project);
    setIsDeleteProjectModalOpen(true);
  };

  const handleConfirmDeleteProject = async () => {
    if (!selectedProject) return;

    try {
      await deleteProjectMutation.mutateAsync({
        projectId: selectedProject.project_id,
      });
      queryClient.invalidateQueries({ queryKey: getListAllProjectsQueryKey() });
      setIsDeleteProjectModalOpen(false);
      setSelectedProject(null);
    } catch (err) {
      console.error("Failed to delete project:", err);
    }
  };

  const handleManageMembers = (project: ProjectListItem) => {
    setSelectedProject(project);
    setIsMembersModalOpen(true);
  };

  const handleCreateProject = async (username: string) => {
    try {
      await createProjectMutation.mutateAsync({ username });
      queryClient.invalidateQueries({ queryKey: getListAllUsersQueryKey() });
      queryClient.invalidateQueries({ queryKey: getListAllProjectsQueryKey() });
    } catch (err) {
      console.error("Failed to create project:", err);
    }
  };

  const handleBulkCreateProjects = async () => {
    if (bulkProjectCandidates.length === 0) return;

    setBulkAction("create-project");
    const created: string[] = [];
    const failed: string[] = [];

    for (const userItem of bulkProjectCandidates) {
      try {
        await createProjectMutation.mutateAsync({ username: userItem.username });
        created.push(userItem.username);
      } catch {
        failed.push(userItem.username);
      }
    }

    await queryClient.invalidateQueries({ queryKey: getListAllUsersQueryKey() });
    await queryClient.invalidateQueries({ queryKey: getListAllProjectsQueryKey() });

    setBulkAction(null);
    setBulkFeedback({
      tone: failed.length === 0 ? "success" : created.length > 0 ? "warning" : "error",
      message:
        failed.length === 0
          ? `Created default project for ${created.length} user${created.length !== 1 ? "s" : ""}.`
          : created.length > 0
            ? `Created ${created.length} default projects. ${failed.length} failed: ${failed.join(", ")}`
            : `Failed to create default projects: ${failed.join(", ")}`,
    });
  };

  const handleAddMember = async (username: string, role: ProjectRole) => {
    if (!selectedProject) return;

    await addMemberMutation.mutateAsync({
      projectId: selectedProject.project_id,
      data: { username, role },
    });
    queryClient.invalidateQueries({ queryKey: getListAllProjectsQueryKey() });
  };

  const handleRemoveMember = async (username: string) => {
    if (!selectedProject) return;

    await removeMemberMutation.mutateAsync({
      projectId: selectedProject.project_id,
      username,
    });
    queryClient.invalidateQueries({ queryKey: getListAllProjectsQueryKey() });
  };

  if (isLoading || projectsLoading) {
    return <AdminPageSkeleton />;
  }

  if (error || projectsError) {
    return (
      <PageContainer>
        <div className="alert alert-error">
          <span>
            Failed to load data:{" "}
            {(error as Error)?.message || (projectsError as Error)?.message || "Unknown error"}
          </span>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader title="Admin Panel" description="Manage users, projects, and system settings" />

      {bulkFeedback && (
        <div
          className={`alert mb-4 ${
            bulkFeedback.tone === "success"
              ? "alert-success"
              : bulkFeedback.tone === "warning"
                ? "alert-warning"
                : "alert-error"
          }`}
          role="status"
        >
          <span className="flex-1">{bulkFeedback.message}</span>
          <button
            type="button"
            aria-label="Dismiss notification"
            className="btn btn-ghost btn-xs btn-square"
            onClick={() => setBulkFeedback(null)}
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* Tabs */}
      <div className="tabs tabs-boxed mb-4 sm:mb-6 w-full sm:w-fit">
        <button
          className={`tab ${activeTab === "users" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("users")}
        >
          Users ({usersData?.data?.total || 0})
        </button>
        <button
          className={`tab ${activeTab === "projects" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("projects")}
        >
          Projects ({projectsData?.data?.total || 0})
        </button>
        <button
          className={`tab ${activeTab === "system" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("system")}
        >
          System
        </button>
      </div>

      {/* Users Tab */}
      {activeTab === "users" && (
        <div className="card bg-base-200 shadow-lg">
          <div className="card-body">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
              <h2 className="card-title">User Management</h2>
              <div className="flex flex-wrap gap-2">
                <button
                  className="btn btn-outline btn-sm"
                  onClick={() => setIsBulkImportModalOpen(true)}
                >
                  <Upload className="h-4 w-4" />
                  Bulk Import
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => setIsCreateModalOpen(true)}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-4 w-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 4v16m8-8H4"
                    />
                  </svg>
                  Create User
                </button>
              </div>
            </div>

            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
              <label className="input input-bordered flex items-center gap-2 w-full sm:flex-1 sm:min-w-[16rem]">
                <Search size={16} className="text-base-content/50" />
                <input
                  type="text"
                  className="grow"
                  value={userSearch}
                  onChange={(event) => setUserSearch(event.target.value)}
                  placeholder="Search username, display name, organization"
                  aria-label="Search users"
                />
              </label>
              <select
                className="select select-bordered w-full sm:w-auto"
                value={userRoleFilter}
                onChange={(event) =>
                  setUserRoleFilter(event.target.value as "all" | "admin" | "user")
                }
                aria-label="Filter by role"
              >
                <option value="all">All roles</option>
                <option value="admin">Admins</option>
                <option value="user">Users</option>
              </select>
              <select
                className="select select-bordered w-full sm:w-auto"
                value={userProjectFilter}
                onChange={(event) =>
                  setUserProjectFilter(event.target.value as "all" | "with" | "without")
                }
                aria-label="Filter by default project"
              >
                <option value="all">All projects</option>
                <option value="with">Has default project</option>
                <option value="without">No default project</option>
              </select>
              <span className="text-sm text-base-content/70 sm:ml-auto">
                Showing {filteredUsers.length} of {allUsers.length} users
              </span>
            </div>

            {selectedUsers.length > 0 && (
              <div className="mb-4 alert alert-info flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="font-medium">{selectedUsers.length} selected</span>
                  <span className="text-sm opacity-80">
                    {bulkProjectCandidates.length} can get a default project
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="btn btn-sm btn-error"
                    onClick={() => setBulkDeleteTargets(selectedUsers)}
                    disabled={bulkAction !== null}
                  >
                    <Trash2 size={16} />
                    Delete Selected
                  </button>
                  <button
                    className="btn btn-sm btn-primary"
                    onClick={handleBulkCreateProjects}
                    disabled={bulkAction !== null || bulkProjectCandidates.length === 0}
                  >
                    {bulkAction === "create-project" ? (
                      <span className="loading loading-spinner loading-xs" />
                    ) : (
                      <FolderPlus size={16} />
                    )}
                    Create Default Projects
                  </button>
                  <button
                    className="btn btn-sm btn-outline"
                    onClick={() => setIsAssignProjectModalOpen(true)}
                    disabled={bulkAction !== null}
                  >
                    <UserPlus size={16} />
                    Assign To Project
                  </button>
                  <button className="btn btn-sm btn-ghost" onClick={clearUserSelection}>
                    Clear
                  </button>
                </div>
              </div>
            )}

            {/* Mobile card view */}
            <div className="sm:hidden space-y-3">
              <label className="flex items-center gap-3 bg-base-100 rounded-box border border-base-300 px-3 py-2">
                <input
                  type="checkbox"
                  className="checkbox checkbox-sm"
                  checked={allSelectableUsersSelected}
                  onChange={handleToggleSelectAllUsers}
                  disabled={selectableFilteredUsers.length === 0}
                />
                <span className="text-sm font-medium">Select all removable users in view</span>
              </label>

              {filteredUsers.map((userItem: UserListItem) => (
                <div key={userItem.username} className="card bg-base-100 shadow-sm">
                  <div className="card-body p-4">
                    <div className="flex justify-between items-start">
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          className="checkbox checkbox-sm mt-1"
                          checked={selectedUsernames.includes(userItem.username)}
                          disabled={
                            userItem.system_role === "admin" || userItem.username === user?.username
                          }
                          onChange={() => handleToggleUserSelection(userItem.username)}
                        />
                        <div>
                          <h3 className="font-mono font-medium">{userItem.username}</h3>
                          <p className="text-sm text-base-content/60">
                            {userItem.display_name || "-"}
                          </p>
                          <p className="text-xs text-base-content/50">
                            {userItem.organization || "No organization"}
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-col gap-1 items-end">
                        <span
                          className={`badge badge-sm ${
                            userItem.system_role === "admin" ? "badge-primary" : "badge-ghost"
                          }`}
                        >
                          {userItem.system_role}
                        </span>
                        <span
                          className={`badge badge-sm ${
                            userItem.disabled ? "badge-error" : "badge-success"
                          }`}
                        >
                          {userItem.disabled ? "Disabled" : "Active"}
                        </span>
                      </div>
                    </div>
                    <div className="flex justify-between items-center mt-2 pt-2 border-t border-base-300">
                      <div>
                        {userItem.default_project_id ? (
                          <span className="badge badge-success badge-sm">Default Project</span>
                        ) : (
                          <button
                            className="btn btn-xs btn-primary"
                            onClick={() => handleCreateProject(userItem.username)}
                            disabled={createProjectMutation.isPending}
                          >
                            {createProjectMutation.isPending ? (
                              <span className="loading loading-spinner loading-xs"></span>
                            ) : (
                              "Create Default"
                            )}
                          </button>
                        )}
                      </div>
                      <div className="flex gap-1">
                        <button
                          className="btn btn-xs btn-ghost"
                          onClick={() => handleEdit(userItem)}
                        >
                          Edit
                        </button>
                        <button
                          className="btn btn-xs btn-error btn-ghost"
                          onClick={() => handleDelete(userItem)}
                          disabled={userItem.username === user?.username}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
              {filteredUsers.length === 0 && (
                <div className="bg-base-100 rounded-box border border-dashed border-base-300 p-6 text-center text-sm text-base-content/60">
                  No users match the current filters.
                </div>
              )}
            </div>

            {/* Desktop table view */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="table table-zebra">
                <thead>
                  <tr>
                    <th>
                      <input
                        type="checkbox"
                        className="checkbox checkbox-sm"
                        checked={allSelectableUsersSelected}
                        onChange={handleToggleSelectAllUsers}
                        disabled={selectableFilteredUsers.length === 0}
                      />
                    </th>
                    <th>Username</th>
                    <th>Display Name</th>
                    <th>Organization</th>
                    <th>System Role</th>
                    <th>Default Project</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.map((userItem: UserListItem) => (
                    <tr key={userItem.username}>
                      <td>
                        <input
                          type="checkbox"
                          className="checkbox checkbox-sm"
                          checked={selectedUsernames.includes(userItem.username)}
                          disabled={
                            userItem.system_role === "admin" || userItem.username === user?.username
                          }
                          onChange={() => handleToggleUserSelection(userItem.username)}
                        />
                      </td>
                      <td className="font-mono">{userItem.username}</td>
                      <td>{userItem.display_name || "-"}</td>
                      <td>{userItem.organization || "-"}</td>
                      <td>
                        <span
                          className={`badge ${
                            userItem.system_role === "admin" ? "badge-primary" : "badge-ghost"
                          }`}
                        >
                          {userItem.system_role}
                        </span>
                      </td>
                      <td>
                        {userItem.default_project_id ? (
                          <span className="badge badge-success badge-sm">Default Project</span>
                        ) : (
                          <button
                            className="btn btn-xs btn-primary"
                            onClick={() => handleCreateProject(userItem.username)}
                            disabled={createProjectMutation.isPending}
                          >
                            {createProjectMutation.isPending ? (
                              <span className="loading loading-spinner loading-xs"></span>
                            ) : (
                              "Create Default"
                            )}
                          </button>
                        )}
                      </td>
                      <td>
                        <span
                          className={`badge ${userItem.disabled ? "badge-error" : "badge-success"}`}
                        >
                          {userItem.disabled ? "Disabled" : "Active"}
                        </span>
                      </td>
                      <td>
                        <div className="flex gap-2">
                          <button
                            className="btn btn-sm btn-ghost"
                            onClick={() => handleEdit(userItem)}
                          >
                            Edit
                          </button>
                          <button
                            className="btn btn-sm btn-error btn-ghost"
                            onClick={() => handleDelete(userItem)}
                            disabled={userItem.username === user?.username}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {filteredUsers.length === 0 && (
                    <tr>
                      <td colSpan={8} className="text-center text-base-content/60">
                        No users match the current filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Projects Tab */}
      {activeTab === "projects" && (
        <div className="card bg-base-200 shadow-lg">
          <div className="card-body">
            <div className="flex justify-between items-center mb-4">
              <h2 className="card-title">Project Management</h2>
            </div>

            {/* Mobile card view */}
            <div className="sm:hidden space-y-3">
              {projectsData?.data?.projects.map((project: ProjectListItem) => (
                <div key={project.project_id} className="card bg-base-100 shadow-sm">
                  <div className="card-body p-4">
                    <div className="flex justify-between items-start">
                      <div>
                        <h3 className="font-medium">{project.name}</h3>
                        {project.description && (
                          <p className="text-xs text-base-content/60">{project.description}</p>
                        )}
                      </div>
                      <span className="badge badge-ghost badge-sm">
                        {project.member_count} members
                      </span>
                    </div>
                    <div className="text-sm text-base-content/60 mt-1">
                      <span className="font-mono">{project.owner_username}</span>
                      {project.created_at && (
                        <span className="ml-2">· {formatDate(project.created_at)}</span>
                      )}
                    </div>
                    <div className="flex justify-end gap-1 mt-2 pt-2 border-t border-base-300">
                      <button
                        className="btn btn-xs btn-ghost"
                        onClick={() => handleManageMembers(project)}
                      >
                        Members
                      </button>
                      {project.owner_username === user?.username ? (
                        <span
                          className="btn btn-xs btn-ghost btn-disabled opacity-50"
                          title="Cannot delete your own project"
                        >
                          Delete
                        </span>
                      ) : (
                        <button
                          className="btn btn-xs btn-error btn-ghost"
                          onClick={() => handleDeleteProject(project)}
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Desktop table view */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="table table-zebra">
                <thead>
                  <tr>
                    <th>Project Name</th>
                    <th>Owner</th>
                    <th>Members</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {projectsData?.data?.projects.map((project: ProjectListItem) => (
                    <tr key={project.project_id}>
                      <td>
                        <div>
                          <div className="font-medium">{project.name}</div>
                          {project.description && (
                            <div className="text-xs text-base-content/60">
                              {project.description}
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="font-mono">{project.owner_username}</td>
                      <td>
                        <span className="badge badge-ghost">{project.member_count}</span>
                      </td>
                      <td className="text-sm text-base-content/60">
                        {formatDate(project.created_at)}
                      </td>
                      <td>
                        <div className="flex gap-2">
                          <button
                            className="btn btn-sm btn-ghost"
                            onClick={() => handleManageMembers(project)}
                          >
                            Members
                          </button>
                          {project.owner_username === user?.username ? (
                            <span
                              className="btn btn-sm btn-ghost btn-disabled opacity-50"
                              title="Cannot delete your own project"
                            >
                              Delete
                            </span>
                          ) : (
                            <button
                              className="btn btn-sm btn-error btn-ghost"
                              onClick={() => handleDeleteProject(project)}
                            >
                              Delete
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* System Tab */}
      {activeTab === "system" && <SettingsCard />}

      {/* Edit Modal */}
      {isEditModalOpen && selectedUser && (
        <EditUserModal
          user={selectedUser}
          currentUsername={user?.username}
          onClose={() => {
            setIsEditModalOpen(false);
            setSelectedUser(null);
          }}
          onSave={handleUpdateUser}
          isLoading={updateUserMutation.isPending}
        />
      )}

      {/* Delete Confirmation Modal */}
      {isDeleteModalOpen && selectedUser && (
        <dialog className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Confirm Delete</h3>
            <p className="py-4">
              Are you sure you want to delete user{" "}
              <span className="font-bold">{selectedUser.username}</span>? This action cannot be
              undone.
            </p>
            <div className="modal-action">
              <button
                className="btn"
                onClick={() => {
                  setIsDeleteModalOpen(false);
                  setSelectedUser(null);
                }}
              >
                Cancel
              </button>
              <button
                className="btn btn-error"
                onClick={handleConfirmDelete}
                disabled={deleteUserMutation.isPending}
              >
                {deleteUserMutation.isPending ? (
                  <span className="loading loading-spinner loading-sm"></span>
                ) : (
                  "Delete"
                )}
              </button>
            </div>
          </div>
          <form method="dialog" className="modal-backdrop">
            <button
              onClick={() => {
                setIsDeleteModalOpen(false);
                setSelectedUser(null);
              }}
            >
              close
            </button>
          </form>
        </dialog>
      )}

      {bulkDeleteTargets.length > 0 && (
        <dialog className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Delete Selected Users</h3>
            <p className="py-4">
              Delete {bulkDeleteTargets.length} selected user
              {bulkDeleteTargets.length !== 1 ? "s" : ""}?
            </p>
            <p className="text-sm text-base-content/60">
              Owned projects and project memberships for these users will also be removed.
            </p>
            <div className="mt-4 card bg-base-200">
              <div className="card-body p-3">
                <div className="text-sm font-medium">Targets</div>
                <div className="flex flex-wrap gap-2 max-h-40 overflow-y-auto">
                  {bulkDeleteTargets.map((userItem) => (
                    <span key={userItem.username} className="badge badge-ghost font-mono">
                      {userItem.username}
                    </span>
                  ))}
                </div>
              </div>
            </div>
            <div className="modal-action">
              <button className="btn" onClick={() => setBulkDeleteTargets([])}>
                Cancel
              </button>
              <button
                className="btn btn-error"
                onClick={handleBulkDeleteUsers}
                disabled={bulkAction === "delete"}
              >
                {bulkAction === "delete" ? (
                  <span className="loading loading-spinner loading-sm" />
                ) : (
                  "Delete Users"
                )}
              </button>
            </div>
          </div>
          <form method="dialog" className="modal-backdrop">
            <button onClick={() => setBulkDeleteTargets([])}>close</button>
          </form>
        </dialog>
      )}

      {/* Create User Modal */}
      {isCreateModalOpen && (
        <CreateUserModal
          onClose={() => setIsCreateModalOpen(false)}
          onSave={handleCreateUser}
          isLoading={registerUserMutation.isPending}
          error={registerUserMutation.error}
        />
      )}

      {isBulkImportModalOpen && (
        <BulkImportUsersModal
          onClose={() => setIsBulkImportModalOpen(false)}
          onImport={handleBulkImportUsers}
          isLoading={bulkImportMutation.isPending}
          error={bulkImportMutation.error}
        />
      )}

      {/* Delete Project Confirmation Modal */}
      {isDeleteProjectModalOpen && selectedProject && (
        <dialog className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Confirm Delete Project</h3>
            <p className="py-4">
              Are you sure you want to delete project{" "}
              <span className="font-bold">{selectedProject.name}</span>?
            </p>
            <p className="text-sm text-base-content/60">
              This will also remove all project memberships. This action cannot be undone.
            </p>
            <div className="modal-action">
              <button
                className="btn"
                onClick={() => {
                  setIsDeleteProjectModalOpen(false);
                  setSelectedProject(null);
                }}
              >
                Cancel
              </button>
              <button
                className="btn btn-error"
                onClick={handleConfirmDeleteProject}
                disabled={deleteProjectMutation.isPending}
              >
                {deleteProjectMutation.isPending ? (
                  <span className="loading loading-spinner loading-sm"></span>
                ) : (
                  "Delete"
                )}
              </button>
            </div>
          </div>
          <form method="dialog" className="modal-backdrop">
            <button
              onClick={() => {
                setIsDeleteProjectModalOpen(false);
                setSelectedProject(null);
              }}
            >
              close
            </button>
          </form>
        </dialog>
      )}

      {/* Members Management Modal */}
      {isMembersModalOpen && selectedProject && (
        <MembersModal
          project={selectedProject}
          users={usersData?.data?.users || []}
          onClose={() => {
            setIsMembersModalOpen(false);
            setSelectedProject(null);
          }}
          onAddMember={handleAddMember}
          onRemoveMember={handleRemoveMember}
          isRemovingMember={removeMemberMutation.isPending}
          addMemberError={addMemberMutation.error}
        />
      )}

      {isAssignProjectModalOpen && (
        <AssignUsersToProjectModal
          users={selectedUsers}
          projects={projectsData?.data?.projects || []}
          onClose={() => setIsAssignProjectModalOpen(false)}
          onAssign={async (projectId, role, usernames) => {
            const added: string[] = [];
            const failed: string[] = [];

            for (const username of usernames) {
              try {
                await addMemberMutation.mutateAsync({
                  projectId,
                  data: { username, role },
                });
                added.push(username);
              } catch {
                failed.push(username);
              }
            }

            await queryClient.invalidateQueries({ queryKey: getListAllProjectsQueryKey() });

            setBulkFeedback({
              tone: failed.length === 0 ? "success" : added.length > 0 ? "warning" : "error",
              message:
                failed.length === 0
                  ? `Assigned ${added.length} user${added.length !== 1 ? "s" : ""} to the project as ${role}.`
                  : added.length > 0
                    ? `Assigned ${added.length} users. ${failed.length} failed: ${failed.join(", ")}`
                    : `Failed to assign selected users: ${failed.join(", ")}`,
            });
          }}
          isLoading={addMemberMutation.isPending}
          error={addMemberMutation.error}
        />
      )}
    </PageContainer>
  );
}

// Edit User Modal Component
function EditUserModal({
  user,
  currentUsername,
  onClose,
  onSave,
  isLoading,
}: {
  user: UserListItem;
  currentUsername?: string;
  onClose: () => void;
  onSave: (updates: {
    organization?: string;
    disabled?: boolean;
    system_role?: SystemRole;
  }) => void;
  isLoading: boolean;
}) {
  const [organization, setOrganization] = useState(user.organization ?? "");
  const [disabled, setDisabled] = useState(user.disabled ?? false);
  const [systemRole, setSystemRole] = useState<SystemRole>(user.system_role ?? "user");
  const isSelf = user.username === currentUsername;
  const [showPasswordReset, setShowPasswordReset] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  const resetPasswordMutation = useResetPassword();

  const handleSave = () => {
    onSave({
      organization: organization.trim(),
      disabled,
      system_role: systemRole,
    });
  };

  const handleResetPassword = async () => {
    setPasswordError(null);
    setPasswordSuccess(false);

    if (!newPassword.trim()) {
      setPasswordError("Password is required");
      return;
    }
    if (newPassword.length < 4) {
      setPasswordError("Password must be at least 4 characters");
      return;
    }

    try {
      await resetPasswordMutation.mutateAsync({
        data: {
          username: user.username,
          new_password: newPassword,
        },
      });
      setPasswordSuccess(true);
      setNewPassword("");
      setTimeout(() => {
        setShowPasswordReset(false);
        setPasswordSuccess(false);
      }, 2000);
    } catch {
      setPasswordError("Failed to reset password");
    }
  };

  return (
    <dialog className="modal modal-open">
      <div className="modal-box max-w-2xl">
        <h3 className="font-bold text-lg mb-4">Edit User: {user.username}</h3>

        <div className="space-y-4">
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">Organization</span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              value={organization}
              onChange={(e) => setOrganization(e.target.value)}
              placeholder="Enter organization or affiliation"
            />
          </div>

          {/* Status */}
          <div className="form-control">
            <label className="label cursor-pointer justify-start gap-4">
              <input
                type="checkbox"
                className="toggle toggle-error"
                checked={disabled}
                onChange={(e) => setDisabled(e.target.checked)}
              />
              <span className="label-text">
                Account Disabled
                {disabled && <span className="text-error ml-2">(User cannot login)</span>}
              </span>
            </label>
          </div>

          {/* System Role */}
          <div className="form-control flex flex-col gap-1">
            <label className="label">
              <span className="label-text font-medium">System Role</span>
            </label>
            <select
              className="select select-bordered"
              value={systemRole}
              onChange={(e) => setSystemRole(e.target.value as SystemRole)}
              disabled={isSelf}
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
            <label className="label">
              <span className="label-text-alt text-base-content/60">
                {isSelf
                  ? "You cannot change your own system role"
                  : "Admin users can manage all users and system settings"}
              </span>
            </label>
          </div>

          {/* Password Reset Section */}
          <div className="divider">Password</div>

          {!showPasswordReset ? (
            <button
              className="btn btn-outline btn-warning btn-sm"
              onClick={() => setShowPasswordReset(true)}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"
                />
              </svg>
              Reset Password
            </button>
          ) : (
            <div className="bg-base-300 p-4 rounded-lg space-y-3">
              <h4 className="font-medium text-sm">Reset Password</h4>

              {passwordError && (
                <div className="alert alert-error py-2">
                  <span className="text-sm">{passwordError}</span>
                </div>
              )}

              {passwordSuccess && (
                <div className="alert alert-success py-2">
                  <span className="text-sm">Password reset successfully!</span>
                </div>
              )}

              <div className="form-control">
                <input
                  type="password"
                  className="input input-bordered input-sm w-full"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Enter new password"
                  disabled={passwordSuccess}
                />
              </div>

              <div className="flex gap-2">
                <button
                  className="btn btn-warning btn-sm"
                  onClick={handleResetPassword}
                  disabled={resetPasswordMutation.isPending || passwordSuccess}
                >
                  {resetPasswordMutation.isPending ? (
                    <span className="loading loading-spinner loading-xs"></span>
                  ) : (
                    "Confirm Reset"
                  )}
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    setShowPasswordReset(false);
                    setNewPassword("");
                    setPasswordError(null);
                  }}
                  disabled={resetPasswordMutation.isPending}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="modal-action">
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={handleSave} disabled={isLoading}>
            {isLoading ? (
              <span className="loading loading-spinner loading-sm"></span>
            ) : (
              "Save Changes"
            )}
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}

// Create User Modal Component
function CreateUserModal({
  onClose,
  onSave,
  isLoading,
  error,
}: {
  onClose: () => void;
  onSave: (userData: {
    username: string;
    display_name?: string;
    organization?: string;
    create_default_project?: boolean;
  }) => Promise<string | null>;
  isLoading: boolean;
  error: Error | unknown | null;
}) {
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [organization, setOrganization] = useState("");
  const [createDefaultProject, setCreateDefaultProject] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleSave = async () => {
    setLocalError(null);

    if (!username.trim()) {
      setLocalError("Username is required");
      return;
    }

    try {
      const generatedPassword = await onSave({
        username: username.trim(),
        display_name: displayName.trim() || undefined,
        organization: organization.trim() || undefined,
        create_default_project: createDefaultProject,
      });
      setTemporaryPassword(generatedPassword);
    } catch {
      // Error is handled by the mutation
    }
  };

  const handleCopyPassword = async () => {
    if (!temporaryPassword) return;
    await navigator.clipboard.writeText(temporaryPassword);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const displayError =
    localError || (error ? "Failed to create user. Username may already exist." : null);

  return (
    <dialog className="modal modal-open">
      <div className="modal-box">
        <h3 className="font-bold text-lg mb-4">Create New User</h3>

        {displayError && (
          <div className="alert alert-error mb-4">
            <span>{displayError}</span>
          </div>
        )}

        {temporaryPassword ? (
          <div className="space-y-4">
            <div className="alert alert-success">
              <span>
                User <span className="font-mono font-semibold">{username}</span> was created. Share
                this temporary password securely.
              </span>
            </div>
            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">Temporary Password</span>
              </label>
              <div className="join w-full">
                <input
                  className="input input-bordered join-item w-full font-mono"
                  value={temporaryPassword}
                  readOnly
                />
                <button
                  type="button"
                  className={`btn join-item ${copied ? "btn-success" : "btn-primary"}`}
                  onClick={handleCopyPassword}
                >
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
              <label className="label">
                <span className="label-text-alt text-base-content/60">
                  This password is shown only once. The user must change it after signing in.
                </span>
              </label>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">Username *</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter username"
              />
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">Display Name</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Enter display name (optional)"
              />
              <label className="label">
                <span className="label-text-alt text-base-content/60">
                  A temporary password will be generated for this user
                </span>
              </label>
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">Organization</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                value={organization}
                onChange={(e) => setOrganization(e.target.value)}
                placeholder="Enter organization or affiliation (optional)"
              />
            </div>
            <label className="form-control cursor-pointer rounded-lg border border-base-300 bg-base-100 p-3">
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary mt-1"
                  checked={createDefaultProject}
                  onChange={(event) => setCreateDefaultProject(event.target.checked)}
                />
                <div>
                  <div className="font-medium">Create default project</div>
                  <div className="text-sm text-base-content/60">
                    Provision a personal project for this user and set it as their default project.
                  </div>
                </div>
              </div>
            </label>
          </div>
        )}

        <div className="modal-action">
          <button className="btn" onClick={onClose}>
            {temporaryPassword ? "Close" : "Cancel"}
          </button>
          {!temporaryPassword && (
            <button className="btn btn-primary" onClick={handleSave} disabled={isLoading}>
              {isLoading ? (
                <span className="loading loading-spinner loading-sm"></span>
              ) : (
                "Create User"
              )}
            </button>
          )}
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}

function csvEscape(value: unknown): string {
  const text = value == null ? "" : String(value);
  if (/[",\n\r]/.test(text)) {
    return `"${text.split('"').join('""')}"`;
  }
  return text;
}

function buildBulkImportResultCsv(result: BulkUserImportResponse): string {
  const headers = [
    "row_number",
    "username",
    "display_name",
    "organization",
    "system_role",
    "initial_password",
    "status",
    "message",
  ];
  const rows = result.results.map((row) =>
    [
      row.row_number,
      row.username,
      row.display_name,
      row.organization,
      row.system_role,
      row.initial_password,
      row.status,
      row.message,
    ]
      .map(csvEscape)
      .join(","),
  );
  return [headers.join(","), ...rows].join("\n");
}

function downloadBulkImportResult(result: BulkUserImportResponse) {
  const csv = buildBulkImportResultCsv(result);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `qdash-user-import-${formatDate(new Date().toISOString())}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function BulkImportUsersModal({
  onClose,
  onImport,
  isLoading,
  error,
}: {
  onClose: () => void;
  onImport: (file: File) => Promise<BulkUserImportResponse>;
  isLoading: boolean;
  error: Error | unknown | null;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<BulkUserImportResponse | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const handleImport = async () => {
    setLocalError(null);
    if (!file) {
      setLocalError("CSV file is required");
      return;
    }

    try {
      const importResult = await onImport(file);
      setResult(importResult);
    } catch {
      // Error is shown from mutation state.
    }
  };

  const displayError = localError || (error ? "Failed to import users from CSV." : null);

  return (
    <dialog className="modal modal-open">
      <div className="modal-box max-w-4xl">
        <h3 className="font-bold text-lg mb-4">Bulk Import Users</h3>

        {displayError && (
          <div className="alert alert-error mb-4">
            <span>{displayError}</span>
          </div>
        )}

        {result ? (
          <div className="space-y-4">
            <div className="stats stats-vertical sm:stats-horizontal w-full bg-base-200">
              <div className="stat">
                <div className="stat-title">Created</div>
                <div className="stat-value text-success">{result.created}</div>
              </div>
              <div className="stat">
                <div className="stat-title">Skipped</div>
                <div className="stat-value">{result.skipped}</div>
              </div>
              <div className="stat">
                <div className="stat-title">Failed</div>
                <div className="stat-value text-error">{result.failed}</div>
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-base-300">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>Row</th>
                    <th>Username</th>
                    <th>Organization</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {result.results.map((row) => (
                    <tr key={`${row.row_number}-${row.username}`}>
                      <td>{row.row_number}</td>
                      <td className="font-mono">{row.username || "-"}</td>
                      <td>{row.organization || "-"}</td>
                      <td>{row.system_role || "-"}</td>
                      <td>
                        <span
                          className={`badge badge-sm ${
                            row.status === "created"
                              ? "badge-success"
                              : row.status === "failed"
                                ? "badge-error"
                                : "badge-ghost"
                          }`}
                        >
                          {row.status}
                        </span>
                      </td>
                      <td className="max-w-xs truncate">{row.message || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="alert alert-info">
              <span>
                Download the result CSV now. Generated passwords are not stored in plain text and
                cannot be shown again later.
              </span>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">CSV File</span>
              </label>
              <input
                type="file"
                accept=".csv,text/csv"
                className="file-input file-input-bordered w-full"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </div>

            <div className="rounded-lg border border-base-300 bg-base-100 p-3">
              <div className="text-sm font-medium">Expected columns</div>
              <pre className="mt-2 overflow-x-auto rounded bg-base-200 p-3 text-xs">
                username,display_name,organization,system_role
                {"\n"}
                alice,Alice Sato,Example Lab,user
                {"\n"}
                bob,Bob Tanaka,Operations,admin
              </pre>
              <p className="mt-2 text-xs text-base-content/60">
                Add users to projects from the Projects tab after importing accounts.
              </p>
            </div>
          </div>
        )}

        <div className="modal-action">
          <button className="btn" onClick={onClose}>
            {result ? "Close" : "Cancel"}
          </button>
          {result ? (
            <button className="btn btn-primary" onClick={() => downloadBulkImportResult(result)}>
              <Download className="h-4 w-4" />
              Download CSV
            </button>
          ) : (
            <button
              className="btn btn-primary"
              onClick={handleImport}
              disabled={isLoading || !file}
            >
              {isLoading ? (
                <span className="loading loading-spinner loading-sm"></span>
              ) : (
                <>
                  <Upload className="h-4 w-4" />
                  Import Users
                </>
              )}
            </button>
          )}
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}

// Members Modal Component
function MembersModal({
  project,
  users,
  onClose,
  onAddMember,
  onRemoveMember,
  isRemovingMember,
  addMemberError,
}: {
  project: ProjectListItem;
  users: UserListItem[];
  onClose: () => void;
  onAddMember: (username: string, role: ProjectRole) => Promise<void>;
  onRemoveMember: (username: string) => Promise<void>;
  isRemovingMember: boolean;
  addMemberError: Error | unknown | null;
}) {
  const [candidateSearch, setCandidateSearch] = useState("");
  const [selectedCandidateUsernames, setSelectedCandidateUsernames] = useState<string[]>([]);
  const [selectedRole, setSelectedRole] = useState<ProjectRole>("viewer");
  const [removingUsername, setRemovingUsername] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [membersFeedback, setMembersFeedback] = useState<{
    tone: "success" | "warning" | "error";
    message: string;
  } | null>(null);
  const [isBulkAdding, setIsBulkAdding] = useState(false);

  // Fetch members for this project
  const {
    data: membersData,
    isLoading: membersLoading,
    refetch,
  } = useListProjectMembersAdmin(project.project_id);

  const members = membersData?.data?.members || [];

  // Filter out users who are already members
  const availableUsers = users.filter(
    (u) => !members.some((m: MemberItem) => m.username === u.username),
  );
  const filteredAvailableUsers = availableUsers.filter((userItem) => {
    const normalizedSearch = candidateSearch.trim().toLowerCase();
    return (
      normalizedSearch.length === 0 ||
      userItem.username.toLowerCase().includes(normalizedSearch) ||
      (userItem.display_name ?? "").toLowerCase().includes(normalizedSearch) ||
      (userItem.organization ?? "").toLowerCase().includes(normalizedSearch)
    );
  });
  const allFilteredCandidatesSelected =
    filteredAvailableUsers.length > 0 &&
    filteredAvailableUsers.every((userItem) =>
      selectedCandidateUsernames.includes(userItem.username),
    );

  const handleToggleCandidate = (username: string) => {
    setSelectedCandidateUsernames((current) =>
      current.includes(username)
        ? current.filter((item) => item !== username)
        : [...current, username],
    );
  };

  const handleToggleAllCandidates = () => {
    if (allFilteredCandidatesSelected) {
      setSelectedCandidateUsernames((current) =>
        current.filter(
          (username) => !filteredAvailableUsers.some((userItem) => userItem.username === username),
        ),
      );
      return;
    }

    setSelectedCandidateUsernames((current) => {
      const next = new Set(current);
      filteredAvailableUsers.forEach((userItem) => next.add(userItem.username));
      return Array.from(next);
    });
  };

  const handleAddMembers = async () => {
    setLocalError(null);
    setMembersFeedback(null);

    if (selectedCandidateUsernames.length === 0) {
      setLocalError("Select at least one user");
      return;
    }

    setIsBulkAdding(true);
    const added: string[] = [];
    const failed: string[] = [];

    try {
      for (const username of selectedCandidateUsernames) {
        try {
          await onAddMember(username, selectedRole);
          added.push(username);
        } catch {
          failed.push(username);
        }
      }

      setSelectedCandidateUsernames((current) =>
        current.filter((username) => !added.includes(username)),
      );
      refetch();
      setMembersFeedback({
        tone: failed.length === 0 ? "success" : added.length > 0 ? "warning" : "error",
        message:
          failed.length === 0
            ? `Added ${added.length} member${added.length !== 1 ? "s" : ""} as ${selectedRole}.`
            : added.length > 0
              ? `Added ${added.length} members. ${failed.length} failed: ${failed.join(", ")}`
              : `Failed to add selected members: ${failed.join(", ")}`,
      });
    } finally {
      setIsBulkAdding(false);
    }
  };

  const handleRemoveMember = async (username: string) => {
    setMembersFeedback(null);
    setRemovingUsername(username);
    await onRemoveMember(username);
    setRemovingUsername(null);
    refetch();
  };

  const getRoleBadgeClass = (role: string) => {
    switch (role) {
      case "owner":
        return "badge-secondary";
      case "editor":
        return "badge-primary";
      case "viewer":
        return "badge-ghost";
      default:
        return "badge-ghost";
    }
  };

  return (
    <dialog className="modal modal-open">
      <div className="modal-box max-w-5xl w-full sm:w-11/12 max-h-[90vh] p-4 sm:p-6">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="font-bold text-lg">Members of {project.name}</h3>
            <p className="text-sm text-base-content/60">
              Add multiple users at once and manage memberships in one place.
            </p>
          </div>
          <span className="badge badge-ghost self-start sm:self-auto">
            {members.length} member{members.length !== 1 ? "s" : ""}
          </span>
        </div>

        {membersFeedback && (
          <div
            className={`alert mb-4 ${
              membersFeedback.tone === "success"
                ? "alert-success"
                : membersFeedback.tone === "warning"
                  ? "alert-warning"
                  : "alert-error"
            }`}
            role="status"
          >
            <span>{membersFeedback.message}</span>
          </div>
        )}

        {membersLoading ? (
          <div className="flex justify-center py-8">
            <span className="loading loading-spinner loading-lg" />
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="card bg-base-100 shadow-sm">
              <div className="card-body p-4">
                <div>
                  <h4 className="font-medium">Current members</h4>
                  <p className="text-sm text-base-content/60">
                    Remove non-owner members from this list.
                  </p>
                </div>

                <div className="overflow-x-auto mt-2">
                  <table className="table table-zebra table-sm">
                    <thead>
                      <tr>
                        <th>Username</th>
                        <th>Role</th>
                        <th className="text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {members.map((member: MemberItem) => (
                        <tr key={member.username}>
                          <td>
                            <div className="font-mono text-sm">{member.username}</div>
                            {member.display_name && (
                              <div className="text-xs text-base-content/60">
                                {member.display_name}
                              </div>
                            )}
                          </td>
                          <td>
                            <span className={`badge badge-sm ${getRoleBadgeClass(member.role)}`}>
                              {member.role}
                            </span>
                          </td>
                          <td className="text-right">
                            {member.role !== "owner" ? (
                              <button
                                className="btn btn-xs btn-ghost btn-error"
                                onClick={() => handleRemoveMember(member.username)}
                                disabled={isRemovingMember && removingUsername === member.username}
                              >
                                {isRemovingMember && removingUsername === member.username ? (
                                  <span className="loading loading-spinner loading-xs" />
                                ) : (
                                  "Remove"
                                )}
                              </button>
                            ) : (
                              <span className="text-xs text-base-content/60">Owner</span>
                            )}
                          </td>
                        </tr>
                      ))}
                      {members.length === 0 && (
                        <tr>
                          <td colSpan={3} className="text-center text-base-content/60">
                            No members found
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <div className="card bg-base-100 shadow-sm">
              <div className="card-body p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h4 className="font-medium">Add members</h4>
                    <p className="text-sm text-base-content/60">
                      Search, select multiple, and add them with one role.
                    </p>
                  </div>
                  <span className="badge badge-outline shrink-0">
                    {availableUsers.length} available
                  </span>
                </div>

                {(localError || !!addMemberError) && (
                  <div className="alert alert-error">
                    <span>
                      {localError || (addMemberError as Error)?.message || "Failed to add member"}
                    </span>
                  </div>
                )}

                <label className="input input-bordered flex items-center gap-2">
                  <Search size={16} className="text-base-content/50" />
                  <input
                    type="text"
                    className="grow"
                    value={candidateSearch}
                    onChange={(event) => setCandidateSearch(event.target.value)}
                    placeholder="Search username, display name, organization"
                    aria-label="Search candidates"
                  />
                </label>

                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      className="checkbox checkbox-sm"
                      checked={allFilteredCandidatesSelected}
                      onChange={handleToggleAllCandidates}
                      disabled={filteredAvailableUsers.length === 0}
                    />
                    <span className="text-sm font-medium">Select all in results</span>
                  </label>
                  <span className="text-sm text-base-content/60">
                    {selectedCandidateUsernames.length} selected
                  </span>
                </div>

                <div className="max-h-[22rem] overflow-y-auto rounded-lg border border-base-300">
                  {filteredAvailableUsers.length === 0 ? (
                    <div className="p-6 text-center text-sm text-base-content/60">
                      No available users match the current search.
                    </div>
                  ) : (
                    <ul className="divide-y divide-base-300">
                      {filteredAvailableUsers.map((userItem) => (
                        <li key={userItem.username}>
                          <label className="flex cursor-pointer items-start gap-3 p-3 hover:bg-base-200">
                            <input
                              type="checkbox"
                              className="checkbox checkbox-sm mt-1"
                              checked={selectedCandidateUsernames.includes(userItem.username)}
                              onChange={() => handleToggleCandidate(userItem.username)}
                            />
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-mono text-sm">{userItem.username}</span>
                                <span
                                  className={`badge badge-sm ${
                                    userItem.system_role === "admin"
                                      ? "badge-primary"
                                      : "badge-ghost"
                                  }`}
                                >
                                  {userItem.system_role}
                                </span>
                              </div>
                              <div className="text-sm text-base-content/70">
                                {userItem.display_name || "No display name"}
                              </div>
                              <div className="text-xs text-base-content/50">
                                {userItem.organization || "No organization"}
                              </div>
                            </div>
                          </label>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="flex flex-col gap-2 sm:flex-row">
                  <select
                    className="select select-bordered sm:w-40"
                    value={selectedRole}
                    onChange={(event) => setSelectedRole(event.target.value as ProjectRole)}
                    aria-label="Role for new members"
                  >
                    <option value="viewer">Viewer</option>
                    <option value="editor">Editor</option>
                  </select>
                  <button
                    className="btn btn-primary sm:flex-1"
                    onClick={handleAddMembers}
                    disabled={isBulkAdding || selectedCandidateUsernames.length === 0}
                  >
                    {isBulkAdding ? (
                      <span className="loading loading-spinner loading-sm" />
                    ) : (
                      <UserPlus size={16} />
                    )}
                    Add Selected
                  </button>
                </div>

                <div className="alert alert-info">
                  <Info size={16} className="shrink-0" />
                  <span className="text-sm">
                    Viewers can read project data. Editors can also operate workflows, notes, chips,
                    and calibration data.
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="modal-action">
          <button className="btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}

function AssignUsersToProjectModal({
  users,
  projects,
  onClose,
  onAssign,
  isLoading,
  error,
}: {
  users: UserListItem[];
  projects: ProjectListItem[];
  onClose: () => void;
  onAssign: (projectId: string, role: ProjectRole, usernames: string[]) => Promise<void>;
  isLoading: boolean;
  error: Error | unknown | null;
}) {
  const [projectSearch, setProjectSearch] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedRole, setSelectedRole] = useState<ProjectRole>("viewer");
  const [localError, setLocalError] = useState<string | null>(null);
  const { data: selectedProjectMembersData, isLoading: selectedProjectMembersLoading } =
    useListProjectMembersAdmin(selectedProjectId);

  const filteredProjects = projects.filter((project) => {
    const normalizedSearch = projectSearch.trim().toLowerCase();
    return (
      normalizedSearch.length === 0 ||
      project.name.toLowerCase().includes(normalizedSearch) ||
      project.owner_username.toLowerCase().includes(normalizedSearch) ||
      project.project_id.toLowerCase().includes(normalizedSearch)
    );
  });
  const selectedProjectMemberUsernames = new Set(
    selectedProjectMembersData?.data?.members.map((member) => member.username) ?? [],
  );
  const assignableUsers = users.filter(
    (user) => !selectedProjectMemberUsernames.has(user.username),
  );
  const alreadyAssignedUsers = users.filter((user) =>
    selectedProjectMemberUsernames.has(user.username),
  );

  const handleAssign = async () => {
    setLocalError(null);

    if (users.length === 0) {
      setLocalError("No users selected");
      return;
    }

    if (!selectedProjectId) {
      setLocalError("Select a project");
      return;
    }

    if (assignableUsers.length === 0) {
      setLocalError("All selected users are already members of this project");
      return;
    }

    await onAssign(
      selectedProjectId,
      selectedRole,
      assignableUsers.map((user) => user.username),
    );
    onClose();
  };

  return (
    <dialog className="modal modal-open">
      <div className="modal-box max-w-4xl w-full sm:w-11/12 max-h-[90vh] p-4 sm:p-6">
        <h3 className="font-bold text-lg">Assign Users To Project</h3>
        <p className="text-sm text-base-content/60 mb-4">
          Add the selected users to one project with the same role in a single action.
        </p>

        {(localError || !!error) && (
          <div className="alert alert-error mb-4">
            <span>{localError || (error as Error)?.message || "Failed to assign users"}</span>
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card bg-base-100 shadow-sm">
            <div className="card-body p-4">
              <div className="flex items-center justify-between gap-2">
                <h4 className="font-medium">Selected users</h4>
                <span className="badge badge-ghost">{users.length}</span>
              </div>
              <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
                {users.map((u) => (
                  <span key={u.username} className="badge badge-ghost font-mono">
                    {u.username}
                  </span>
                ))}
              </div>

              {selectedProjectId && (
                <div className="stats stats-vertical sm:stats-horizontal w-full bg-base-200">
                  <div className="stat py-2 px-3">
                    <div className="stat-title text-xs">Will add</div>
                    <div className="stat-value text-primary text-2xl">
                      {selectedProjectMembersLoading ? "-" : assignableUsers.length}
                    </div>
                  </div>
                  <div className="stat py-2 px-3">
                    <div className="stat-title text-xs">Already member</div>
                    <div className="stat-value text-2xl">
                      {selectedProjectMembersLoading ? "-" : alreadyAssignedUsers.length}
                    </div>
                  </div>
                </div>
              )}

              {selectedProjectId &&
                alreadyAssignedUsers.length > 0 &&
                !selectedProjectMembersLoading && (
                  <div className="rounded-lg bg-base-200 p-3">
                    <div className="mb-2 text-sm font-medium">Skipped (already members)</div>
                    <div className="flex flex-wrap gap-2">
                      {alreadyAssignedUsers.map((u) => (
                        <span key={u.username} className="badge badge-outline font-mono">
                          {u.username}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

              <div className="form-control">
                <label className="label" htmlFor="assign-role">
                  <span className="label-text font-medium">Role</span>
                </label>
                <select
                  id="assign-role"
                  className="select select-bordered w-full"
                  value={selectedRole}
                  onChange={(event) => setSelectedRole(event.target.value as ProjectRole)}
                >
                  <option value="viewer">Viewer</option>
                  <option value="editor">Editor</option>
                </select>
              </div>
            </div>
          </div>

          <div className="card bg-base-100 shadow-sm">
            <div className="card-body p-4">
              <h4 className="font-medium">Target project</h4>
              <label className="input input-bordered flex items-center gap-2">
                <Search size={16} className="text-base-content/50" />
                <input
                  type="text"
                  className="grow"
                  value={projectSearch}
                  onChange={(event) => setProjectSearch(event.target.value)}
                  placeholder="Search project name, owner, or project ID"
                  aria-label="Search projects"
                />
              </label>

              <div className="max-h-[22rem] overflow-y-auto rounded-lg border border-base-300">
                {filteredProjects.length === 0 ? (
                  <div className="p-6 text-center text-sm text-base-content/60">
                    No projects match the current search.
                  </div>
                ) : (
                  <ul className="divide-y divide-base-300">
                    {filteredProjects.map((project) => (
                      <li key={project.project_id}>
                        <label className="flex cursor-pointer items-start gap-3 p-3 hover:bg-base-200">
                          <input
                            type="radio"
                            name="assign-project"
                            className="radio radio-sm mt-1"
                            checked={selectedProjectId === project.project_id}
                            onChange={() => setSelectedProjectId(project.project_id)}
                          />
                          <div className="min-w-0 flex-1">
                            <div className="font-medium">{project.name}</div>
                            <div className="text-sm text-base-content/70">
                              Owner: <span className="font-mono">{project.owner_username}</span>
                            </div>
                            <div className="text-xs text-base-content/50">
                              {project.member_count} members · {project.project_id}
                            </div>
                          </div>
                        </label>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="modal-action">
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleAssign}
            disabled={isLoading || selectedProjectMembersLoading || !selectedProjectId}
          >
            {isLoading || selectedProjectMembersLoading ? (
              <span className="loading loading-spinner loading-sm" />
            ) : (
              "Assign Users"
            )}
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}
