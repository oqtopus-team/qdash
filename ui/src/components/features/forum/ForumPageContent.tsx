"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useQueryClient } from "@tanstack/react-query";
import { Lock, MessageSquare, Plus, Settings, Trash2, Unlock, X } from "lucide-react";

import {
  getListForumCategoriesQueryKey,
  getListForumPostsQueryKey,
  useCloseForumPost,
  useCreateForumCategory,
  useCreateForumPost,
  useDeleteForumCategory,
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
  getForumCategory,
  toForumCategoryDefinition,
  type ForumCategoryDefinition,
} from "./categories";

const ForumBlockEditor = dynamic(
  () => import("./ForumBlockEditor").then((m) => ({ default: m.ForumBlockEditor })),
  { ssr: false },
);

const PAGE_SIZE = 30;

type CategoryFilter = "all" | NonNullable<ListForumPostsParams["category"]>;
type StatusFilter = "open" | "closed" | "all";

function ForumThreadCard({
  post,
  categories,
  canManage,
  onClose,
  onReopen,
}: {
  post: ForumPostResponse;
  categories: ForumCategoryDefinition[];
  canManage: boolean;
  onClose: (postId: string) => void;
  onReopen: (postId: string) => void;
}) {
  const category = getForumCategory(post.category, categories);
  const Icon = category.icon;

  return (
    <div
      className={`bg-base-100 rounded-lg border border-base-300 hover:border-primary/50 transition-colors ${
        post.is_closed ? "opacity-75" : ""
      }`}
    >
      <Link href={`/forum/${post.id}`} className="block p-4">
        <div className="flex items-start gap-3">
          <div className="hidden sm:flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-base-200">
            <UserAvatar username={post.username} avatarKey={post.avatar_key} size={28} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className={`badge badge-sm ${category.badgeClass}`}>
                <Icon className="h-3 w-3" />
                {category.shortLabel}
              </span>
              <span className="badge badge-sm badge-neutral">{post.username}</span>
              <span className="text-xs text-base-content/40">
                {formatRelativeTime(post.created_at)}
              </span>
              {post.is_closed && <span className="badge badge-sm badge-ghost">Closed</span>}
            </div>
            <h2 className="mb-1 truncate text-sm font-semibold">{post.title}</h2>
            <div className="line-clamp-2 text-sm text-base-content/75">
              <MarkdownContent content={post.content} preview />
            </div>
            <div className="mt-3 flex items-center gap-3 text-xs text-base-content/50">
              <span className="flex items-center gap-1">
                <MessageSquare className="h-3.5 w-3.5" />
                {post.reply_count ?? 0} replies
              </span>
              <span>{category.description}</span>
            </div>
          </div>
        </div>
      </Link>
      {canManage && (
        <div className="border-t border-base-300 px-4 py-2">
          {post.is_closed ? (
            <button className="btn btn-ghost btn-xs gap-1" onClick={() => onReopen(post.id)}>
              <Unlock className="h-3 w-3" />
              Reopen
            </button>
          ) : (
            <button className="btn btn-ghost btn-xs gap-1" onClick={() => onClose(post.id)}>
              <Lock className="h-3 w-3" />
              Close
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function ForumPageContent() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { isOwner } = useProject();
  const [category, setCategory] = useState<CategoryFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("open");
  const [skip, setSkip] = useState(0);
  const [showComposer, setShowComposer] = useState(false);
  const [showCategoryManager, setShowCategoryManager] = useState(false);
  const [newCategory, setNewCategory] = useState("qubit");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [contentBlocks, setContentBlocks] = useState<Record<string, unknown>[]>([]);
  const [categoryKey, setCategoryKey] = useState("");
  const [categoryName, setCategoryName] = useState("");
  const [categoryDescription, setCategoryDescription] = useState("");
  const [categoryColor, setCategoryColor] = useState("neutral");
  const [categoryIcon, setCategoryIcon] = useState("message-square");
  const { uploadImage } = useImageUpload("forum");

  const params: ListForumPostsParams = {
    skip,
    limit: PAGE_SIZE,
    category: category === "all" ? undefined : category,
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
      },
    });
    setTitle("");
    setContent("");
    setContentBlocks([]);
    setShowComposer(false);
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

      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        {categories.map((item) => {
          const Icon = item.icon;
          const active = category === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setCategoryFilter(active ? "all" : item.id)}
              className={`rounded-lg border p-3 text-left transition-colors ${
                active
                  ? "border-primary bg-primary/10"
                  : "border-base-300 bg-base-100 hover:border-primary/50"
              }`}
            >
              <div className="mb-2 flex items-center gap-2">
                <Icon className="h-4 w-4 text-base-content/70" />
                <span className="text-sm font-semibold">{item.label}</span>
              </div>
              <p className="text-xs text-base-content/60">{item.description}</p>
            </button>
          );
        })}
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

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="tabs tabs-boxed">
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
        {category !== "all" && (
          <button className="btn btn-ghost btn-xs gap-1" onClick={() => setCategoryFilter("all")}>
            <X className="h-3 w-3" />
            Clear category
          </button>
        )}
      </div>

      {showComposer && (
        <div className="card bg-base-200 shadow-lg mb-4">
          <div className="card-body">
            <h2 className="card-title text-sm">New Thread</h2>
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
            <ForumBlockEditor
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
    </PageContainer>
  );
}
