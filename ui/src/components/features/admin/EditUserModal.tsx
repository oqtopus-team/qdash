"use client";

import { useState } from "react";

import type { SystemRole, UserListItem } from "@/schemas";

import { useResetPassword } from "@/client/auth/auth";

type EditUserModalProps = {
  user: UserListItem;
  currentUsername?: string;
  onClose: () => void;
  onSave: (updates: {
    organization?: string;
    disabled?: boolean;
    system_role?: SystemRole;
  }) => void;
  isLoading: boolean;
};

export function EditUserModal({
  user,
  currentUsername,
  onClose,
  onSave,
  isLoading,
}: EditUserModalProps) {
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
              onChange={(event) => setOrganization(event.target.value)}
              placeholder="Enter organization or affiliation"
            />
          </div>

          <div className="form-control">
            <label className="label cursor-pointer justify-start gap-4">
              <input
                type="checkbox"
                className="toggle toggle-error"
                checked={disabled}
                onChange={(event) => setDisabled(event.target.checked)}
              />
              <span className="label-text">
                Account Disabled
                {disabled && <span className="text-error ml-2">(User cannot login)</span>}
              </span>
            </label>
          </div>

          <div className="form-control flex flex-col gap-1">
            <label className="label">
              <span className="label-text font-medium">System Role</span>
            </label>
            <select
              className="select select-bordered"
              value={systemRole}
              onChange={(event) => setSystemRole(event.target.value as SystemRole)}
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
            <div className="space-y-3 rounded-lg bg-base-300 p-4">
              <h4 className="text-sm font-medium">Reset Password</h4>

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
                  onChange={(event) => setNewPassword(event.target.value)}
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
                    <span className="loading loading-spinner loading-xs" />
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
            {isLoading ? <span className="loading loading-spinner loading-sm" /> : "Save Changes"}
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}
