"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/Dialog";
import type { SystemRole, UserListItem } from "@/schemas";

import { useResetPassword } from "@/client/auth/auth";
import { getApiErrorMessage } from "@/lib/utils/apiError";

type EditUserModalProps = {
  user: UserListItem;
  currentUsername?: string;
  onClose: () => void;
  onSave: (updates: {
    organization?: string;
    disabled?: boolean;
    system_role?: SystemRole;
  }) => Promise<void>;
  isLoading: boolean;
};

/** Zod schema for the edit user form. */
const editUserSchema = z.object({
  organization: z.string().trim(),
  disabled: z.boolean(),
  systemRole: z.enum(["user", "admin"], { error: "Select a system role" }),
});

type EditUserFormInput = z.input<typeof editUserSchema>;
type EditUserFormData = z.output<typeof editUserSchema>;

/** Modal for editing a user's organization, disabled state, system role, and password. */
export function EditUserModal({
  user,
  currentUsername,
  onClose,
  onSave,
  isLoading,
}: EditUserModalProps) {
  const isSelf = user.username === currentUsername;
  const [showPasswordReset, setShowPasswordReset] = useState(false);
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<EditUserFormInput, unknown, EditUserFormData>({
    resolver: zodResolver(editUserSchema),
    defaultValues: {
      organization: user.organization ?? "",
      disabled: user.disabled ?? false,
      systemRole: user.system_role ?? "user",
    },
  });
  const disabled = watch("disabled");

  const resetPasswordMutation = useResetPassword();
  const isPending = isLoading || isSubmitting || resetPasswordMutation.isPending;

  /** Submits the validated form values and surfaces a save failure as a server error. */
  const handleSave = async (data: EditUserFormData) => {
    setServerError(null);
    try {
      await onSave({
        organization: data.organization,
        disabled: data.disabled,
        system_role: data.systemRole,
      });
    } catch (err) {
      setServerError(getApiErrorMessage(err, "Failed to update user"));
    }
  };

  /** Generates a temporary password for the user. */
  const handleResetPassword = async () => {
    setPasswordError(null);
    setPasswordSuccess(false);

    try {
      const response = await resetPasswordMutation.mutateAsync({
        data: { username: user.username },
      });
      setTemporaryPassword(response.data.initial_password);
      setPasswordSuccess(true);
    } catch (err) {
      setPasswordError(getApiErrorMessage(err, "Failed to reset password"));
    }
  };

  /** Copies the temporary password to the clipboard. */
  const handleCopyPassword = async () => {
    if (!temporaryPassword) return;
    await navigator.clipboard.writeText(temporaryPassword);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Dialog open onOpenChange={(open) => !open && !isPending && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogTitle className="mb-4">Edit User: {user.username}</DialogTitle>

        <form className="space-y-4" onSubmit={handleSubmit(handleSave)} noValidate>
          <div className="form-control">
            <label className="label" htmlFor="edit-user-organization">
              <span className="label-text font-medium">Organization</span>
            </label>
            <input
              id="edit-user-organization"
              type="text"
              className={`input input-bordered w-full ${errors.organization ? "input-error" : ""}`}
              placeholder="Enter organization or affiliation"
              aria-invalid={Boolean(errors.organization)}
              aria-describedby={errors.organization ? "edit-user-organization-error" : undefined}
              {...register("organization")}
            />
            {errors.organization && (
              <p id="edit-user-organization-error" className="mt-1 text-sm text-error">
                {errors.organization.message}
              </p>
            )}
          </div>

          <div className="form-control">
            <label
              className="label cursor-pointer justify-start gap-4"
              htmlFor="edit-user-disabled"
            >
              <input
                id="edit-user-disabled"
                type="checkbox"
                className="toggle toggle-error"
                {...register("disabled")}
              />
              <span className="label-text">
                Account Disabled
                {disabled && <span className="text-error ml-2">(User cannot login)</span>}
              </span>
            </label>
          </div>

          <div className="form-control flex flex-col gap-1">
            <label className="label" htmlFor="edit-user-system-role">
              <span className="label-text font-medium">System Role</span>
            </label>
            <select
              id="edit-user-system-role"
              className={`select select-bordered ${errors.systemRole ? "select-error" : ""}`}
              disabled={isSelf}
              aria-invalid={Boolean(errors.systemRole)}
              aria-describedby={
                errors.systemRole
                  ? "edit-user-system-role-hint edit-user-system-role-error"
                  : "edit-user-system-role-hint"
              }
              {...register("systemRole")}
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
            {errors.systemRole && (
              <p id="edit-user-system-role-error" className="mt-1 text-sm text-error">
                {errors.systemRole.message}
              </p>
            )}
            <label className="label">
              <span id="edit-user-system-role-hint" className="label-text-alt text-base-content/60">
                {isSelf
                  ? "You cannot change your own system role"
                  : "Admin users can manage all users and system settings"}
              </span>
            </label>
          </div>

          <div className="divider">Password</div>

          {!showPasswordReset ? (
            <button
              type="button"
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
              <h4 className="text-sm font-medium">Generate Temporary Password</h4>

              {passwordError && (
                <div className="alert alert-error py-2" role="alert">
                  <span className="text-sm">{passwordError}</span>
                </div>
              )}

              {passwordSuccess && (
                <div className="alert alert-success py-2">
                  <span className="text-sm">
                    Password reset. Share this temporary password securely.
                  </span>
                </div>
              )}

              {temporaryPassword && (
                <div className="space-y-1">
                  <div className="join w-full">
                    <input
                      className="input input-bordered input-sm join-item w-full font-mono"
                      value={temporaryPassword}
                      readOnly
                      aria-label="Temporary password"
                    />
                    <button
                      type="button"
                      className={`btn btn-sm join-item ${copied ? "btn-success" : "btn-primary"}`}
                      onClick={handleCopyPassword}
                    >
                      {copied ? "Copied" : "Copy"}
                    </button>
                  </div>
                  <p className="text-xs text-base-content/60">
                    This password is shown only once. The user must change it after signing in.
                  </p>
                </div>
              )}

              {!passwordSuccess && (
                <p className="text-sm text-base-content/70">
                  This invalidates the current password. The generated password is shown only once,
                  and the user must change it after signing in.
                </p>
              )}

              <div className="flex gap-2">
                <button
                  type="button"
                  className="btn btn-warning btn-sm"
                  onClick={handleResetPassword}
                  disabled={resetPasswordMutation.isPending || passwordSuccess}
                >
                  {resetPasswordMutation.isPending ? (
                    <span className="loading loading-spinner loading-xs" />
                  ) : (
                    "Generate and Reset"
                  )}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    setShowPasswordReset(false);
                    setTemporaryPassword(null);
                    setCopied(false);
                    setPasswordError(null);
                    setPasswordSuccess(false);
                  }}
                  disabled={resetPasswordMutation.isPending}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {serverError && (
            <div className="alert alert-error py-2" role="alert">
              <span className="text-sm">{serverError}</span>
            </div>
          )}

          <div className="modal-action">
            <button type="button" className="btn" onClick={onClose} disabled={isPending}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={isPending}>
              {isLoading ? <span className="loading loading-spinner loading-sm" /> : "Save Changes"}
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
