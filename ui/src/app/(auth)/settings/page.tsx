"use client";

import { useEffect, useMemo, useState } from "react";
import { Cpu } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { useTheme } from "@/contexts/ThemeContext";
import { PasswordChangeCard } from "@/components/features/settings/PasswordChangeCard";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { AVAILABLE_THEMES, DEV_THEMES } from "@/constants/themes";
import { useGetCopilotConfig } from "@/client/copilot/copilot";
import {
  getListProjectMembersQueryKey,
  useInviteProjectMember,
  useListProjectMembers,
  useRemoveProjectMember,
  useUpdateProjectMember,
} from "@/client/projects/projects";
import {
  buildAnalysisModelOptions,
  getStoredAnalysisModelKey,
  resolveAnalysisModelOption,
  setStoredAnalysisModelKey,
} from "@/lib/copilotModels";
import type { MemberResponse, ProjectRole } from "@/schemas";
import { getGetCurrentUserQueryKey, useUpdateCurrentUserProfile } from "@/client/auth/auth";
import { AVATAR_PRESETS, UserAvatar } from "@/components/ui/UserAvatar";

type Tab = "appearance" | "project" | "copilot" | "account" | "api";

const editableProjectRoles: ProjectRole[] = ["viewer", "editor"];

function roleBadgeClass(role: ProjectRole) {
  if (role === "owner") return "badge-secondary";
  if (role === "editor") return "badge-primary";
  return "badge-ghost";
}

function mutationErrorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return "Failed to update project members";
}

