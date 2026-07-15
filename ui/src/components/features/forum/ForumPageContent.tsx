"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  CalendarDays,
  Crosshair,
  ExternalLink,
  MessageSquare,
  Pencil,
  Plus,
  Settings,
  Tag,
  Trash2,
  UserRound,
  X,
  XCircle,
} from "lucide-react";

import { useListChips } from "@/client/chip/chip";
import { useListCooldowns } from "@/client/cooldown/cooldown";
import { useListProjectMembers } from "@/client/projects/projects";
import {
  getGetForumPostQueryKey,
  getListForumCategoriesQueryKey,
  getListForumPostsQueryKey,
  useCreateForumCategory,
  useDeleteForumCategory,
  useGetForumPost,
  useGetForumPostReplies,
  useListForumCategories,
  useListForumPosts,
  useUpdateForumPost,
} from "@/client/forum/forum";
import { EmptyState } from "@/components/ui/EmptyState";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";
import { PageHeader } from "@/components/ui/PageHeader";
import { SearchInput } from "@/components/ui/SearchInput";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { formatDateTimeCompact, formatRelativeTime } from "@/lib/utils/datetime";
import type { ForumPostResponse, ListForumPostsParams } from "@/schemas";

import {
  DEFAULT_FORUM_CATEGORIES,
  FORUM_LABELS,
  FORUM_STATUSES,
  getForumCategory,
  formatForumPostNumber,
  getForumLabel,
  getForumStatus,
  isForumTerminalStatus,
  toForumCategoryDefinition,
  type ForumCategoryDefinition,
} from "./categories";
import { ForumLabelPicker } from "./ForumLabelSelector";
import { ForumBlockViewer } from "./ForumBlockEditor";

const PAGE_SIZE = 30;

type CategoryFilter = "all" | NonNullable<ListForumPostsParams["category"]>;
type StatusFilter = "open" | "investigating" | "identified" | "resolved" | "all";

function parseForumPage(value: string | null): number {
  const page = Number.parseInt(value ?? "1", 10);
  return Number.isFinite(page) && page > 0 ? page : 1;
}

function parseForumStatus(value: string | null): StatusFilter {
  if (
    value === "open" ||
    value === "investigating" ||
    value === "identified" ||
    value === "resolved" ||
    value === "all"
  ) {
    return value;
  }
  return "open";
}

type ForumTargetContext = {
  chipId: string;
  targetType: "qubit" | "coupling";
  targetId: string;
};

function normalizeTargetType(value: string | null | undefined): "qubit" | "coupling" | null {
  return value === "qubit" || value === "coupling" ? value : null;
}

function formatTargetLabel(targetType: "qubit" | "coupling", targetId: string): string {
  if (targetType === "coupling") {
    const [a, b] = targetId.split("-");
    return b ? `Q${a} -> Q${b}` : targetId;
  }
  return `Q${targetId}`;
}

function formatCooldownPeriod(
  cooldown: { started_at?: string | null; ended_at?: string | null } | undefined,
): string {
  if (!cooldown?.started_at) return "";
  const start = formatDateTimeCompact(cooldown.started_at);
  const end = cooldown.ended_at ? formatDateTimeCompact(cooldown.ended_at) : "ongoing";
  return `${start} - ${end}`;
}

function parseTargetId(
  targetLabel: string,
): { targetType: "qubit" | "coupling"; targetId: string } | null {
  const qids = Array.from(targetLabel.matchAll(/Q(\d+)/g)).map((match) => match[1]);
  if (qids.length >= 2) return { targetType: "coupling", targetId: `${qids[0]}-${qids[1]}` };
  if (qids.length === 1) return { targetType: "qubit", targetId: qids[0] };
  return null;
}

function postTargetContext(post: ForumPostResponse): ForumTargetContext | null {
  const targetType = normalizeTargetType(post.target_type);
  if (post.chip_id && targetType && post.target_id) {
    return {
      chipId: post.chip_id,
      targetType,
      targetId: post.target_id,
    };
  }
  const chip = post.content.match(/^Chip:\s*(.+)$/m)?.[1]?.trim();
  const target = post.content.match(/^Target:\s*(.+)$/m)?.[1]?.trim();
  const parsed = target ? parseTargetId(target) : null;
  if (!chip || !target || !parsed) return null;
  return {
    chipId: chip,
    targetType: parsed.targetType,
    targetId: parsed.targetId,
  };
}

