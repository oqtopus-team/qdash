"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  CalendarDays,
  Crosshair,
  ExternalLink,
  Lock,
  MessageSquare,
  Plus,
  Settings,
  Trash2,
  Unlock,
  X,
} from "lucide-react";

import {
  getListForumCategoriesQueryKey,
  getListForumPostsQueryKey,
  useCloseForumPost,
  useCreateForumCategory,
  useCreateForumPost,
  useDeleteForumCategory,
  useGetForumPost,
  useGetForumPostReplies,
  useListForumCategories,
  useListForumPosts,
  useReopenForumPost,
} from "@/client/forum/forum";
import { EmptyState } from "@/components/ui/EmptyState";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { useForumAiReply } from "@/hooks/useForumAiReply";
import { useImageUpload } from "@/hooks/useImageUpload";
import { formatRelativeTime } from "@/lib/utils/datetime";
import type { ForumPostResponse, ListForumPostsParams } from "@/schemas";

import {
  DEFAULT_FORUM_CATEGORIES,
  FORUM_LABELS,
  getForumCategory,
  formatForumPostNumber,
  getForumLabel,
  toForumCategoryDefinition,
  type ForumCategoryDefinition,
} from "./categories";
import { ForumLabelSelector } from "./ForumLabelSelector";

const ForumBlockEditor = dynamic(
  () => import("./ForumBlockEditor").then((m) => ({ default: m.ForumBlockEditor })),
  { ssr: false },
);

const PAGE_SIZE = 30;