function CopilotSettingsPanel() {
  const [selectedModelKey, setSelectedModelKey] = useState(getStoredAnalysisModelKey);
  const { data: copilotConfigResponse, isLoading } = useGetCopilotConfig();
  const modelOptions = useMemo(
    () => buildAnalysisModelOptions(copilotConfigResponse?.data ?? null),
    [copilotConfigResponse?.data],
  );
  const selectedModel = resolveAnalysisModelOption(modelOptions, selectedModelKey);

  const handleModelChange = (key: string) => {
    setSelectedModelKey(key);
    setStoredAnalysisModelKey(key);
  };

  return (
    <div className="card bg-base-200 shadow-lg" key="copilot">
      <div className="card-body">
        <h2 className="card-title text-xl mb-4">Copilot Settings</h2>
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <label className="text-sm font-medium">Default analysis model</label>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <select
                className="select select-bordered w-full sm:max-w-md"
                value={selectedModel.key}
                onChange={(event) => handleModelChange(event.target.value)}
                disabled={isLoading}
              >
                {modelOptions.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </select>
              <div className="badge badge-neutral gap-1 w-fit">
                <Cpu className="h-3 w-3" />
                {selectedModel.model?.provider ?? "configured"}
              </div>
            </div>
            <p className="text-sm text-base-content/60">
              This controls the default model used when asking about calibration task results in Ask
              AI. The available choices come from copilot.yaml.
            </p>
          </div>

          <div className="bg-base-100 rounded-lg p-4">
            <div className="text-xs font-semibold text-base-content/50 mb-2">
              Current effective model
            </div>
            <div className="font-mono text-sm break-all">
              {selectedModel.model
                ? `${selectedModel.model.provider}:${selectedModel.model.name}`
                : selectedModel.label}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProfileSettingsPanel() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [avatarKey, setAvatarKey] = useState(user?.avatar_key ?? "");
  const [saved, setSaved] = useState(false);
  const updateProfileMutation = useUpdateCurrentUserProfile({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getGetCurrentUserQueryKey(),
        });
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      },
    },
  });

  useEffect(() => {
    setDisplayName(user?.display_name ?? "");
    setAvatarKey(user?.avatar_key ?? "");
  }, [user?.display_name, user?.avatar_key]);

  const handleSave = () => {
    updateProfileMutation.mutate({
      data: {
        display_name: displayName.trim() || null,
        avatar_key: avatarKey || null,
      },
    });
  };

  const isDirty =
    displayName.trim() !== (user?.display_name ?? "") || avatarKey !== (user?.avatar_key ?? "");

  return (
    <div className="card bg-base-200 shadow-lg">
      <div className="card-body">
        <h2 className="card-title text-xl mb-4">Profile</h2>
        <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
          <div className="flex flex-col items-center gap-3 rounded-lg bg-base-100 p-4">
            <UserAvatar username={user?.username ?? ""} avatarKey={avatarKey} size={72} />
            <div className="text-center">
              <div className="font-medium">{displayName || user?.username}</div>
              <div className="text-xs text-base-content/50">@{user?.username}</div>
            </div>
          </div>
          <div className="space-y-5">
            <label className="form-control w-full">
              <div className="label">
                <span className="label-text">Display name</span>
              </div>
              <input
                className="input input-bordered w-full"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder={user?.username ?? "Display name"}
                maxLength={100}
              />
            </label>

            <div>
              <div className="mb-2 text-sm font-medium">Avatar</div>
              <div className="grid grid-cols-4 gap-2 sm:grid-cols-7 md:grid-cols-9">
                <button
                  type="button"
                  className={`btn h-12 min-h-0 rounded-lg p-1 ${
                    avatarKey === "" ? "btn-primary" : "btn-ghost bg-base-100"
                  }`}
                  onClick={() => setAvatarKey("")}
                  title="Automatic"
                >
                  <UserAvatar username={user?.username ?? ""} size={28} />
                </button>
                {AVATAR_PRESETS.map((preset) => (
                  <button
                    key={preset.key}
                    type="button"
                    className={`btn h-12 min-h-0 rounded-lg p-1 ${
                      avatarKey === preset.key ? "btn-primary" : "btn-ghost bg-base-100"
                    }`}
                    onClick={() => setAvatarKey(preset.key)}
                    title={preset.label}
                  >
                    <UserAvatar username={user?.username ?? ""} avatarKey={preset.key} size={28} />
                  </button>
                ))}
              </div>
            </div>

            {updateProfileMutation.isError && (
              <div className="alert alert-error">
                <span>Failed to update profile.</span>
              </div>
            )}
            {saved && (
              <div className="alert alert-success">
                <span>Profile updated.</span>
              </div>
            )}
            <button
              className="btn btn-primary"
              onClick={handleSave}
              disabled={!isDirty || updateProfileMutation.isPending}
            >
              {updateProfileMutation.isPending ? (
                <span className="loading loading-spinner loading-xs" />
              ) : (
                "Save Profile"
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProjectMembersPanel() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { currentProject, projectId, isOwner } = useProject();
  const [inviteUsername, setInviteUsername] = useState("");
  const [inviteRole, setInviteRole] = useState<ProjectRole>("viewer");
  const [localError, setLocalError] = useState<string | null>(null);

  const membersQuery = useListProjectMembers(projectId ?? "", {
    query: {
      enabled: !!projectId,
      retry: false,
    },
  });
  const inviteMutation = useInviteProjectMember();
  const updateMutation = useUpdateProjectMember();
  const removeMutation = useRemoveProjectMember();
  const members = membersQuery.data?.data.members ?? [];
  const isMutating =
    inviteMutation.isPending || updateMutation.isPending || removeMutation.isPending;
  const memberError =
    localError ||
    (inviteMutation.error || updateMutation.error || removeMutation.error
      ? mutationErrorMessage(inviteMutation.error || updateMutation.error || removeMutation.error)
      : null);

  const refreshMembers = () => {
    if (!projectId) return;
    queryClient.invalidateQueries({
      queryKey: getListProjectMembersQueryKey(projectId),
    });
  };

  const handleInvite = async () => {
    if (!projectId) return;
    const username = inviteUsername.trim();
    if (!username) {
      setLocalError("Enter a username.");
      return;
    }
    setLocalError(null);
    try {
      await inviteMutation.mutateAsync({
        projectId,
        data: { username, role: inviteRole },
      });
      setInviteUsername("");
      setInviteRole("viewer");
      refreshMembers();
    } catch {
      // The mutation error is rendered from TanStack Query state.
    }
  };

  const handleRoleChange = async (member: MemberResponse, role: ProjectRole) => {
    if (!projectId || member.role === role) return;
    setLocalError(null);
    try {
      await updateMutation.mutateAsync({
        projectId,
        username: member.username,
        data: { role },
      });
      refreshMembers();
    } catch {
      // The mutation error is rendered from TanStack Query state.
    }
  };

  const handleRemove = async (member: MemberResponse) => {
    if (!projectId) return;
    setLocalError(null);
    try {
      await removeMutation.mutateAsync({
        projectId,
        username: member.username,
      });
      refreshMembers();
    } catch {
      // The mutation error is rendered from TanStack Query state.
    }
  };

  return (
    <div className="space-y-4" key="project">
      <div className="card bg-base-200 shadow-lg">
        <div className="card-body">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="card-title text-xl">Project Members</h2>
              <p className="text-sm text-base-content/60">
                {currentProject?.name ?? "Current project"}
              </p>
            </div>
            <div className={`badge ${isOwner ? "badge-secondary" : "badge-ghost"} w-fit`}>
              {isOwner ? "Owner controls" : "Read only"}
            </div>
          </div>

          {!isOwner && (
            <div className="alert alert-info mt-4">
              <span>
                Only the project owner can invite members, remove members, or change Viewer and
                Editor roles.
              </span>
            </div>
          )}

          {isOwner && (
            <div className="mt-4 grid gap-3 rounded-lg bg-base-100 p-4 md:grid-cols-[1fr_160px_auto]">
              <input
                className="input input-bordered w-full"
                value={inviteUsername}
                onChange={(event) => setInviteUsername(event.target.value)}
                placeholder="Username"
              />
              <select
                className="select select-bordered w-full"
                value={inviteRole}
                onChange={(event) => setInviteRole(event.target.value as ProjectRole)}
              >
                <option value="viewer">Viewer</option>
                <option value="editor">Editor</option>
              </select>
              <button
                className="btn btn-primary"
                onClick={handleInvite}
                disabled={isMutating || !inviteUsername.trim()}
              >
                Add Member
              </button>
            </div>
          )}

          {memberError && (
            <div className="alert alert-error mt-4">
              <span>{memberError}</span>
            </div>
          )}

          <div className="mt-4 overflow-x-auto">
            <table className="table table-zebra">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {membersQuery.isLoading ? (
                  <tr>
                    <td colSpan={4} className="py-8 text-center">
                      <span className="loading loading-spinner" />
                    </td>
                  </tr>
                ) : members.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-8 text-center text-base-content/60">
                      No members found
                    </td>
                  </tr>
                ) : (
                  members.map((member) => {
                    const isProjectOwner = member.role === "owner";
                    const isCurrentUser = member.username === user?.username;
                    return (
                      <tr key={member.username}>
                        <td className="font-mono">{member.username}</td>
                        <td>
                          {isOwner && !isProjectOwner ? (
                            <select
                              className="select select-bordered select-sm w-32"
                              value={member.role}
                              disabled={isMutating}
                              onChange={(event) =>
                                handleRoleChange(member, event.target.value as ProjectRole)
                              }
                            >
                              {editableProjectRoles.map((role) => (
                                <option key={role} value={role}>
                                  {role.charAt(0).toUpperCase() + role.slice(1)}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <span className={`badge ${roleBadgeClass(member.role)}`}>
                              {member.role}
                            </span>
                          )}
                        </td>
                        <td>
                          <span className="badge badge-ghost">{member.status}</span>
                        </td>
                        <td className="text-right">
                          {isOwner && !isProjectOwner ? (
                            <button
                              className="btn btn-error btn-ghost btn-sm"
                              disabled={isMutating || isCurrentUser}
                              onClick={() => handleRemove(member)}
                            >
                              Remove
                            </button>
                          ) : (
                            <span className="text-xs text-base-content/50">
                              {isProjectOwner ? "Owner" : "-"}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <div className="mt-3 grid gap-2 text-sm text-base-content/60 md:grid-cols-3">
            <p>
              <span className="font-medium text-base-content">Viewer</span> can read project data.
            </p>
            <p>
              <span className="font-medium text-base-content">Editor</span> can run workflows and
              update operational data.
            </p>
            <p>
              <span className="font-medium text-base-content">Owner</span> manages project settings
              and membership.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const { theme, setTheme, isDevEnv } = useTheme();
  const { accessToken, user } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>("appearance");

  useEffect(() => {
    if (user?.must_change_password) {
      setActiveTab("account");
    }
  }, [user?.must_change_password]);

  // Limit theme options in dev environment
  const themes = isDevEnv ? DEV_THEMES : AVAILABLE_THEMES;
  const [copied, setCopied] = useState(false);
  const [copiedCurl, setCopiedCurl] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5715";

  const handleCopyToken = async () => {
    if (accessToken) {
      await navigator.clipboard.writeText(accessToken);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleCopyCurl = async () => {
    const token = accessToken || "<your-token>";
    const curlCommand = `curl -H "Authorization: Bearer ${token}" ${apiUrl}/auth/me`;
    await navigator.clipboard.writeText(curlCommand);
    setCopiedCurl(true);
    setTimeout(() => setCopiedCurl(false), 2000);
  };

  return (
    <PageContainer>
      <PageHeader title="Settings" description="Customize your experience and manage account" />
      <div className="w-full gap-8">
        <div className="tabs tabs-boxed mb-4 sm:mb-6 w-full sm:w-fit overflow-x-auto flex-nowrap">
          <a
            className={`tab ${activeTab === "appearance" ? "tab-active" : ""}`}
            onClick={() => setActiveTab("appearance")}
          >
            Appearance
          </a>
          <a
            className={`tab ${activeTab === "project" ? "tab-active" : ""}`}
            onClick={() => setActiveTab("project")}
          >
            Project
          </a>
          <a
            className={`tab ${activeTab === "copilot" ? "tab-active" : ""}`}
            onClick={() => setActiveTab("copilot")}
          >
            Copilot
          </a>
          <a
            className={`tab ${activeTab === "account" ? "tab-active" : ""}`}
            onClick={() => setActiveTab("account")}
          >
            Account
          </a>
          <a
            className={`tab ${activeTab === "api" ? "tab-active" : ""}`}
            onClick={() => setActiveTab("api")}
          >
            API Token
          </a>
        </div>
        <div className="w-full h-full space-y-6">
          {activeTab === "appearance" ? (
            <div className="card bg-base-200 shadow-lg" key="appearance">
              <div className="card-body">
                <h2 className="card-title text-xl mb-4">Theme Settings</h2>
                {isDevEnv && (
                  <div className="alert alert-warning mb-4">
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
                        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                      />
                    </svg>
                    <span>Dev environment: Using purple theme for visual distinction</span>
                  </div>
                )}
                <div className="flex flex-col gap-6">
                  <div className="flex flex-col gap-3">
                    <label className="text-sm font-medium">Select Theme</label>
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                      {themes.slice(0, 8).map((t) => (
                        <button
                          key={t}
                          className={`btn btn-sm w-full ${
                            theme === t ? "btn-primary" : "btn-ghost"
                          }`}
                          onClick={() => setTheme(t)}
                        >
                          {t.charAt(0).toUpperCase() + t.slice(1)}
                        </button>
                      ))}
                    </div>
                    {!isDevEnv && themes.length > 8 && (
                      <details className="collapse collapse-arrow bg-base-100">
                        <summary className="collapse-title text-sm font-medium">
                          More themes
                        </summary>
                        <div className="collapse-content">
                          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 pt-2">
                            {themes.slice(8).map((t) => (
                              <button
                                key={t}
                                className={`btn btn-sm w-full ${
                                  theme === t ? "btn-primary" : "btn-ghost"
                                }`}
                                onClick={() => setTheme(t)}
                              >
                                {t.charAt(0).toUpperCase() + t.slice(1)}
                              </button>
                            ))}
                          </div>
                        </div>
                      </details>
                    )}
                  </div>

                  {/* Color palette */}
                  <div className="flex flex-col gap-3">
                    <h3 className="text-sm font-medium">Color Palette</h3>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-primary"></div>
                        <span className="text-sm font-medium">Primary</span>
                      </div>
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-secondary"></div>
                        <span className="text-sm font-medium">Secondary</span>
                      </div>
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-accent"></div>
                        <span className="text-sm font-medium">Accent</span>
                      </div>
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-neutral"></div>
                        <span className="text-sm font-medium">Neutral</span>
                      </div>
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-info"></div>
                        <span className="text-sm font-medium">Info</span>
                      </div>
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-success"></div>
                        <span className="text-sm font-medium">Success</span>
                      </div>
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-warning"></div>
                        <span className="text-sm font-medium">Warning</span>
                      </div>
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-error"></div>
                        <span className="text-sm font-medium">Error</span>
                      </div>
                    </div>

                    {/* Example components */}
                    <div className="flex flex-col gap-3">
                      <h3 className="text-sm font-medium">Preview Components</h3>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <button className="btn btn-primary btn-sm w-full">Primary</button>
                        <button className="btn btn-secondary btn-sm w-full">Secondary</button>
                        <button className="btn btn-accent btn-sm w-full">Accent</button>
                        <button className="btn btn-neutral btn-sm w-full">Neutral</button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : activeTab === "project" ? (
            <ProjectMembersPanel />
          ) : activeTab === "copilot" ? (
            <CopilotSettingsPanel />
          ) : activeTab === "account" ? (
            <div className="space-y-4" key="account">
              {user?.must_change_password && (
                <div className="alert alert-warning">
                  <span>
                    You are using a temporary password. Change it before continuing regular work.
                  </span>
                </div>
              )}
              <ProfileSettingsPanel />
              <PasswordChangeCard />
            </div>
          ) : (
            <div className="card bg-base-200 shadow-lg" key="api">
              <div className="card-body">
                <h2 className="card-title text-xl mb-4">API Access Token</h2>
                <div className="flex flex-col gap-6">
                  <div className="flex flex-col gap-3">
                    <p className="text-sm text-base-content/70">
                      Use this token to authenticate API requests. Include it in the Authorization
                      header:
                    </p>
                    <code className="bg-base-300 p-3 rounded-lg text-sm">
                      Authorization: Bearer {"<your-token>"}
                    </code>
                  </div>

                  <div className="flex flex-col gap-3">
                    <label className="text-sm font-medium">Your Access Token</label>
                    <div className="flex flex-col gap-2">
                      <input
                        type={showToken ? "text" : "password"}
                        value={accessToken || ""}
                        readOnly
                        className="input input-bordered w-full font-mono text-sm"
                      />
                      <div className="flex gap-2">
                        <button
                          className="btn btn-sm flex-1"
                          onClick={() => setShowToken(!showToken)}
                        >
                          {showToken ? (
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
                                d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88"
                              />
                            </svg>
                          ) : (
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
                                d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z"
                              />
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                              />
                            </svg>
                          )}
                          <span className="hidden sm:inline">{showToken ? "Hide" : "Show"}</span>
                        </button>
                        <button
                          className={`btn btn-sm flex-1 ${copied ? "btn-success" : "btn-primary"}`}
                          onClick={handleCopyToken}
                        >
                          {copied ? (
                            <>
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
                                  d="M4.5 12.75l6 6 9-13.5"
                                />
                              </svg>
                              <span className="hidden sm:inline">Copied!</span>
                            </>
                          ) : (
                            <>
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
                                  d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9.75a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184"
                                />
                              </svg>
                              <span className="hidden sm:inline">Copy</span>
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-col gap-3">
                    <label className="text-sm font-medium">Example Usage (curl)</label>
                    <div className="relative">
                      <div className="mockup-code text-xs sm:text-sm overflow-x-auto">
                        <pre className="whitespace-pre-wrap break-all sm:whitespace-pre sm:break-normal">
                          <code>
                            curl -H "Authorization: Bearer{" "}
                            {showToken && accessToken ? accessToken : "<your-token>"}" \
                          </code>
                        </pre>
                        <pre>
                          <code> {apiUrl}/auth/me</code>
                        </pre>
                      </div>
                      <button
                        className={`btn btn-xs sm:btn-sm absolute top-2 right-2 ${copiedCurl ? "btn-success" : "btn-ghost"}`}
                        onClick={handleCopyCurl}
                      >
                        {copiedCurl ? (
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
                              d="M4.5 12.75l6 6 9-13.5"
                            />
                          </svg>
                        ) : (
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
                              d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9.75a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184"
                            />
                          </svg>
                        )}
                        <span className="hidden sm:inline">{copiedCurl ? "Copied!" : "Copy"}</span>
                      </button>
                    </div>
                  </div>

                  <div className="alert alert-info">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      className="stroke-current shrink-0 w-6 h-6"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                      ></path>
                    </svg>
                    <div>
                      <p className="font-medium">Keep your token secure</p>
                      <p className="text-sm">
                        This token provides full access to your account. Do not share it publicly.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </PageContainer>
  );
}
