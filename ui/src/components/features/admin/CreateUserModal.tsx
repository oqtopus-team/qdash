"use client";

import { useState } from "react";

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

export function CreateUserModal({ onClose, onSave, isLoading, error }: CreateUserModalProps) {
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
      // Error is handled by the mutation.
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
                onChange={(event) => setUsername(event.target.value)}
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
                onChange={(event) => setDisplayName(event.target.value)}
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
                onChange={(event) => setOrganization(event.target.value)}
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
              {isLoading ? <span className="loading loading-spinner loading-sm" /> : "Create User"}
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