type CategoryFilter = "all" | NonNullable<ListForumPostsParams["category"]>;
type StatusFilter = "open" | "closed" | "all";

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
  canManage,
  isSelected,
  onSelect,
  onClose,
  onReopen,
}: {
  post: ForumPostResponse;
  categories: ForumCategoryDefinition[];
  canManage: boolean;
  isSelected: boolean;
  onSelect: () => void;
  onClose: (postId: string) => void;
  onReopen: (postId: string) => void;
}) {
  const category = getForumCategory(post.category, categories);
  const targetContext = postTargetContext(post);
  const Icon = category.icon;
  const displayNumber = formatForumPostNumber(post.number);
  const primaryLabel = (post.labels ?? [])[0];
  const labelDef = primaryLabel ? getForumLabel(primaryLabel) : null;

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
      } ${post.is_closed ? "opacity-70" : ""}`}
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
              {post.is_closed && <span className="badge badge-sm badge-ghost">Closed</span>}
            </div>
          </div>

          <div className="mt-1 line-clamp-1 text-sm leading-6 text-base-content/60">
            <MarkdownContent content={post.content} preview />
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-base-content/50">
            <span>{post.username}</span>
            <span>{formatRelativeTime(post.created_at)}</span>
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

      {canManage && (
        <div className="flex justify-end border-t border-base-300 px-3 py-2 sm:px-4">
          {post.is_closed ? (
            <button
              className="btn btn-ghost btn-xs gap-1"
              onClick={(event) => {
                event.stopPropagation();
                onReopen(post.id);
              }}
            >
              <Unlock className="h-3 w-3" />
              Reopen
            </button>
          ) : (
            <button
              className="btn btn-ghost btn-xs gap-1"
              onClick={(event) => {
                event.stopPropagation();
                onClose(post.id);
              }}
            >
              <Lock className="h-3 w-3" />
              Close
            </button>
          )}
        </div>
      )}
    </article>
  );
}

function ForumThreadPreviewSidebar({
  postId,
  categories,
  onClose,
}: {
  postId: string | null;
  categories: ForumCategoryDefinition[];
  onClose: () => void;
}) {
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
  const post = postResponse?.data;
  const replies = repliesResponse?.data ?? [];
  const isOpen = !!postId;
  const category = post ? getForumCategory(post.category, categories) : null;
  const label = post?.labels?.[0] ? getForumLabel(post.labels[0]) : null;
  const targetContext = post ? postTargetContext(post) : null;

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
                  {post.is_closed && <span className="badge badge-sm badge-ghost">Closed</span>}
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
                  <Link href={`/forum/${post.id}`} className="btn btn-primary btn-sm gap-1">
                    <ExternalLink className="h-3.5 w-3.5" />
                    Open full page
                  </Link>
                </div>
              </header>

              {(targetContext || post.cooldown_id) && (
                <div className="rounded-lg bg-base-200/60 p-3 text-xs">
                  <div className="grid gap-2 sm:grid-cols-2">
                    {targetContext && (
                      <div>
                        <div className="text-base-content/45">Target</div>
                        <div className="mt-1 font-medium">
                          {formatTargetLabel(targetContext.targetType, targetContext.targetId)} ·{" "}
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
                  </div>
                </div>
              )}

              <section>
                <h3 className="mb-2 text-sm font-semibold">Root thread</h3>
                <div className="rounded-lg border border-base-300 bg-base-100 p-4">
                  <MarkdownContent
                    content={post.content}
                    className="text-sm text-base-content/80"
                  />
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
                        <MarkdownContent
                          content={reply.content}
                          preview
                          className="line-clamp-3 text-sm text-base-content/70"
                        />
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
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const { isOwner } = useProject();
  const [category, setCategory] = useState<CategoryFilter>("all");
  const [labelFilter, setLabelFilter] = useState<string>("all");
  const [status, setStatus] = useState<StatusFilter>("open");
  const [skip, setSkip] = useState(0);
  const [showComposer, setShowComposer] = useState(false);
  const [showCategoryManager, setShowCategoryManager] = useState(false);
  const [selectedPostId, setSelectedPostId] = useState<string | null>(null);
  const [hasAppliedDraftParams, setHasAppliedDraftParams] = useState(false);
  const [draftTargetContext, setDraftTargetContext] = useState<ForumTargetContext | null>(null);
  const [draftCooldownId, setDraftCooldownId] = useState<string | null>(null);
  const [newCategory, setNewCategory] = useState("qubit");
  const [selectedLabels, setSelectedLabels] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [contentBlocks, setContentBlocks] = useState<Record<string, unknown>[]>([]);
  const [categoryKey, setCategoryKey] = useState("");
  const [categoryName, setCategoryName] = useState("");
  const [categoryDescription, setCategoryDescription] = useState("");
  const [categoryColor, setCategoryColor] = useState("neutral");
  const [categoryIcon, setCategoryIcon] = useState("message-square");
  const { uploadImage } = useImageUpload("forum");

  useEffect(() => {
    if (hasAppliedDraftParams) return;
    const draftTitle = searchParams.get("title");
    const draftContent = searchParams.get("content");
    const draftCategory = searchParams.get("category");
    const chipId = searchParams.get("chip_id");
    const targetId = searchParams.get("target_id");
    const targetType = normalizeTargetType(searchParams.get("target_type"));
    const draftLabels = searchParams.get("labels");
    const cooldownId = searchParams.get("cooldown_id");
    if (!draftTitle && !draftContent && !draftCategory) {
      setHasAppliedDraftParams(true);
      return;
    }
    if (draftCategory) {
      setNewCategory(draftCategory);
      setCategory(draftCategory as CategoryFilter);
    }
    if (draftTitle) setTitle(draftTitle);
    if (draftContent) setContent(draftContent);
    if (draftLabels) {
      setSelectedLabels(
        draftLabels
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      );
    }
    if (chipId && targetId && targetType) {
      setDraftTargetContext({ chipId, targetType, targetId });
    }
    if (cooldownId) setDraftCooldownId(cooldownId);
    setContentBlocks([]);
    setShowComposer(true);
    setHasAppliedDraftParams(true);
  }, [hasAppliedDraftParams, searchParams]);

  const params: ListForumPostsParams = {
    skip,
    limit: PAGE_SIZE,
    category: category === "all" ? undefined : category,
    label: labelFilter === "all" ? undefined : labelFilter,
    is_closed: status === "all" ? null : status === "closed" ? true : false,
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

  const createMutation = useCreateForumPost();
  const createCategoryMutation = useCreateForumCategory();
  const deleteCategoryMutation = useDeleteForumCategory();
  const closeMutation = useCloseForumPost();
  const reopenMutation = useReopenForumPost();
  const { triggerAiReply } = useForumAiReply();

  const invalidateList = () => {
    queryClient.invalidateQueries({ queryKey: getListForumPostsQueryKey() });
  };

  const invalidateCategories = () => {
    queryClient.invalidateQueries({
      queryKey: getListForumCategoriesQueryKey(),
    });
  };

  const submitThread = async () => {
    const trimmedTitle = title.trim();
    const trimmedContent = content.trim();
    if (!trimmedTitle || !trimmedContent) return;

    const response = await createMutation.mutateAsync({
      data: {
        category: newCategory,
        title: trimmedTitle,
        content: trimmedContent,
        content_blocks: contentBlocks,
        parent_id: null,
        labels: selectedLabels,
        chip_id: draftTargetContext?.chipId,
        target_type: draftTargetContext?.targetType,
        target_id: draftTargetContext?.targetId,
        cooldown_id: draftCooldownId,
      },
    });
    setTitle("");
    setContent("");
    setContentBlocks([]);
    setSelectedLabels([]);
    setShowComposer(false);
    setDraftTargetContext(null);
    setDraftCooldownId(null);
    invalidateList();
    if (/@qdash\b/i.test(trimmedContent)) {
      triggerAiReply(response.data.id, trimmedContent, invalidateList);
    }
  };

  const setCategoryFilter = (nextCategory: CategoryFilter) => {
    setCategory(nextCategory);
    setSkip(0);
  };

  const setStatusFilter = (nextStatus: StatusFilter) => {
    setStatus(nextStatus);
    setSkip(0);
  };

  const toggleSelectedLabel = (label: string) => {
    setSelectedLabels((current) => (current.includes(label) ? [] : [label]));
  };

  const setLabelFilterValue = (nextLabel: string) => {
    setLabelFilter(nextLabel);
    setSkip(0);
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
            <button
              className="btn btn-primary btn-sm gap-2"
              onClick={() => setShowComposer((open) => !open)}
            >
              {showComposer ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
              {showComposer ? "Close" : "New Thread"}
            </button>
          </div>
        }
      />

      <div className="mb-4">
        <div className="tabs tabs-boxed w-fit">
          {(["open", "closed", "all"] as const).map((item) => (
            <button
              key={item}
              className={`tab tab-sm ${status === item ? "tab-active" : ""}`}
              onClick={() => setStatusFilter(item)}
            >
              {item.charAt(0).toUpperCase() + item.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-4 rounded-lg border border-base-300 bg-base-100 px-3 py-2">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => setCategoryFilter("all")}
              className={`btn btn-xs ${category === "all" ? "btn-neutral" : "btn-ghost"}`}
            >
              All categories
            </button>
            {categories.map((item) => {
              const Icon = item.icon;
              const active = category === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setCategoryFilter(active ? "all" : item.id)}
                  className={`btn btn-xs gap-1 ${active ? "btn-neutral" : "btn-ghost"}`}
                  title={item.description}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {item.shortLabel}
                </button>
              );
            })}
          </div>

          <select
            className="select select-bordered select-xs w-36"
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
        </div>

        {(category !== "all" || labelFilter !== "all") && (
          <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-base-300 pt-2 text-xs text-base-content/55">
            <span>Filtered by</span>
            {category !== "all" && (
              <button
                className="badge badge-outline gap-1"
                onClick={() => setCategoryFilter("all")}
              >
                {getForumCategory(category, categories).label}
                <X className="h-3 w-3" />
              </button>
            )}
            {labelFilter !== "all" && (
              <button
                className="badge badge-outline gap-1"
                onClick={() => setLabelFilterValue("all")}
              >
                {getForumLabel(labelFilter).label}
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        )}
      </div>

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
                              if (newCategory === item.id) {
                                setNewCategory(
                                  categories.find((candidate) => candidate.id !== item.id)?.id ??
                                    "other",
                                );
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

      {showComposer && (
        <div className="card bg-base-200 shadow-lg mb-4">
          <div className="card-body">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="card-title text-sm">New Thread</h2>
              {draftTargetContext && (
                <span className="badge badge-outline gap-1">
                  <Crosshair className="h-3 w-3" />
                  {formatTargetLabel(
                    draftTargetContext.targetType,
                    draftTargetContext.targetId,
                  )} ·{" "}
                  {draftTargetContext.chipId}
                </span>
              )}
              {draftCooldownId && (
                <span className="badge badge-outline">Cooldown · {draftCooldownId}</span>
              )}
            </div>
            <div className="grid gap-3 sm:grid-cols-[220px_1fr]">
              <select
                className="select select-bordered select-sm w-full"
                value={newCategory}
                onChange={(event) => setNewCategory(event.target.value)}
              >
                {categories.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
              <input
                className="input input-bordered input-sm w-full"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Thread title"
              />
            </div>
            <ForumLabelSelector selectedLabels={selectedLabels} onToggle={toggleSelectedLabel} />
            <ForumBlockEditor
              key={showComposer ? "composer-open" : "composer-closed"}
              legacyMarkdown={content}
              onChange={(blocks, markdown) => {
                setContentBlocks(blocks);
                setContent(markdown);
              }}
              onImageUpload={uploadImage}
            />
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-xs text-base-content/50">
                Type <kbd className="kbd kbd-xs">/</kbd> for blocks (table, image, heading, list,
                …). Use <span className="font-mono">@username</span> in text to mention members.
              </span>
              <button
                type="button"
                className="btn btn-sm btn-primary"
                onClick={submitThread}
                disabled={!title.trim() || !content.trim() || createMutation.isPending}
              >
                {createMutation.isPending ? (
                  <span className="loading loading-spinner loading-xs" />
                ) : (
                  "Post"
                )}
              </button>
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
                canManage={isOwner || user?.username === post.username}
                isSelected={selectedPostId === post.id}
                onSelect={() => setSelectedPostId(post.id)}
                onClose={(postId) =>
                  closeMutation.mutate({ postId }, { onSuccess: invalidateList })
                }
                onReopen={(postId) =>
                  reopenMutation.mutate({ postId }, { onSuccess: invalidateList })
                }
              />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-2">
              <button
                className="btn btn-sm btn-ghost"
                disabled={currentPage === 0}
                onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}
              >
                Previous
              </button>
              <span className="text-sm text-base-content/60">
                Page {currentPage + 1} of {totalPages}
              </span>
              <button
                className="btn btn-sm btn-ghost"
                disabled={currentPage >= totalPages - 1}
                onClick={() => setSkip(skip + PAGE_SIZE)}
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
        onClose={() => setSelectedPostId(null)}
      />
    </PageContainer>
  );
}
