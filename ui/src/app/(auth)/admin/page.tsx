"use client";

import { useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import type {
  UserListItem,
  SystemRole,
  ProjectListItem,
  MemberItem,
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
} from "@/client/admin/admin";
import { useRegisterUser, useResetPassword } from "@/client/auth/auth";
import { SettingsCard } from "@/components/features/setting/SettingsCard";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { AdminPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useAuth } from "@/contexts/AuthContext";

export default function AdminPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"users" | "projects" | "system">(
    "users",
  );
  const [selectedUser, setSelectedUser] = useState<UserListItem | null>(null);
  const [selectedProject, setSelectedProject] =
    useState<ProjectListItem | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isDeleteProjectModalOpen, setIsDeleteProjectModalOpen] =
    useState(false);
  const [isMembersModalOpen, setIsMembersModalOpen] = useState(false);

  const { data: usersData, isLoading, error } = useListAllUsers();
  const {
    data: projectsData,
    isLoading: projectsLoading,
    error: projectsError,
  } = useListAllProjects();
  const updateUserMutation = useUpdateUserSettings();
  const deleteUserMutation = useDeleteUser();
  const registerUserMutation = useRegisterUser();
  const deleteProjectMutation = useAdminDeleteProject();
  const addMemberMutation = useAddProjectMemberAdmin();
  const removeMemberMutation = useRemoveProjectMemberAdmin();
  const createProjectMutation = useCreateProjectForUser();

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

  const handleUpdateUser = async (updates: {
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

  const handleCreateUser = async (userData: {
    username: string;
    password: string;
    full_name?: string;
  }) => {
    try {
      await registerUserMutation.mutateAsync({ data: userData });
      queryClient.invalidateQueries({ queryKey: getListAllUsersQueryKey() });
      queryClient.invalidateQueries({ queryKey: getListAllProjectsQueryKey() });
      setIsCreateModalOpen(false);
    } catch (err) {
      console.error("Failed to create user:", err);
      throw err;
    }
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

  const handleAddMember = async (username: string) => {
    if (!selectedProject) return;

    await addMemberMutation.mutateAsync({
      projectId: selectedProject.project_id,
      data: { username },
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
            {(error as Error)?.message ||
              (projectsError as Error)?.message ||
              "Unknown error"}
          </span>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="Admin Panel"
        description="Manage users, projects, and system settings"
      />

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
            <div className="flex justify-between items-center mb-4">
              <h2 className="card-title">User Management</h2>
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

            {/* Mobile card view */}
            <div className="sm:hidden space-y-3">
              {usersData?.data?.users.map((userItem: UserListItem) => (
                <div
                  key={userItem.username}
                  className="card bg-base-100 shadow-sm"
                >
                  <div className="card-body p-4">
                    <div className="flex justify-between items-start">
                      <div>
                        <h3 className="font-mono font-medium">
                          {userItem.username}
                        </h3>
                        <p className="text-sm text-base-content/60">
                          {userItem.full_name || "-"}
                        </p>
                      </div>
                      <div className="flex flex-col gap-1 items-end">
                        <span
                          className={`badge badge-sm ${
                            userItem.system_role === "admin"
                              ? "badge-primary"
                              : "badge-ghost"
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
                          <span className="badge badge-success badge-sm">
                            Has Project
                          </span>
                        ) : (
                          <button
                            className="btn btn-xs btn-primary"
                            onClick={() =>
                              handleCreateProject(userItem.username)
                            }
                            disabled={createProjectMutation.isPending}
                          >
                            {createProjectMutation.isPending ? (
                              <span className="loading loading-spinner loading-xs"></span>
                            ) : (
                              "Add Project"
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
            </div>

            {/* Desktop table view */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="table table-zebra">
                <thead>
                  <tr>
                    <th>Username</th>
                    <th>Full Name</th>
                    <th>System Role</th>
                    <th>Project</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {usersData?.data?.users.map((userItem: UserListItem) => (
                    <tr key={userItem.username}>
                      <td className="font-mono">{userItem.username}</td>
                      <td>{userItem.full_name || "-"}</td>
                      <td>
                        <span
                          className={`badge ${
                            userItem.system_role === "admin"
                              ? "badge-primary"
                              : "badge-ghost"
                          }`}
                        >
                          {userItem.system_role}
                        </span>
                      </td>
                      <td>
                        {userItem.default_project_id ? (
                          <span className="badge badge-success badge-sm">
                            Has Project
                          </span>
                        ) : (
                          <button
                            className="btn btn-xs btn-primary"
                            onClick={() =>
                              handleCreateProject(userItem.username)
                            }
                            disabled={createProjectMutation.isPending}
                          >
                            {createProjectMutation.isPending ? (
                              <span className="loading loading-spinner loading-xs"></span>
                            ) : (
                              "Add Project"
                            )}
                          </button>
                        )}
                      </td>
                      <td>
                        <span
                          className={`badge ${
                            userItem.disabled ? "badge-error" : "badge-success"
                          }`}
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
                <div
                  key={project.project_id}
                  className="card bg-base-100 shadow-sm"
                >
                  <div className="card-body p-4">
                    <div className="flex justify-between items-start">
                      <div>
                        <h3 className="font-medium">{project.name}</h3>
                        {project.description && (
                          <p className="text-xs text-base-content/60">
                            {project.description}
                          </p>
                        )}
                      </div>
                      <span className="badge badge-ghost badge-sm">
                        {project.member_count} members
                      </span>
                    </div>
                    <div className="text-sm text-base-content/60 mt-1">
                      <span className="font-mono">
                        {project.owner_username}
                      </span>
                      {project.created_at && (
                        <span className="ml-2">
                          · {new Date(project.created_at).toLocaleDateString()}
                        </span>
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
                  {projectsData?.data?.projects.map(
                    (project: ProjectListItem) => (
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
                          <span className="badge badge-ghost">
                            {project.member_count}
                          </span>
                        </td>
                        <td className="text-sm text-base-content/60">
                          {project.created_at
                            ? new Date(project.created_at).toLocaleDateString()
                            : "-"}
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
                    ),
                  )}
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
              <span className="font-bold">{selectedUser.username}</span>? This
              action cannot be undone.
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

      {/* Create User Modal */}
      {isCreateModalOpen && (
        <CreateUserModal
          onClose={() => setIsCreateModalOpen(false)}
          onSave={handleCreateUser}
          isLoading={registerUserMutation.isPending}
          error={registerUserMutation.error}
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
              This will also remove all project memberships. This action cannot
              be undone.
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
          isAddingMember={addMemberMutation.isPending}
          isRemovingMember={removeMemberMutation.isPending}
          addMemberError={addMemberMutation.error}
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
  onSave: (updates: { disabled?: boolean; system_role?: SystemRole }) => void;
  isLoading: boolean;
}) {
  const [disabled, setDisabled] = useState(user.disabled ?? false);
  const [systemRole, setSystemRole] = useState<SystemRole>(
    user.system_role ?? "user",
  );
  const isSelf = user.username === currentUsername;
  const [showPasswordReset, setShowPasswordReset] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  const resetPasswordMutation = useResetPassword();

  const handleSave = () => {
    onSave({
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
                {disabled && (
                  <span className="text-error ml-2">(User cannot login)</span>
                )}
              </span>
            </label>
          </div>

          {/* System Role */}
          <div className="form-control">
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
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={isLoading}
          >
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
    password: string;
    full_name?: string;
  }) => Promise<void>;
  isLoading: boolean;
  error: Error | unknown | null;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const handleSave = async () => {
    setLocalError(null);

    if (!username.trim()) {
      setLocalError("Username is required");
      return;
    }
    if (!password.trim()) {
      setLocalError("Password is required");
      return;
    }
    if (password.length < 4) {
      setLocalError("Password must be at least 4 characters");
      return;
    }

    try {
      await onSave({
        username: username.trim(),
        password,
        full_name: fullName.trim() || undefined,
      });
    } catch {
      // Error is handled by the mutation
    }
  };

  const displayError =
    localError ||
    (error ? "Failed to create user. Username may already exist." : null);

  return (
    <dialog className="modal modal-open">
      <div className="modal-box">
        <h3 className="font-bold text-lg mb-4">Create New User</h3>

        {displayError && (
          <div className="alert alert-error mb-4">
            <span>{displayError}</span>
          </div>
        )}

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
              <span className="label-text font-medium">Password *</span>
            </label>
            <input
              type="password"
              className="input input-bordered w-full"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
            />
          </div>

          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">Full Name</span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Enter full name (optional)"
            />
            <label className="label">
              <span className="label-text-alt text-base-content/60">
                A default project will be created for this user
              </span>
            </label>
          </div>
        </div>

        <div className="modal-action">
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={isLoading}
          >
            {isLoading ? (
              <span className="loading loading-spinner loading-sm"></span>
            ) : (
              "Create User"
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

// Members Modal Component
function MembersModal({
  project,
  users,
  onClose,
  onAddMember,
  onRemoveMember,
  isAddingMember,
  isRemovingMember,
  addMemberError,
}: {
  project: ProjectListItem;
  users: UserListItem[];
  onClose: () => void;
  onAddMember: (username: string) => Promise<void>;
  onRemoveMember: (username: string) => Promise<void>;
  isAddingMember: boolean;
  isRemovingMember: boolean;
  addMemberError: Error | unknown | null;
}) {
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [selectedUsername, setSelectedUsername] = useState("");
  const [removingUsername, setRemovingUsername] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

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

  const handleAddMember = async () => {
    setLocalError(null);

    if (!selectedUsername) {
      setLocalError("Please select a user");
      return;
    }

    try {
      await onAddMember(selectedUsername);
      setSelectedUsername("");
      setIsAddModalOpen(false);
      refetch();
    } catch {
      // Error is handled by the mutation
    }
  };

  const handleRemoveMember = async (username: string) => {
    setRemovingUsername(username);
    await onRemoveMember(username);
    setRemovingUsername(null);
    refetch();
  };

  const getRoleBadgeClass = (role: string) => {
    switch (role) {
      case "owner":
        return "badge-secondary";
      case "viewer":
        return "badge-ghost";
      default:
        return "badge-ghost";
    }
  };

  return (
    <dialog className="modal modal-open">
      <div className="modal-box max-w-2xl">
        <h3 className="font-bold text-lg mb-4">Members of {project.name}</h3>

        {membersLoading ? (
          <div className="flex justify-center py-8">
            <span className="loading loading-spinner loading-lg"></span>
          </div>
        ) : (
          <>
            <div className="flex justify-between items-center mb-4">
              <span className="text-sm text-base-content/60">
                {members.length} member{members.length !== 1 ? "s" : ""}
              </span>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => setIsAddModalOpen(true)}
              >
                Add Member
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="table table-zebra">
                <thead>
                  <tr>
                    <th>Username</th>
                    <th>Full Name</th>
                    <th>Role</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {members.map((member: MemberItem) => (
                    <tr key={member.username}>
                      <td className="font-mono">{member.username}</td>
                      <td>{member.full_name || "-"}</td>
                      <td>
                        <span
                          className={`badge ${getRoleBadgeClass(member.role)}`}
                        >
                          {member.role}
                        </span>
                      </td>
                      <td>
                        {member.role !== "owner" ? (
                          <button
                            className="btn btn-sm btn-error btn-ghost"
                            onClick={() => handleRemoveMember(member.username)}
                            disabled={
                              isRemovingMember &&
                              removingUsername === member.username
                            }
                          >
                            {isRemovingMember &&
                            removingUsername === member.username ? (
                              <span className="loading loading-spinner loading-xs"></span>
                            ) : (
                              "Remove"
                            )}
                          </button>
                        ) : (
                          <span className="text-xs text-base-content/60">
                            Owner
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {members.length === 0 && (
                    <tr>
                      <td
                        colSpan={4}
                        className="text-center text-base-content/60"
                      >
                        No members found
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}

        <div className="modal-action">
          <button className="btn" onClick={onClose}>
            Close
          </button>
        </div>

        {/* Add Member Sub-Modal */}
        {isAddModalOpen && (
          <dialog className="modal modal-open" style={{ zIndex: 100 }}>
            <div className="modal-box">
              <h3 className="font-bold text-lg mb-4">Add Member as Viewer</h3>

              {(localError || !!addMemberError) && (
                <div className="alert alert-error mb-4">
                  <span>
                    {localError ||
                      (addMemberError as Error)?.message ||
                      "Failed to add member"}
                  </span>
                </div>
              )}

              <div className="space-y-4">
                <div className="form-control">
                  <label className="label">
                    <span className="label-text font-medium">User</span>
                  </label>
                  <select
                    className="select select-bordered ml-2"
                    value={selectedUsername}
                    onChange={(e) => setSelectedUsername(e.target.value)}
                  >
                    <option value="">Select a user...</option>
                    {availableUsers.map((u: UserListItem) => (
                      <option key={u.username} value={u.username}>
                        {u.username}
                        {u.full_name ? ` (${u.full_name})` : ""}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="alert alert-info">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    className="stroke-current shrink-0 w-5 h-5"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                    ></path>
                  </svg>
                  <span className="text-sm">
                    Members are added as viewers with read-only access.
                  </span>
                </div>
              </div>

              <div className="modal-action">
                <button
                  className="btn"
                  onClick={() => setIsAddModalOpen(false)}
                >
                  Cancel
                </button>
                <button
                  className="btn btn-primary"
                  onClick={handleAddMember}
                  disabled={isAddingMember || !selectedUsername}
                >
                  {isAddingMember ? (
                    <span className="loading loading-spinner loading-sm"></span>
                  ) : (
                    "Add as Viewer"
                  )}
                </button>
              </div>
            </div>
            <form method="dialog" className="modal-backdrop">
              <button onClick={() => setIsAddModalOpen(false)}>close</button>
            </form>
          </dialog>
        )}
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}
