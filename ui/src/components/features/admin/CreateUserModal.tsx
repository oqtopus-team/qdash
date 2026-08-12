"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/Dialog";

type CreateUserModalProps = {
  onClose: () => void;
  onSave: (userData: {
    username: string;
    display_name?: string;
    organization?: string;
    create_default_project?: boolean;
  }) => Promise<string | null>;
  isLoading: boolean;
  error: Error | unknown | null;
};

const createUserSchema = z.object({
  username: z.string().trim().min(1, "Username is required"),
  displayName: z.string().transform((value) => value.trim() || undefined),
  organization: z.string().transform((value) => value.trim() || undefined),
  createDefaultProject: z.boolean(),
});

type CreateUserFormInput = z.input<typeof createUserSchema>;
type CreateUserFormData = z.output<typeof createUserSchema>;

export function CreateUserModal({ onClose, onSave, isLoading, error }: CreateUserModalProps) {
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null);
  const [createdUsername, setCreatedUsername] = useState("");
  const [copied, setCopied] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CreateUserFormInput, unknown, CreateUserFormData>({
    resolver: zodResolver(createUserSchema),
    defaultValues: {
      username: "",
      displayName: "",
      organization: "",
      createDefaultProject: false,
    },
  });

  const handleSave = async (data: CreateUserFormData) => {
    try {
      const generatedPassword = await onSave({
        username: data.username,
        display_name: data.displayName,
        organization: data.organization,
        create_default_project: data.createDefaultProject,
      });
      setCreatedUsername(data.username);
      setTemporaryPassword(generatedPassword);
    } catch {
      // Error is handled by the mutation.
    }
  };

  const handleCopyPassword = async () => {
    if (!temporaryPassword) return;
    await navigator.clipboard.writeText(temporaryPassword);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const displayError = error ? "Failed to create user. Username may already exist." : null;

  return (
    <Dialog open onOpenChange={(open) => !open && !isLoading && onClose()}>
      <DialogContent>
        <DialogTitle className="mb-4">Create New User</DialogTitle>

        {displayError && (
          <div className="alert alert-error mb-4">
            <span>{displayError}</span>
          </div>
        )}

        {temporaryPassword ? (
          <div className="space-y-4">
            <div className="alert alert-success">
              <span>
                User <span className="font-mono font-semibold">{createdUsername}</span> was created.
                Share this temporary password securely.
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
          <form className="space-y-4" onSubmit={handleSubmit(handleSave)} noValidate>
            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">Username *</span>
              </label>
              <input
                type="text"
                className={`input input-bordered w-full ${errors.username ? "input-error" : ""}`}
                placeholder="Enter username"
                autoComplete="username"
                aria-invalid={Boolean(errors.username)}
                aria-describedby={errors.username ? "create-user-username-error" : undefined}
                {...register("username")}
              />
              {errors.username && (
                <p id="create-user-username-error" className="mt-1 text-sm text-error">
                  {errors.username.message}
                </p>
              )}
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">Display Name</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                placeholder="Enter display name (optional)"
                autoComplete="name"
                {...register("displayName")}
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
                placeholder="Enter organization or affiliation (optional)"
                autoComplete="organization"
                {...register("organization")}
              />
            </div>
            <label className="form-control cursor-pointer rounded-lg border border-base-300 bg-base-100 p-3">
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary mt-1"
                  {...register("createDefaultProject")}
                />
                <div>
                  <div className="font-medium">Create default project</div>
                  <div className="text-sm text-base-content/60">
                    Provision a personal project for this user and set it as their default project.
                  </div>
                </div>
              </div>
            </label>
            <div className="modal-action">
              <button type="button" className="btn" onClick={onClose} disabled={isLoading}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={isLoading}>
                {isLoading ? (
                  <span className="loading loading-spinner loading-sm" />
                ) : (
                  "Create User"
                )}
              </button>
            </div>
          </form>
        )}

        {temporaryPassword && (
          <div className="modal-action">
            <button type="button" className="btn" onClick={onClose} disabled={isLoading}>
              Close
            </button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
