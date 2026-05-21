"use client";

import type { ProjectListItem, UserListItem } from "@/schemas";

type DeleteUserDialogProps = {
  user: UserListItem;
  isLoading: boolean;
  onClose: () => void;
  onConfirm: () => void;
};

export function DeleteUserDialog({ user, isLoading, onClose, onConfirm }: DeleteUserDialogProps) {
  return (
    <dialog className="modal modal-open">
      <div className="modal-box">
        <h3 className="font-bold text-lg">Confirm Delete</h3>
        <p className="py-4">
          Are you sure you want to delete user <span className="font-bold">{user.username}</span>?
          This action cannot be undone.
        </p>
        <div className="modal-action">
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-error" onClick={onConfirm} disabled={isLoading}>
            {isLoading ? <span className="loading loading-spinner loading-sm" /> : "Delete"}
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}

type BulkDeleteUsersDialogProps = {
  users: UserListItem[];
  isLoading: boolean;
  onClose: () => void;
  onConfirm: () => void;
};

export function BulkDeleteUsersDialog({
  users,
  isLoading,
  onClose,
  onConfirm,
}: BulkDeleteUsersDialogProps) {
  return (
    <dialog className="modal modal-open">
      <div className="modal-box">
        <h3 className="font-bold text-lg">Delete Selected Users</h3>
        <p className="py-4">
          Delete {users.length} selected user{users.length !== 1 ? "s" : ""}?
        </p>
        <p className="text-sm text-base-content/60">
          Owned projects and project memberships for these users will also be removed.
        </p>
        <div className="card mt-4 bg-base-200">
          <div className="card-body p-3">
            <div className="text-sm font-medium">Targets</div>
            <div className="flex max-h-40 flex-wrap gap-2 overflow-y-auto">
              {users.map((user) => (
                <span key={user.username} className="badge badge-ghost font-mono">
                  {user.username}
                </span>
              ))}
            </div>
          </div>
        </div>
        <div className="modal-action">
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-error" onClick={onConfirm} disabled={isLoading}>
            {isLoading ? <span className="loading loading-spinner loading-sm" /> : "Delete Users"}
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}

type DeleteProjectDialogProps = {
  project: ProjectListItem;
  isLoading: boolean;
  onClose: () => void;
  onConfirm: () => void;
};

export function DeleteProjectDialog({
  project,
  isLoading,
  onClose,
  onConfirm,
}: DeleteProjectDialogProps) {
  return (
    <dialog className="modal modal-open">
      <div className="modal-box">
        <h3 className="font-bold text-lg">Confirm Delete Project</h3>
        <p className="py-4">
          Are you sure you want to delete project <span className="font-bold">{project.name}</span>?
        </p>
        <p className="text-sm text-base-content/60">
          This will also remove all project memberships. This action cannot be undone.
        </p>
        <div className="modal-action">
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-error" onClick={onConfirm} disabled={isLoading}>
            {isLoading ? <span className="loading loading-spinner loading-sm" /> : "Delete"}
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}
