"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Copy, Cpu } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiAccessTokenPanel } from "@/components/features/settings/ApiAccessTokenPanel";
import { AppearanceSettingsPanel } from "@/components/features/settings/AppearanceSettingsPanel";
import { PasswordChangeCard } from "@/components/features/settings/PasswordChangeCard";
import { ProfileSettingsPanel } from "@/components/features/settings/ProfileSettingsPanel";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { SelectedLabel } from "@/components/ui/SelectedLabel";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { useGetCopilotConfig } from "@/client/copilot/copilot";
import {
  getListProjectMembersQueryKey,
  useInviteProjectMember,
  useListProjectMembers,
  useRemoveProjectMember,
  useUpdateProjectMember,
} from "@/client/projects/projects";
import {
  buildChatModelOptions,
  getStoredChatModelKey,
  resolveChatModelOption,
  setStoredChatModelKey,
} from "@/lib/copilotModels";
import type { MemberResponse, ProjectRole } from "@/schemas";
import { getApiErrorMessage } from "@/lib/utils/apiError";

import { CopilotInstructionsSettings } from "./CopilotInstructionsSettings";
import { CopilotSystemPromptView } from "./CopilotSystemPromptView";

const TABS = ["appearance", "project", "copilot", "account", "api"] as const;
type Tab = (typeof TABS)[number];

const editableProjectRoles: ProjectRole[] = ["viewer", "editor"];

/** Returns the DaisyUI badge class for a project role. */
function roleBadgeClass(role: ProjectRole) {
  if (role === "owner") return "badge-secondary";
  if (role === "editor") return "badge-primary";
  return "badge-ghost";
}

/** Copilot settings for the chat model, custom instructions and system prompt. */
function CopilotSettingsPanel() {
  const [selectedModelKey, setSelectedModelKey] = useState(getStoredChatModelKey);
  const { data: copilotConfigResponse, isLoading } = useGetCopilotConfig();
  const modelOptions = useMemo(
    () => buildChatModelOptions(copilotConfigResponse?.data ?? null),
    [copilotConfigResponse?.data],
  );
  const selectedModel = resolveChatModelOption(modelOptions, selectedModelKey);

  const handleModelChange = (key: string) => {
    setSelectedModelKey(key);
    setStoredChatModelKey(key);
  };

  return (
    <div className="card bg-base-200 shadow-sm" key="copilot">
      <div className="card-body">
        <h2 className="card-title mb-4">Copilot Settings</h2>
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <label className="text-sm font-medium">Default chat model</label>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <select
                className="select select-bordered w-full sm:max-w-md"
                value={selectedModel.key}
                onChange={(event) => handleModelChange(event.target.value)}
                disabled={isLoading}
              >
                <SelectedLabel />
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
            <div className="text-xs font-medium text-base-content/50 mb-2">
              Current effective model
            </div>
            <div className="font-mono text-sm break-all">
              {selectedModel.model
                ? `${selectedModel.model.provider}:${selectedModel.model.name}`
                : selectedModel.label}
            </div>
          </div>

          <div className="divider my-0" />

          <CopilotInstructionsSettings />

          <CopilotSystemPromptView />
        </div>
      </div>
    </div>
  );
}

/** Project member list with owner controls to invite, change roles and remove members. */
function ProjectMembersPanel() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { currentProject, projects, projectId, isOwner, switchProject } = useProject();
  const [inviteUsername, setInviteUsername] = useState("");
  const [copiedProjectId, setCopiedProjectId] = useState<string | null>(null);
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
      ? getApiErrorMessage(
          inviteMutation.error || updateMutation.error || removeMutation.error,
          "Failed to update project members",
        )
      : null);

  const refreshMembers = () => {
    if (!projectId) return;
    queryClient.invalidateQueries({
      queryKey: getListProjectMembersQueryKey(projectId),
    });
  };

  const handleCopyProjectId = async (id: string) => {
    await navigator.clipboard.writeText(id);
    setCopiedProjectId(id);
    setTimeout(() => setCopiedProjectId(null), 2000);
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
      <div className="card bg-base-200 shadow-sm">
        <div className="card-body">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="card-title">Project Members</h2>
              <p className="text-sm text-base-content/60">
                {currentProject?.name ?? "Current project"}
              </p>
            </div>
            <div className={`badge ${isOwner ? "badge-secondary" : "badge-ghost"} w-fit`}>
              {isOwner ? "Owner controls" : "Read only"}
            </div>
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(260px,360px)]">
            <div className="rounded-lg bg-base-100 p-4">
              <div className="text-xs font-medium text-base-content/50">Current project ID</div>
              <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
                <code className="min-w-0 flex-1 rounded bg-base-300 px-3 py-2 text-sm break-all">
                  {projectId ?? "No project selected"}
                </code>
                <button
                  className={`btn btn-sm ${copiedProjectId === projectId ? "btn-success" : "btn-ghost"}`}
                  disabled={!projectId}
                  onClick={() => projectId && handleCopyProjectId(projectId)}
                  type="button"
                >
                  {copiedProjectId === projectId ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                  {copiedProjectId === projectId ? "Copied" : "Copy"}
                </button>
              </div>
            </div>

            <div className="rounded-lg bg-base-100 p-4">
              <div className="text-xs font-medium text-base-content/50">Your projects</div>
              <div className="mt-2 flex max-h-48 flex-col gap-2 overflow-y-auto">
                {projects.length === 0 ? (
                  <span className="text-sm text-base-content/60">No projects available</span>
                ) : (
                  projects.map((project) => (
                    <div
                      className={`rounded border p-2 ${
                        project.project_id === projectId
                          ? "border-primary bg-primary/10"
                          : "border-base-300"
                      }`}
                      key={project.project_id}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <button
                          className="min-w-0 text-left"
                          onClick={() => switchProject(project.project_id)}
                          type="button"
                        >
                          <div className="truncate text-sm font-medium">{project.name}</div>
                          <div className="font-mono text-xs text-base-content/60 break-all">
                            {project.project_id}
                          </div>
                        </button>
                        <button
                          className={`btn btn-square btn-ghost btn-xs ${
                            copiedProjectId === project.project_id ? "btn-success" : ""
                          }`}
                          onClick={() => handleCopyProjectId(project.project_id)}
                          title="Copy project ID"
                          type="button"
                        >
                          {copiedProjectId === project.project_id ? (
                            <Check className="h-3 w-3" />
                          ) : (
                            <Copy className="h-3 w-3" />
                          )}
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
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

export function SettingsPageContent() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>("appearance");

  // `?tab=copilot` opens a tab directly (the chat links to its instructions).
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("tab");
    if (requested && (TABS as readonly string[]).includes(requested)) {
      setActiveTab(requested as Tab);
    }
  }, []);

  useEffect(() => {
    if (user?.must_change_password) {
      setActiveTab("account");
    }
  }, [user?.must_change_password]);

  return (
    <PageContainer>
      <PageHeader
        title="Settings"
        description="Appearance, project, Copilot, account and API tokens"
      />
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
            <AppearanceSettingsPanel />
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
            <ApiAccessTokenPanel />
          )}
        </div>
      </div>
    </PageContainer>
  );
}
