"use client";

import { FolderPlus, Plus, Search, Trash2, Upload, UserPlus } from "lucide-react";

import type { UserListItem } from "@/schemas";

type UserRoleFilter = "all" | "admin" | "user";
type UserProjectFilter = "all" | "with" | "without";

type AdminUsersPanelProps = {
  users: UserListItem[];
  filteredUsers: UserListItem[];
  selectedUsers: UserListItem[];
  selectedUsernames: string[];
  bulkProjectCandidates: UserListItem[];
  userSearch: string;
  userRoleFilter: UserRoleFilter;
  userProjectFilter: UserProjectFilter;
  currentUsername?: string;
  allSelectableUsersSelected: boolean;
  selectableFilteredUsersCount: number;
  bulkAction: "delete" | "create-project" | null;
  isCreatingProject: boolean;
  onSearchChange: (value: string) => void;
  onRoleFilterChange: (value: UserRoleFilter) => void;
  onProjectFilterChange: (value: UserProjectFilter) => void;
  onOpenBulkImport: () => void;
  onOpenCreateUser: () => void;
  onSetBulkDeleteTargets: (users: UserListItem[]) => void;
  onBulkCreateProjects: () => void;
  onOpenAssignProject: () => void;
  onClearSelection: () => void;
  onToggleSelectAll: () => void;
  onToggleUserSelection: (username: string) => void;
  onCreateProject: (username: string) => void;
  onEditUser: (user: UserListItem) => void;
  onDeleteUser: (user: UserListItem) => void;
};

function isUserSelectable(user: UserListItem, currentUsername?: string) {
  return user.system_role !== "admin" && user.username !== currentUsername;
}

function UserStatusBadges({ user }: { user: UserListItem }) {
  return (
    <>
      <span
        className={`badge badge-sm ${user.system_role === "admin" ? "badge-primary" : "badge-ghost"}`}
      >
        {user.system_role}
      </span>
      <span className={`badge badge-sm ${user.disabled ? "badge-error" : "badge-success"}`}>
        {user.disabled ? "Disabled" : "Active"}
      </span>
    </>
  );
}