function ForumThreadCard({
  post,
  categories,
  isSelected,
  onSelect,
}: {
  post: ForumPostResponse;
  categories: ForumCategoryDefinition[];
  isSelected: boolean;
  onSelect: () => void;
}) {
  const category = getForumCategory(post.category, categories);
  const targetContext = postTargetContext(post);
  const Icon = category.icon;
  const displayNumber = formatForumPostNumber(post.number);
  const primaryLabel = (post.labels ?? [])[0];
  const labelDef = primaryLabel ? getForumLabel(primaryLabel) : null;
  const statusDef = getForumStatus(post.status);
  const StatusIcon = statusDef.icon;
  const isTerminal = isForumTerminalStatus(post.status);

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      className={`cursor-pointer rounded-lg border bg-base-100 transition-colors hover:border-primary/40 ${
        isSelected ? "border-primary/60 ring-1 ring-primary/20" : "border-base-300"
      } ${isTerminal ? "opacity-70" : ""}`}
    >
      <div className="flex gap-3 p-3 sm:p-4">
        <div className="hidden pt-0.5 sm:block">
          <UserAvatar username={post.username} avatarKey={post.avatar_key} size={30} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0 flex-1">
              <h2 className="line-clamp-2 text-sm font-semibold leading-6 text-base-content sm:text-base">
                {displayNumber && (
                  <span className="mr-2 font-mono text-xs font-medium text-base-content/50">
                    {displayNumber}
                  </span>
                )}
                {post.title || "Untitled topic"}
              </h2>
            </div>

            <div className="flex shrink-0 flex-wrap items-center gap-1.5">
              <span
                className={`badge badge-sm gap-1 ${category.badgeClass}`}
                title={category.label}
              >
                <Icon className="h-3 w-3" />
                {category.shortLabel}
              </span>
              {labelDef && (
                <span className={`badge badge-sm ${labelDef.badgeClass}`}>{labelDef.label}</span>
              )}
              <span className={`badge badge-sm gap-1 ${statusDef.badgeClass}`}>
                <StatusIcon className="h-3 w-3" />
                {statusDef.label}
              </span>
            </div>
          </div>

          <div className="mt-1 line-clamp-1 text-sm leading-6 text-base-content/60">
            <MarkdownContent content={post.content} preview />
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-base-content/50">
            <span>{post.username}</span>
            <span>{formatRelativeTime(post.created_at)}</span>
            {post.assignee_username && (
              <span className="inline-flex items-center gap-1">
                <UserRound className="h-3.5 w-3.5" />
                {post.assignee_username}
              </span>
            )}
            <span className="inline-flex items-center gap-1">
              <MessageSquare className="h-3.5 w-3.5" />
              {post.reply_count ?? 0}
            </span>
            {targetContext && (
              <span className="inline-flex min-w-0 items-center gap-1">
                <Crosshair className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">
                  {formatTargetLabel(targetContext.targetType, targetContext.targetId)} ·{" "}
                  {targetContext.chipId}
                </span>
              </span>
            )}
            {post.cooldown_id && (
              <span className="inline-flex items-center gap-1">
                <CalendarDays className="h-3.5 w-3.5" />
                {post.cooldown_id}
              </span>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

function ForumThreadPreviewSidebar({
  postId,
  categories,
  currentUsername,
  isOwner,
  projectId,
  returnQuery,
  onClose,
}: {
  postId: string | null;
  categories: ForumCategoryDefinition[];
  currentUsername?: string;
  isOwner: boolean;
  projectId?: string | null;
  returnQuery: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [editingMetadata, setEditingMetadata] = useState(false);
  const [targetDraftChipId, setTargetDraftChipId] = useState("");
  const [targetDraftType, setTargetDraftType] = useState<"qubit" | "coupling">("qubit");
  const [targetDraftId, setTargetDraftId] = useState("");
  const [cooldownDraftId, setCooldownDraftId] = useState("");

  const {
    data: postResponse,
    isLoading,
    isError,
  } = useGetForumPost(postId ?? "", {
    query: { enabled: !!postId, staleTime: 30_000 },
  });
  const { data: repliesResponse, isLoading: repliesLoading } = useGetForumPostReplies(
    postId ?? "",
    { skip: 0, limit: 5 },
    { query: { enabled: !!postId, staleTime: 30_000 } },
  );
  const { data: membersResponse } = useListProjectMembers(projectId ?? "", {
    query: { enabled: !!projectId && editingMetadata, staleTime: 60_000 },
  });
  const { data: chipsResponse } = useListChips({
    query: { enabled: editingMetadata, staleTime: 60_000 },
  });

  const post = postResponse?.data;
  const replies = repliesResponse?.data ?? [];
  const isOpen = !!postId;
  const category = post ? getForumCategory(post.category, categories) : null;
  const CategoryIcon = category?.icon;
  const label = post?.labels?.[0] ? getForumLabel(post.labels[0]) : null;
  const statusDef = getForumStatus(post?.status);
  const StatusIcon = statusDef.icon;
  const targetContext = post ? postTargetContext(post) : null;
  const canManage = !!post && (isOwner || currentUsername === post.username);
  const updateMutation = useUpdateForumPost();
  const members = useMemo(
    () => (membersResponse?.data.members ?? []).filter((member) => member.status === "active"),
    [membersResponse?.data.members],
  );
  const chips = useMemo(
    () =>
      [...(chipsResponse?.data.chips ?? [])].sort((a, b) => {
        const aTime = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const bTime = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return bTime - aTime || b.chip_id.localeCompare(a.chip_id);
      }),
    [chipsResponse?.data.chips],
  );
  const { data: cooldownsResponse } = useListCooldowns(
    { chip_id: targetDraftChipId || undefined },
    {
      query: {
        enabled: editingMetadata && (!!targetDraftChipId || !!post?.cooldown_id),
        staleTime: 60_000,
      },
    },
  );
  const cooldowns = useMemo(
    () =>
      [...(cooldownsResponse?.data.cooldowns ?? [])].sort((a, b) => {
        const aTime = a.started_at ? new Date(a.started_at).getTime() : 0;
        const bTime = b.started_at ? new Date(b.started_at).getTime() : 0;
        return bTime - aTime || b.cooldown_id.localeCompare(a.cooldown_id);
      }),
    [cooldownsResponse?.data.cooldowns],
  );
  const selectedCooldown = cooldowns.find((cooldown) => cooldown.cooldown_id === cooldownDraftId);

  useEffect(() => {
    setEditingMetadata(false);
  }, [postId]);

  useEffect(() => {
    if (!post || editingMetadata) return;
    const context = postTargetContext(post);
    setTargetDraftChipId(context?.chipId ?? "");
    setTargetDraftType(context?.targetType ?? "qubit");
    setTargetDraftId(context?.targetId ?? "");
    setCooldownDraftId(post.cooldown_id ?? "");
  }, [editingMetadata, post]);

  const syncPostCache = (nextPost: ForumPostResponse) => {
    queryClient.setQueryData(getGetForumPostQueryKey(nextPost.id), (current: unknown) =>
      current && typeof current === "object" ? { ...current, data: nextPost } : current,
    );
    queryClient.invalidateQueries({ queryKey: getListForumPostsQueryKey() });
  };

  const updateMetadata = async ({
    category: nextCategory,
    labels: nextLabels,
    chipId: nextChipId,
    targetType: nextTargetType,
    targetId: nextTargetId,
    cooldownId: nextCooldownId,
    assigneeUsername: nextAssigneeUsername,
  }: {
    category?: string;
    labels?: string[];
    chipId?: string | null;
    targetType?: "qubit" | "coupling" | null;
    targetId?: string | null;
    cooldownId?: string | null;
    assigneeUsername?: string | null;
  }) => {
    if (!post || !canManage) return;
    const response = await updateMutation.mutateAsync({
      postId: post.id,
      data: {
        category: nextCategory ?? post.category,
        title: post.title ?? null,
        content: post.content,
        content_blocks: (post.content_blocks ?? []) as Record<string, unknown>[],
        labels: nextLabels ?? post.labels ?? [],
        ...(nextCooldownId !== undefined ? { cooldown_id: nextCooldownId } : {}),
        ...(nextAssigneeUsername !== undefined ? { assignee_username: nextAssigneeUsername } : {}),
        ...(nextChipId !== undefined || nextTargetType !== undefined || nextTargetId !== undefined
          ? {
              chip_id: nextChipId,
              target_type: nextTargetType,
              target_id: nextTargetId,
            }
          : {}),
      },
    });
    syncPostCache(response.data);
  };

  const togglePostLabel = (labelId: string) => {
    if (!post) return;
    const currentLabels = post.labels ?? [];
    const nextLabels = currentLabels.includes(labelId) ? [] : [labelId];
    updateMetadata({ labels: nextLabels });
  };

  const saveTargetMetadata = (
    nextChipId = targetDraftChipId,
    nextTargetType = targetDraftType,
    nextTargetId = targetDraftId,
  ) => {
    const chipId = nextChipId.trim();
    const targetId = nextTargetId.trim();
    if (!chipId || !targetId) return;
    updateMetadata({ chipId, targetType: nextTargetType, targetId });
  };

  const clearTargetMetadata = () => {
    setTargetDraftChipId("");
    setTargetDraftType("qubit");
    setTargetDraftId("");
    setCooldownDraftId("");
    updateMetadata({ chipId: "", targetType: null, targetId: "", cooldownId: "" });
  };

  const saveCooldownMetadata = (nextCooldownId: string) => {
    setCooldownDraftId(nextCooldownId);
    updateMetadata({ cooldownId: nextCooldownId });
  };

  const saveAssigneeMetadata = (nextAssigneeUsername: string) => {
    updateMetadata({ assigneeUsername: nextAssigneeUsername || null });
  };

  return (
    <div
      className={`fixed right-0 top-0 z-50 h-full w-full overflow-y-auto border-l border-base-300 bg-base-100 p-4 shadow-xl transition-transform duration-200 sm:w-3/4 sm:p-6 lg:w-2/5 ${
        isOpen ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <button
        type="button"
        onClick={onClose}
        className="btn btn-ghost btn-sm btn-circle absolute right-3 top-3 sm:right-4 sm:top-4"
        aria-label="Close forum thread preview"
      >
        <X className="h-4 w-4" />
      </button>

      {postId && (
        <div className="pr-8">
          {isLoading ? (
            <div className="flex justify-center py-12">
              <span className="loading loading-spinner loading-lg" />
            </div>
          ) : isError || !post ? (
            <div className="alert alert-error">
              <span>Failed to load forum thread.</span>
            </div>
          ) : (
            <div className="space-y-5">
              <header>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  {category && (
                    <span className={`badge badge-sm ${category.badgeClass}`}>
                      {category.shortLabel}
                    </span>
                  )}
                  {label && (
                    <span className={`badge badge-sm ${label.badgeClass}`}>{label.label}</span>
                  )}
                  <span className={`badge badge-sm gap-1 ${statusDef.badgeClass}`}>
                    <StatusIcon className="h-3 w-3" />
                    {statusDef.label}
                  </span>
                </div>
                <h2 className="text-xl font-bold leading-tight">
                  {formatForumPostNumber(post.number) && (
                    <span className="mr-2 font-mono text-sm text-base-content/50">
                      {formatForumPostNumber(post.number)}
                    </span>
                  )}
                  {post.title || "Untitled topic"}
                </h2>
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-base-content/50">
                  <span>Opened by {post.username}</span>
                  <span>{formatRelativeTime(post.created_at)}</span>
                  <span className="inline-flex items-center gap-1">
                    <MessageSquare className="h-3.5 w-3.5" />
                    {post.reply_count ?? 0} replies
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Link
                    href={
                      returnQuery
                        ? `/forum/${post.id}?from=${encodeURIComponent(returnQuery)}`
                        : `/forum/${post.id}`
                    }
                    className="btn btn-primary btn-sm gap-1"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Open full page
                  </Link>
                  {canManage && (
                    <button
                      type="button"
                      className={`btn btn-sm gap-1 ${editingMetadata ? "btn-neutral" : "btn-outline"}`}
                      onClick={() => setEditingMetadata((open) => !open)}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      Edit metadata
                    </button>
                  )}
                </div>
              </header>

              {(targetContext || post.cooldown_id || post.assignee_username) && (
                <div className="rounded-lg bg-base-200/60 p-3 text-xs">
                  <div className="grid gap-2 sm:grid-cols-2">
                    {targetContext && (
                      <div>
                        <div className="text-base-content/45">Target</div>
                        <div className="mt-1 font-medium">
                          {formatTargetLabel(targetContext.targetType, targetContext.targetId)} -{" "}
                          {targetContext.chipId}
                        </div>
                      </div>
                    )}
                    {post.cooldown_id && (
                      <div>
                        <div className="text-base-content/45">Cooldown</div>
                        <div className="mt-1 font-medium">{post.cooldown_id}</div>
                      </div>
                    )}
                    {post.assignee_username && (
                      <div>
                        <div className="text-base-content/45">Assignee</div>
                        <div className="mt-1 font-medium">{post.assignee_username}</div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {editingMetadata && canManage && (
                <section className="rounded-lg border border-base-300 bg-base-200/40 p-3">
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold">Metadata</h3>
                    {updateMutation.isPending && (
                      <span className="loading loading-spinner loading-xs" />
                    )}
                  </div>
                  <div className="space-y-4">
                    <label className="block space-y-1">
                      <span className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
                        {CategoryIcon && <CategoryIcon className="h-3.5 w-3.5" />}
                        Category
                      </span>
                      <select
                        className="select select-bordered select-sm w-full"
                        value={post.category}
                        disabled={updateMutation.isPending}
                        onChange={(event) => updateMetadata({ category: event.target.value })}
                      >
                        {categories.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
                        <Crosshair className="h-3.5 w-3.5" />
                        Target
                      </div>
                      <select
                        className="select select-bordered select-xs w-full"
                        value={targetDraftChipId}
                        disabled={updateMutation.isPending}
                        onChange={(event) => {
                          const nextChipId = event.target.value;
                          setTargetDraftChipId(nextChipId);
                          setCooldownDraftId("");
                          saveTargetMetadata(nextChipId, targetDraftType, targetDraftId);
                        }}
                      >
                        <option value="">Select chip</option>
                        {chips.map((chip) => (
                          <option key={chip.chip_id} value={chip.chip_id}>
                            {chip.chip_id}
                          </option>
                        ))}
                      </select>
                      <div className="grid grid-cols-[96px_1fr] gap-2">
                        <select
                          className="select select-bordered select-xs w-full"
                          value={targetDraftType}
                          disabled={updateMutation.isPending}
                          onChange={(event) => {
                            const nextType =
                              event.target.value === "coupling" ? "coupling" : "qubit";
                            setTargetDraftType(nextType);
                            saveTargetMetadata(targetDraftChipId, nextType, targetDraftId);
                          }}
                        >
                          <option value="qubit">Qubit</option>
                          <option value="coupling">Coupling</option>
                        </select>
                        <input
                          className="input input-bordered input-xs w-full"
                          value={targetDraftId}
                          disabled={updateMutation.isPending}
                          onChange={(event) => setTargetDraftId(event.target.value)}
                          onBlur={() => saveTargetMetadata()}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              event.currentTarget.blur();
                            }
                          }}
                          placeholder={targetDraftType === "coupling" ? "0-1" : "0"}
                        />
                      </div>
                      <div className="flex justify-end">
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs"
                          onClick={clearTargetMetadata}
                          disabled={updateMutation.isPending || !targetContext}
                        >
                          Clear
                        </button>
                      </div>
                    </div>

                    <label className="block space-y-1">
                      <span className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
                        <CalendarDays className="h-3.5 w-3.5" />
                        Cooldown
                      </span>
                      <select
                        className="select select-bordered select-xs w-full"
                        value={cooldownDraftId}
                        onChange={(event) => saveCooldownMetadata(event.target.value)}
                        disabled={!targetDraftChipId || updateMutation.isPending}
                      >
                        <option value="">No cooldown</option>
                        {cooldowns.map((cooldown) => (
                          <option key={cooldown.cooldown_id} value={cooldown.cooldown_id}>
                            {cooldown.cooldown_id}
                            {formatCooldownPeriod(cooldown)
                              ? ` - ${formatCooldownPeriod(cooldown)}`
                              : ""}
                          </option>
                        ))}
                      </select>
                      {selectedCooldown && (
                        <span className="block text-xs text-base-content/55">
                          {formatCooldownPeriod(selectedCooldown)}
                        </span>
                      )}
                    </label>

                    <label className="block space-y-1">
                      <span className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
                        <UserRound className="h-3.5 w-3.5" />
                        Assignee
                      </span>
                      <select
                        className="select select-bordered select-xs w-full"
                        value={post.assignee_username ?? ""}
                        onChange={(event) => saveAssigneeMetadata(event.target.value)}
                        disabled={updateMutation.isPending}
                      >
                        <option value="">Unassigned</option>
                        {members.map((member) => (
                          <option key={member.username} value={member.username}>
                            {member.display_name
                              ? `${member.display_name} (@${member.username})`
                              : member.username}
                          </option>
                        ))}
                      </select>
                    </label>

                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
                        <Tag className="h-3.5 w-3.5" />
                        Labels
                      </div>
                      <ForumLabelPicker
                        selectedLabels={post.labels ?? []}
                        onToggle={togglePostLabel}
                        disabled={updateMutation.isPending}
                      />
                    </div>
                  </div>
                </section>
              )}

              <section>
                <h3 className="mb-2 text-sm font-semibold">Root thread</h3>
                <div className="rounded-lg border border-base-300 bg-base-100 p-4">
                  {(post.content_blocks ?? []).length > 0 ? (
                    <ForumBlockViewer
                      blocks={(post.content_blocks ?? []) as Record<string, unknown>[]}
                    />
                  ) : (
                    <MarkdownContent
                      content={post.content}
                      className="text-sm text-base-content/80"
                    />
                  )}
                </div>
              </section>

              <section>
                <h3 className="mb-2 text-sm font-semibold">Recent replies</h3>
                {repliesLoading ? (
                  <div className="flex justify-center py-4">
                    <span className="loading loading-spinner loading-sm" />
                  </div>
                ) : replies.length > 0 ? (
                  <div className="space-y-2">
                    {replies.map((reply) => (
                      <div key={reply.id} className="rounded-lg border border-base-300 p-3">
                        <div className="mb-2 flex items-center gap-2 text-xs text-base-content/50">
                          <UserAvatar
                            username={reply.username}
                            avatarKey={reply.avatar_key}
                            size={20}
                          />
                          <span>{reply.username}</span>
                          <span>{formatRelativeTime(reply.created_at)}</span>
                        </div>
                        {(reply.content_blocks ?? []).length > 0 ? (
                          <ForumBlockViewer
                            blocks={(reply.content_blocks ?? []) as Record<string, unknown>[]}
                          />
                        ) : (
                          <MarkdownContent
                            content={reply.content}
                            preview
                            className="line-clamp-3 text-sm text-base-content/70"
                          />
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-lg border border-base-300 bg-base-200/40 p-3 text-sm text-base-content/55">
                    No replies yet
                  </div>
                )}
              </section>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ForumPageContent() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const { isOwner, projectId } = useProject();
  const [category, setCategory] = useState<CategoryFilter>(
    () => (searchParams.get("forum_category") as CategoryFilter | null) ?? "all",
  );
  const [labelFilter, setLabelFilter] = useState<string>(
    () => searchParams.get("forum_label") ?? "all",
  );
  const [cooldownFilter, setCooldownFilter] = useState(
    () => searchParams.get("forum_cooldown") ?? "all",
  );
  const [status, setStatus] = useState<StatusFilter>(() =>
    parseForumStatus(searchParams.get("forum_status")),
  );
  const [searchQuery, setSearchQuery] = useState(() => searchParams.get("forum_q") ?? "");
  const [skip, setSkip] = useState(
    () => (parseForumPage(searchParams.get("forum_page")) - 1) * PAGE_SIZE,
  );
  const [showCategoryManager, setShowCategoryManager] = useState(false);
  const [selectedPostId, setSelectedPostId] = useState<string | null>(null);
  const [categoryKey, setCategoryKey] = useState("");
  const [categoryName, setCategoryName] = useState("");
  const [categoryDescription, setCategoryDescription] = useState("");
  const [categoryColor, setCategoryColor] = useState("neutral");
  const [categoryIcon, setCategoryIcon] = useState("message-square");

  useEffect(() => {
    const draftKeys = [
      "title",
      "content",
      "category",
      "chip_id",
      "target_id",
      "target_type",
      "cooldown_id",
      "labels",
    ];
    if (!draftKeys.some((key) => searchParams.has(key))) return;
    router.replace(`/forum/new?${searchParams.toString()}`);
  }, [router, searchParams]);

  const params: ListForumPostsParams = {
    skip,
    limit: PAGE_SIZE,
    category: category === "all" ? undefined : category,
    label: labelFilter === "all" ? undefined : labelFilter,
    cooldown_id: cooldownFilter === "all" ? undefined : cooldownFilter,
    status: status === "all" ? null : status,
    q: searchQuery.trim() || undefined,
  };
  const { data, isLoading } = useListForumPosts(params, {
    query: { staleTime: 30_000 },
  });
  const posts = data?.data.posts ?? [];
  const total = data?.data.total ?? 0;
  const currentPage = Math.floor(skip / PAGE_SIZE);
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const { data: categoriesResponse } = useListForumCategories(undefined, {
    query: { staleTime: 60_000 },
  });
  const categories = useMemo(
    () =>
      categoriesResponse?.data.categories.map(toForumCategoryDefinition) ??
      DEFAULT_FORUM_CATEGORIES,
    [categoriesResponse?.data.categories],
  );

  const { data: cooldownsResponse } = useListCooldowns(undefined, {
    query: { staleTime: 60_000 },
  });
  const cooldowns = useMemo(
    () =>
      [...(cooldownsResponse?.data.cooldowns ?? [])].sort((a, b) => {
        const aTime = a.started_at ? new Date(a.started_at).getTime() : 0;
        const bTime = b.started_at ? new Date(b.started_at).getTime() : 0;
        return bTime - aTime || b.cooldown_id.localeCompare(a.cooldown_id);
      }),
    [cooldownsResponse?.data.cooldowns],
  );

  const createCategoryMutation = useCreateForumCategory();
  const deleteCategoryMutation = useDeleteForumCategory();
  const invalidateCategories = () => {
    queryClient.invalidateQueries({
      queryKey: getListForumCategoriesQueryKey(),
    });
  };

  const buildListQuery = (
    nextState: {
      category?: CategoryFilter;
      labelFilter?: string;
      cooldownFilter?: string;
      status?: StatusFilter;
      searchQuery?: string;
      skip?: number;
    } = {},
  ) => {
    const nextCategory = nextState.category ?? category;
    const nextLabelFilter = nextState.labelFilter ?? labelFilter;
    const nextCooldownFilter = nextState.cooldownFilter ?? cooldownFilter;
    const nextStatus = nextState.status ?? status;
    const nextSearchQuery = nextState.searchQuery ?? searchQuery;
    const nextSkip = nextState.skip ?? skip;
    const next = new URLSearchParams();
    const page = Math.floor(nextSkip / PAGE_SIZE) + 1;
    if (page > 1) next.set("forum_page", String(page));
    if (nextCategory !== "all") next.set("forum_category", nextCategory);
    if (nextLabelFilter !== "all") next.set("forum_label", nextLabelFilter);
    if (nextCooldownFilter !== "all") next.set("forum_cooldown", nextCooldownFilter);
    if (nextStatus !== "open") next.set("forum_status", nextStatus);
    if (nextSearchQuery.trim()) next.set("forum_q", nextSearchQuery.trim());
    return next.toString();
  };

  const replaceListQuery = (nextState: {
    category?: CategoryFilter;
    labelFilter?: string;
    cooldownFilter?: string;
    status?: StatusFilter;
    searchQuery?: string;
    skip?: number;
  }) => {
    const next = new URLSearchParams(searchParams.toString());
    next.delete("forum_page");
    next.delete("forum_category");
    next.delete("forum_label");
    next.delete("forum_cooldown");
    next.delete("forum_status");
    next.delete("forum_q");
    const listQuery = buildListQuery(nextState);
    new URLSearchParams(listQuery).forEach((value, key) => next.set(key, value));
    const query = next.toString();
    router.replace(query ? `/forum?${query}` : "/forum", { scroll: false });
  };

  const listReturnQuery = buildListQuery();

  const setCategoryFilter = (nextCategory: CategoryFilter) => {
    setCategory(nextCategory);
    setSkip(0);
    replaceListQuery({ category: nextCategory, skip: 0 });
  };

  const setStatusFilter = (nextStatus: StatusFilter) => {
    setStatus(nextStatus);
    setSkip(0);
    replaceListQuery({ status: nextStatus, skip: 0 });
  };

  const setLabelFilterValue = (nextLabel: string) => {
    setLabelFilter(nextLabel);
    setSkip(0);
    replaceListQuery({ labelFilter: nextLabel, skip: 0 });
  };

  const setCooldownFilterValue = (nextCooldown: string) => {
    setCooldownFilter(nextCooldown);
    setSkip(0);
    replaceListQuery({ cooldownFilter: nextCooldown, skip: 0 });
  };

  const setSearchFilter = (nextSearchQuery: string) => {
    setSearchQuery(nextSearchQuery);
    setSkip(0);
    replaceListQuery({ searchQuery: nextSearchQuery, skip: 0 });
  };

  const clearFilters = () => {
    setCategory("all");
    setLabelFilter("all");
    setCooldownFilter("all");
    setSearchQuery("");
    setSkip(0);
    replaceListQuery({
      category: "all",
      labelFilter: "all",
      cooldownFilter: "all",
      searchQuery: "",
      skip: 0,
    });
  };

  const hasListFilters =
    category !== "all" || labelFilter !== "all" || cooldownFilter !== "all" || !!searchQuery.trim();

  const setPageSkip = (nextSkip: number) => {
    const boundedSkip = Math.max(0, nextSkip);
    setSkip(boundedSkip);
    replaceListQuery({ skip: boundedSkip });
  };

  const submitCategory = async () => {
    const trimmedKey = categoryKey.trim();
    const trimmedName = categoryName.trim();
    if (!trimmedKey || !trimmedName) return;

    await createCategoryMutation.mutateAsync({
      data: {
        key: trimmedKey,
        name: trimmedName,
        description: categoryDescription.trim(),
        color: categoryColor,
        icon: categoryIcon,
        sort_order: null,
      },
    });
    setCategoryKey("");
    setCategoryName("");
    setCategoryDescription("");
    setCategoryColor("neutral");
    setCategoryIcon("message-square");
    invalidateCategories();
  };

  return (
    <PageContainer maxWidth>
      <PageHeader
        title="Forum"
        description="Discuss project-wide calibration work across qubits, couplings, control stack, system policy, and other topics."
        actions={
          <div className="flex flex-wrap gap-2">
            {isOwner && (
              <button
                className="btn btn-ghost btn-sm gap-2"
                onClick={() => setShowCategoryManager((open) => !open)}
              >
                <Settings className="h-4 w-4" />
                Categories
              </button>
            )}
            <Link
              className="btn btn-primary btn-sm gap-2"
              href={
                listReturnQuery
                  ? `/forum/new?from=${encodeURIComponent(listReturnQuery)}`
                  : "/forum/new"
              }
            >
              <Plus className="h-4 w-4" />
              New Thread
            </Link>
          </div>
        }
      />

      <div className="mb-4 overflow-x-auto">
        <div className="tabs tabs-boxed w-fit whitespace-nowrap">
          {FORUM_STATUSES.map((item) => (
            <button
              key={item.id}
              className={`tab tab-sm ${status === item.id ? "tab-active" : ""}`}
              onClick={() => setStatusFilter(item.id as StatusFilter)}
            >
              {item.label}
            </button>
          ))}
          <button
            className={`tab tab-sm ${status === "all" ? "tab-active" : ""}`}
            onClick={() => setStatusFilter("all")}
          >
            All
          </button>
        </div>
      </div>

      <PageFiltersBar className="mb-4 sm:mb-6">
        <PageFiltersBar.Group className="flex-1">
          <PageFiltersBar.Item label="Search" className="sm:min-w-64 sm:flex-1">
            <SearchInput
              value={searchQuery}
              onChange={setSearchFilter}
              placeholder="Search threads"
              className="w-full"
            />
          </PageFiltersBar.Item>
          <PageFiltersBar.Item label="Category" className="sm:min-w-44">
            <select
              aria-label="Filter by category"
              className="select select-bordered select-sm w-full"
              value={category}
              onChange={(event) => setCategoryFilter(event.target.value as CategoryFilter)}
            >
              <option value="all">All categories</option>
              {categories.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </PageFiltersBar.Item>
          <PageFiltersBar.Item label="Label" className="sm:min-w-40">
            <select
              aria-label="Filter by label"
              className="select select-bordered select-sm w-full"
              value={labelFilter}
              onChange={(event) => setLabelFilterValue(event.target.value)}
            >
              <option value="all">All labels</option>
              {FORUM_LABELS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </PageFiltersBar.Item>
          <PageFiltersBar.Item label="Cool-down" className="sm:min-w-52">
            <select
              aria-label="Filter by cool-down"
              className="select select-bordered select-sm w-full"
              value={cooldownFilter}
              onChange={(event) => setCooldownFilterValue(event.target.value)}
            >
              <option value="all">All cool-downs</option>
              {cooldowns.map((cooldown) => (
                <option key={cooldown.cooldown_id} value={cooldown.cooldown_id}>
                  {cooldown.cooldown_id}
                  {cooldown.ended_at ? "" : " (active)"}
                </option>
              ))}
            </select>
          </PageFiltersBar.Item>
        </PageFiltersBar.Group>
        {hasListFilters && (
          <PageFiltersBar.Group position="end">
            <button type="button" className="btn btn-ghost btn-sm gap-1" onClick={clearFilters}>
              <XCircle className="h-4 w-4" />
              Clear
            </button>
          </PageFiltersBar.Group>
        )}
      </PageFiltersBar>

      {showCategoryManager && isOwner && (
        <div className="card bg-base-200 shadow-lg mb-4">
          <div className="card-body">
            <div className="flex items-center justify-between gap-3">
              <h2 className="card-title text-sm">Forum Categories</h2>
              <span className="text-xs text-base-content/50">
                Deleting archives the category and keeps existing threads readable.
              </span>
            </div>
            <div className="mb-4 grid gap-2 sm:grid-cols-[150px_180px_1fr_130px_160px_auto]">
              <input
                className="input input-bordered input-sm"
                value={categoryKey}
                onChange={(event) => setCategoryKey(event.target.value)}
                placeholder="key"
              />
              <input
                className="input input-bordered input-sm"
                value={categoryName}
                onChange={(event) => setCategoryName(event.target.value)}
                placeholder="Name"
              />
              <input
                className="input input-bordered input-sm"
                value={categoryDescription}
                onChange={(event) => setCategoryDescription(event.target.value)}
                placeholder="Description"
              />
              <select
                className="select select-bordered select-sm"
                value={categoryColor}
                onChange={(event) => setCategoryColor(event.target.value)}
              >
                {[
                  "neutral",
                  "primary",
                  "secondary",
                  "accent",
                  "info",
                  "success",
                  "warning",
                  "error",
                  "ghost",
                ].map((color) => (
                  <option key={color} value={color}>
                    {color}
                  </option>
                ))}
              </select>
              <select
                className="select select-bordered select-sm"
                value={categoryIcon}
                onChange={(event) => setCategoryIcon(event.target.value)}
              >
                {[
                  "message-square",
                  "activity",
                  "network",
                  "circuit-board",
                  "settings",
                  "calendar-check",
                ].map((icon) => (
                  <option key={icon} value={icon}>
                    {icon}
                  </option>
                ))}
              </select>
              <button
                className="btn btn-primary btn-sm"
                onClick={submitCategory}
                disabled={
                  !categoryKey.trim() || !categoryName.trim() || createCategoryMutation.isPending
                }
              >
                Add
              </button>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {categories.map((item) => {
                const Icon = item.icon;
                return (
                  <div
                    key={item.id}
                    className="flex items-center justify-between gap-2 rounded-lg border border-base-300 px-3 py-2"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Icon className="h-4 w-4 text-base-content/60" />
                        <span className="truncate text-sm font-medium">{item.label}</span>
                        <span className={`badge badge-xs ${item.badgeClass}`}>{item.id}</span>
                      </div>
                      <p className="truncate text-xs text-base-content/50">{item.description}</p>
                    </div>
                    <button
                      className="btn btn-ghost btn-xs text-error"
                      onClick={() =>
                        deleteCategoryMutation.mutate(
                          { categoryKey: item.id },
                          {
                            onSuccess: () => {
                              if (category === item.id) {
                                setCategoryFilter("all");
                              }
                              invalidateCategories();
                            },
                          },
                        )
                      }
                      disabled={deleteCategoryMutation.isPending}
                      title="Archive category"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-16">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      ) : posts.length === 0 ? (
        <EmptyState
          title="No forum threads yet"
          description="Project discussions and mentions will appear here."
          emoji="speech-balloon"
        />
      ) : (
        <>
          <div className="space-y-3">
            {posts.map((post) => (
              <ForumThreadCard
                key={post.id}
                post={post}
                categories={categories}
                isSelected={selectedPostId === post.id}
                onSelect={() => setSelectedPostId(post.id)}
              />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-2">
              <button
                className="btn btn-sm btn-ghost"
                disabled={currentPage === 0}
                onClick={() => setPageSkip(skip - PAGE_SIZE)}
              >
                Previous
              </button>
              <span className="text-sm text-base-content/60">
                Page {currentPage + 1} of {totalPages}
              </span>
              <button
                className="btn btn-sm btn-ghost"
                disabled={currentPage >= totalPages - 1}
                onClick={() => setPageSkip(skip + PAGE_SIZE)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
      <ForumThreadPreviewSidebar
        postId={selectedPostId}
        categories={categories}
        currentUsername={user?.username}
        isOwner={isOwner}
        projectId={projectId}
        returnQuery={listReturnQuery}
        onClose={() => setSelectedPostId(null)}
      />
    </PageContainer>
  );
}