export function AdminUsersPanel({
  users,
  filteredUsers,
  selectedUsers,
  selectedUsernames,
  bulkProjectCandidates,
  userSearch,
  userRoleFilter,
  userProjectFilter,
  currentUsername,
  allSelectableUsersSelected,
  selectableFilteredUsersCount,
  bulkAction,
  isCreatingProject,
  onSearchChange,
  onRoleFilterChange,
  onProjectFilterChange,
  onOpenBulkImport,
  onOpenCreateUser,
  onSetBulkDeleteTargets,
  onBulkCreateProjects,
  onOpenAssignProject,
  onClearSelection,
  onToggleSelectAll,
  onToggleUserSelection,
  onCreateProject,
  onEditUser,
  onDeleteUser,
}: AdminUsersPanelProps) {
  return (
    <div className="card bg-base-200 shadow-lg">
      <div className="card-body">
        <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <h2 className="card-title">User Management</h2>
          <div className="flex flex-wrap gap-2">
            <button className="btn btn-outline btn-sm" onClick={onOpenBulkImport}>
              <Upload className="h-4 w-4" />
              Bulk Import
            </button>
            <button className="btn btn-primary btn-sm" onClick={onOpenCreateUser}>
              <Plus className="h-4 w-4" />
              Create User
            </button>
          </div>
        </div>

        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
          <label className="input input-bordered flex w-full items-center gap-2 sm:min-w-[16rem] sm:flex-1">
            <Search size={16} className="text-base-content/50" />
            <input
              type="text"
              className="grow"
              value={userSearch}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Search username, display name, organization"
              aria-label="Search users"
            />
          </label>
          <select
            className="select select-bordered w-full sm:w-auto"
            value={userRoleFilter}
            onChange={(event) => onRoleFilterChange(event.target.value as UserRoleFilter)}
            aria-label="Filter by role"
          >
            <option value="all">All roles</option>
            <option value="admin">Admins</option>
            <option value="user">Users</option>
          </select>
          <select
            className="select select-bordered w-full sm:w-auto"
            value={userProjectFilter}
            onChange={(event) => onProjectFilterChange(event.target.value as UserProjectFilter)}
            aria-label="Filter by default project"
          >
            <option value="all">All projects</option>
            <option value="with">Has default project</option>
            <option value="without">No default project</option>
          </select>
          <span className="text-sm text-base-content/70 sm:ml-auto">
            Showing {filteredUsers.length} of {users.length} users
          </span>
        </div>

        {selectedUsers.length > 0 && (
          <div className="alert alert-info mb-4 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="font-medium">{selectedUsers.length} selected</span>
              <span className="text-sm opacity-80">
                {bulkProjectCandidates.length} can get a default project
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="btn btn-sm btn-error"
                onClick={() => onSetBulkDeleteTargets(selectedUsers)}
                disabled={bulkAction !== null}
              >
                <Trash2 size={16} />
                Delete Selected
              </button>
              <button
                className="btn btn-sm btn-primary"
                onClick={onBulkCreateProjects}
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
                onClick={onOpenAssignProject}
                disabled={bulkAction !== null}
              >
                <UserPlus size={16} />
                Assign To Project
              </button>
              <button className="btn btn-sm btn-ghost" onClick={onClearSelection}>
                Clear
              </button>
            </div>
          </div>
        )}

        <div className="space-y-3 sm:hidden">
          <label className="flex items-center gap-3 rounded-box border border-base-300 bg-base-100 px-3 py-2">
            <input
              type="checkbox"
              className="checkbox checkbox-sm"
              checked={allSelectableUsersSelected}
              onChange={onToggleSelectAll}
              disabled={selectableFilteredUsersCount === 0}
            />
            <span className="text-sm font-medium">Select all removable users in view</span>
          </label>

          {filteredUsers.map((userItem) => (
            <div key={userItem.username} className="card bg-base-100 shadow-sm">
              <div className="card-body p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      className="checkbox checkbox-sm mt-1"
                      checked={selectedUsernames.includes(userItem.username)}
                      disabled={!isUserSelectable(userItem, currentUsername)}
                      onChange={() => onToggleUserSelection(userItem.username)}
                    />
                    <div>
                      <h3 className="font-mono font-medium">{userItem.username}</h3>
                      <p className="text-sm text-base-content/60">{userItem.display_name || "-"}</p>
                      <p className="text-xs text-base-content/50">
                        {userItem.organization || "No organization"}
                      </p>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <UserStatusBadges user={userItem} />
                  </div>
                </div>
                <div className="mt-2 flex items-center justify-between border-t border-base-300 pt-2">
                  <div>
                    {userItem.default_project_id ? (
                      <span className="badge badge-success badge-sm">Default Project</span>
                    ) : (
                      <button
                        className="btn btn-xs btn-primary"
                        onClick={() => onCreateProject(userItem.username)}
                        disabled={isCreatingProject}
                      >
                        {isCreatingProject ? (
                          <span className="loading loading-spinner loading-xs" />
                        ) : (
                          "Create Default"
                        )}
                      </button>
                    )}
                  </div>
                  <div className="flex gap-1">
                    <button className="btn btn-xs btn-ghost" onClick={() => onEditUser(userItem)}>
                      Edit
                    </button>
                    <button
                      className="btn btn-xs btn-error btn-outline"
                      onClick={() => onDeleteUser(userItem)}
                      disabled={userItem.username === currentUsername}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
          {filteredUsers.length === 0 && (
            <div className="rounded-box border border-dashed border-base-300 bg-base-100 p-6 text-center text-sm text-base-content/60">
              No users match the current filters.
            </div>
          )}
        </div>

        <div className="hidden overflow-x-auto sm:block">
          <table className="table table-zebra">
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    className="checkbox checkbox-sm"
                    checked={allSelectableUsersSelected}
                    onChange={onToggleSelectAll}
                    disabled={selectableFilteredUsersCount === 0}
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
              {filteredUsers.map((userItem) => (
                <tr key={userItem.username}>
                  <td>
                    <input
                      type="checkbox"
                      className="checkbox checkbox-sm"
                      checked={selectedUsernames.includes(userItem.username)}
                      disabled={!isUserSelectable(userItem, currentUsername)}
                      onChange={() => onToggleUserSelection(userItem.username)}
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
                        onClick={() => onCreateProject(userItem.username)}
                        disabled={isCreatingProject}
                      >
                        {isCreatingProject ? (
                          <span className="loading loading-spinner loading-xs" />
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
                      <button className="btn btn-sm btn-ghost" onClick={() => onEditUser(userItem)}>
                        Edit
                      </button>
                      <button
                        className="btn btn-sm btn-error btn-outline"
                        onClick={() => onDeleteUser(userItem)}
                        disabled={userItem.username === currentUsername}
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
  );
}
