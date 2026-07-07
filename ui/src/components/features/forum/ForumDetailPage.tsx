"use client";

import { useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CalendarDays,
  Lock,
  MessageSquare,
  Pencil,
  Crosshair,
  Tag,
  Trash2,
  Unlock,
  UserRound,
} from "lucide-react";

import { useListChips } from "@/client/chip/chip";
import { useListCooldowns } from "@/client/cooldown/cooldown";
import {
  getGetForumPostQueryKey,
  getGetForumPostRepliesQueryKey,
  getListForumPostsQueryKey,
  useCloseForumPost,
  useCreateForumPost,
  useDeleteForumPost,
  useGetForumPost,
  useGetForumPostReplies,
  useListForumCategories,
  useReopenForumPost,
  useUpdateForumPost,
} from "@/client/forum/forum";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { QdashBotAvatar, UserAvatar } from "@/components/ui/UserAvatar";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { useForumAiReply } from "@/hooks/useForumAiReply";
import { useImageUpload } from "@/hooks/useImageUpload";
import { formatDateTimeCompact, formatRelativeTime } from "@/lib/utils/datetime";
import type { ForumPostResponse } from "@/schemas";

import {
  formatForumPostNumber,
  getForumCategory,
  getForumLabel,
  toForumCategoryDefinition,
} from "./categories";
import { ForumLabelPicker } from "./ForumLabelSelector";
import { ForumBlockViewer, type ForumBlockSnapshotGetter } from "./ForumBlockEditor";

const ForumBlockEditor = dynamic(
  () => import("./ForumBlockEditor").then((m) => ({ default: m.ForumBlockEditor })),
  { ssr: false },
);

const REPLY_PAGE_SIZE = 100;

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

function dashboardTargetHref(context: ForumTargetContext): string {
  if (context.targetType === "qubit") return `/chip/${context.chipId}/qubit/${context.targetId}`;
  return `/dashboard?chip=${encodeURIComponent(context.chipId)}&type=coupling`;
}

function isEdited(createdAt: string, updatedAt: string): boolean {
  return Math.abs(new Date(updatedAt).getTime() - new Date(createdAt).getTime()) > 1000;
}

function PostBody({
  post,
  currentUsername,
  canEdit: canEditOverride,
  onEdit,
  onDelete,
  editing,
  editTitle,
  editContent,
  editInitialBlocks,
  editLegacyMarkdown,
  editMetaControls,
  onTitleChange,
  onEditChange,
  onCancel,
  onSave,
  saving,
  onImageUpload,
  editorSnapshotRef,
}: {
  post: ForumPostResponse;
  currentUsername?: string;
  canEdit?: boolean;
  onEdit: () => void;
  onDelete: () => void;
  editing: boolean;
  editTitle?: string;
  /** Current markdown projection — used only to gate the Save button. */
  editContent: string;
  editInitialBlocks: Record<string, unknown>[];
  editLegacyMarkdown: string;
  editMetaControls?: ReactNode;
  onTitleChange?: (value: string) => void;
  onEditChange: (blocks: Record<string, unknown>[], markdown: string) => void;
  onCancel: () => void;
  onSave: () => void;
  saving: boolean;
  onImageUpload: (file: File) => Promise<string>;
  editorSnapshotRef?: MutableRefObject<ForumBlockSnapshotGetter | null>;
}) {
  const canEdit = canEditOverride ?? currentUsername === post.username;
  const isAi = post.is_ai_reply || post.username === "qdash";

  return (
    <div
      className={`rounded-lg border p-4 ${
        isAi ? "border-primary/30 bg-primary/5" : "border-base-300 bg-base-100"
      }`}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {isAi ? (
            <QdashBotAvatar size={24} />
          ) : (
            <UserAvatar username={post.username} avatarKey={post.avatar_key} size={24} />
          )}
          <span className={`badge badge-sm ${isAi ? "badge-primary" : "badge-neutral"}`}>
            {post.username}
          </span>
          <span className="text-xs text-base-content/40">
            {formatRelativeTime(post.created_at)}
          </span>
          {isEdited(post.created_at, post.updated_at) && (
            <span className="text-xs italic text-base-content/30">(edited)</span>
          )}
        </div>
        {canEdit && !editing && !isAi && (
          <div className="flex items-center gap-1">
            <button
              className="btn btn-ghost btn-sm btn-square text-base-content/40 hover:text-primary"
              onClick={onEdit}
              title="Edit"
            >
              <Pencil className="h-4 w-4" />
            </button>
            <button
              className="btn btn-ghost btn-sm btn-square text-base-content/40 hover:text-error"
              onClick={onDelete}
              title="Delete"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
      {editing ? (
        <div className="space-y-3">
          {editMetaControls}
          {onTitleChange && (
            <input
              className="input input-bordered input-sm w-full"
              value={editTitle ?? ""}
              onChange={(event) => onTitleChange(event.target.value)}
              placeholder="Thread title"
            />
          )}
          <ForumBlockEditor
            initialBlocks={editInitialBlocks}
            legacyMarkdown={editLegacyMarkdown}
            onChange={onEditChange}
            onImageUpload={onImageUpload}
            snapshotRef={editorSnapshotRef}
          />
          <div className="flex justify-end gap-2">
            <button className="btn btn-ghost btn-sm" onClick={onCancel}>
              Cancel
            </button>
            <button
              className="btn btn-primary btn-sm"
              onClick={onSave}
              disabled={!editContent.trim() || saving}
            >
              {saving ? <span className="loading loading-spinner loading-xs" /> : "Save"}
            </button>
          </div>
        </div>
      ) : (
        (() => {
          const displayBlocks = (post.content_blocks ?? []) as Record<string, unknown>[];
          return displayBlocks.length > 0 ? (
            <ForumBlockViewer blocks={displayBlocks} />
          ) : (
            <MarkdownContent content={post.content} className="text-sm text-base-content/80" />
          );
        })()
      )}
    </div>
  );
}

export function ForumDetailPage({ postId }: { postId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { isOwner } = useProject();
  const { uploadImage } = useImageUpload("forum");
  const currentUsername = user?.username;
  const [replyText, setReplyText] = useState("");
  const [replyBlocks, setReplyBlocks] = useState<Record<string, unknown>[]>([]);
  // Bumped after a successful reply to remount (reset) the composer editor.
  const [replyKey, setReplyKey] = useState(0);
  const [editingRoot, setEditingRoot] = useState(false);
  const [editRootTitle, setEditRootTitle] = useState("");
  const [editRootContent, setEditRootContent] = useState("");
  const [editRootBlocks, setEditRootBlocks] = useState<Record<string, unknown>[]>([]);
  const editRootSnapshotRef = useRef<ForumBlockSnapshotGetter | null>(null);
  const [targetDraftChipId, setTargetDraftChipId] = useState("");
  const [targetDraftType, setTargetDraftType] = useState<"qubit" | "coupling">("qubit");
  const [targetDraftId, setTargetDraftId] = useState("");
  const [cooldownDraftId, setCooldownDraftId] = useState("");
  const [editingReplyId, setEditingReplyId] = useState<string | null>(null);
  const [editReplyContent, setEditReplyContent] = useState("");
  const [editReplyBlocks, setEditReplyBlocks] = useState<Record<string, unknown>[]>([]);
  const editReplySnapshotRef = useRef<ForumBlockSnapshotGetter | null>(null);
  const replyComposerSnapshotRef = useRef<ForumBlockSnapshotGetter | null>(null);
  const [replyLimit, setReplyLimit] = useState(REPLY_PAGE_SIZE);

  const { data: postResponse, isLoading: postLoading } = useGetForumPost(postId, {
    query: { staleTime: 30_000 },
  });
  const post = postResponse?.data ?? null;
  const { data: repliesResponse, isLoading: repliesLoading } = useGetForumPostReplies(
    postId,
    { skip: 0, limit: replyLimit },
    { query: { enabled: !!post } },
  );
  const replies = repliesResponse?.data ?? [];
  const { data: categoriesResponse } = useListForumCategories(undefined, {
    query: { staleTime: 60_000 },
  });
  const categories = useMemo(
    () => categoriesResponse?.data.categories.map(toForumCategoryDefinition) ?? [],
    [categoriesResponse?.data.categories],
  );
  const { data: chipsResponse } = useListChips({ query: { staleTime: 60_000 } });
  const chips = chipsResponse?.data.chips ?? [];
  const { data: cooldownsResponse } = useListCooldowns(
    { chip_id: targetDraftChipId || undefined },
    { query: { enabled: !!targetDraftChipId || !!post?.cooldown_id, staleTime: 60_000 } },
  );
  const cooldowns = cooldownsResponse?.data.cooldowns ?? [];
  const selectedCooldown = cooldowns.find((cooldown) => cooldown.cooldown_id === cooldownDraftId);
  const currentPostCooldown = cooldowns.find(
    (cooldown) => cooldown.cooldown_id === post?.cooldown_id,
  );

  const createMutation = useCreateForumPost();
  const updateMutation = useUpdateForumPost();
  const deleteMutation = useDeleteForumPost();
  const closeMutation = useCloseForumPost();
  const reopenMutation = useReopenForumPost();
  const {
    isGenerating,
    statusMessage: aiStatus,
    error: aiError,
    triggerAiReply,
  } = useForumAiReply();

  useEffect(() => {
    if (!post) return;
    const context = postTargetContext(post);
    setTargetDraftChipId(context?.chipId ?? "");
    setTargetDraftType(context?.targetType ?? "qubit");
    setTargetDraftId(context?.targetId ?? "");
    setCooldownDraftId(post.cooldown_id ?? "");
  }, [post]);

  const invalidateThread = () => {
    queryClient.invalidateQueries({
      queryKey: getGetForumPostQueryKey(postId),
    });
    queryClient.invalidateQueries({
      queryKey: getGetForumPostRepliesQueryKey(postId),
    });
    queryClient.invalidateQueries({ queryKey: getListForumPostsQueryKey() });
  };

  const syncRootPostCache = (nextPost: ForumPostResponse) => {
    queryClient.setQueryData(getGetForumPostQueryKey(nextPost.id), (current: unknown) =>
      current && typeof current === "object" ? { ...current, data: nextPost } : current,
    );
  };

  const syncReplyCache = (nextReply: ForumPostResponse) => {
    queryClient.setQueriesData(
      { queryKey: getGetForumPostRepliesQueryKey(postId), exact: false },
      (current: unknown) => {
        if (!Array.isArray(current)) return current;
        return current.map((reply) =>
          reply && typeof reply === "object" && "id" in reply && reply.id === nextReply.id
            ? nextReply
            : reply,
        );
      },
    );
  };

  const handleStartEditRoot = () => {
    if (!post) return;
    setEditRootTitle(post.title ?? "");
    setEditRootContent(post.content);
    setEditRootBlocks((post.content_blocks ?? []) as Record<string, unknown>[]);
    setEditingRoot(true);
  };

  const handleSaveRoot = async () => {
    if (!post) return;
    const snapshot = await editRootSnapshotRef.current?.();
    const nextContent = (snapshot?.markdown ?? editRootContent).trim();
    const nextBlocks = snapshot?.blocks ?? editRootBlocks;
    if (!nextContent) return;
    const response = await updateMutation.mutateAsync({
      postId: post.id,
      data: {
        category: post.category,
        title: editRootTitle.trim() || null,
        content: nextContent,
        content_blocks: nextBlocks,
        labels: post.labels ?? [],
      },
    });
    syncRootPostCache(response.data);
    setEditRootContent(nextContent);
    setEditRootBlocks(nextBlocks);
    setEditingRoot(false);
    invalidateThread();
  };

  const handleAddReply = async () => {
    if (!post) return;
    const snapshot = await replyComposerSnapshotRef.current?.();
    const trimmed = (snapshot?.markdown ?? replyText).trim();
    const nextBlocks = snapshot?.blocks ?? replyBlocks;
    if (!trimmed) return;
    await createMutation.mutateAsync({
      data: {
        category: post.category,
        title: null,
        content: trimmed,
        content_blocks: nextBlocks,
        parent_id: post.id,
      },
    });
    setReplyText("");
    setReplyBlocks([]);
    setReplyKey((key) => key + 1);
    invalidateThread();
    if (/@qdash\b/i.test(trimmed)) {
      triggerAiReply(post.id, trimmed, invalidateThread);
    }
  };

  const handleStartEditReply = (reply: ForumPostResponse) => {
    setEditingReplyId(reply.id);
    setEditReplyContent(reply.content);
    setEditReplyBlocks((reply.content_blocks ?? []) as Record<string, unknown>[]);
  };

  const handleSaveReply = async () => {
    if (!editingReplyId) return;
    const snapshot = await editReplySnapshotRef.current?.();
    const nextContent = (snapshot?.markdown ?? editReplyContent).trim();
    const nextBlocks = snapshot?.blocks ?? editReplyBlocks;
    if (!nextContent) return;
    const response = await updateMutation.mutateAsync({
      postId: editingReplyId,
      data: {
        title: null,
        content: nextContent,
        content_blocks: nextBlocks,
      },
    });
    syncReplyCache(response.data);
    setEditReplyContent(nextContent);
    setEditReplyBlocks(nextBlocks);
    setEditingReplyId(null);
    invalidateThread();
  };

  const updateRootMetadata = async ({
    category: nextCategory,
    labels: nextLabels,
    chipId: nextChipId,
    targetType: nextTargetType,
    targetId: nextTargetId,
    cooldownId: nextCooldownId,
  }: {
    category?: string;
    labels?: string[];
    chipId?: string | null;
    targetType?: "qubit" | "coupling" | null;
    targetId?: string | null;
    cooldownId?: string | null;
  }) => {
    if (!post || !canManage) return;
    await updateMutation.mutateAsync({
      postId: post.id,
      data: {
        category: nextCategory ?? post.category,
        content: post.content,
        content_blocks: (post.content_blocks ?? []) as Record<string, unknown>[],
        labels: nextLabels ?? post.labels ?? [],
        ...(nextCooldownId !== undefined ? { cooldown_id: nextCooldownId } : {}),
        ...(nextChipId !== undefined || nextTargetType !== undefined || nextTargetId !== undefined
          ? {
              chip_id: nextChipId,
              target_type: nextTargetType,
              target_id: nextTargetId,
            }
          : {}),
      },
    });
    invalidateThread();
  };

  const togglePostLabel = (label: string) => {
    if (!post) return;
    const currentLabels = post.labels ?? [];
    const nextLabels = currentLabels.includes(label) ? [] : [label];
    updateRootMetadata({ labels: nextLabels });
  };

  const saveTargetMetadata = () => {
    updateRootMetadata({
      chipId: targetDraftChipId.trim(),
      targetType: targetDraftType,
      targetId: targetDraftId.trim(),
    });
  };

  const clearTargetMetadata = () => {
    setTargetDraftChipId("");
    setTargetDraftType("qubit");
    setTargetDraftId("");
    updateRootMetadata({ chipId: "", targetType: null, targetId: "" });
  };

  const saveCooldownMetadata = () => {
    updateRootMetadata({ cooldownId: cooldownDraftId });
  };

  const handleDelete = async (targetPostId: string, isRoot: boolean) => {
    await deleteMutation.mutateAsync({ postId: targetPostId });
    if (isRoot) {
      router.push("/forum");
      return;
    }
    invalidateThread();
  };

  if (postLoading) {
    return (
      <div className="flex justify-center py-16">
        <span className="loading loading-spinner loading-lg" />
      </div>
    );
  }

  if (!post) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-16">
        <p className="text-base-content/60">Forum thread not found</p>
        <Link href="/forum" className="btn btn-sm btn-ghost">
          <ArrowLeft className="h-4 w-4" />
          Back to Forum
        </Link>
      </div>
    );
  }

  const category = getForumCategory(post.category, categories);
  const CategoryIcon = category.icon;
  const targetContext = postTargetContext(post);
  const canManage = isOwner || currentUsername === post.username;

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex min-w-0 items-start gap-3">
        <button
          className="btn btn-square btn-ghost btn-sm shrink-0"
          onClick={() => router.push("/forum")}
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="min-w-0">
          <h1 className="flex min-w-0 items-center gap-2 text-xl font-bold">
            {formatForumPostNumber(post.number) && (
              <span className="badge badge-outline shrink-0">
                {formatForumPostNumber(post.number)}
              </span>
            )}
            <span className="truncate">{post.title || "Untitled topic"}</span>
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-base-content/50">
            <span>Opened by {post.username}</span>
            <span>{formatRelativeTime(post.created_at)}</span>
            {post.is_closed && <span className="badge badge-sm badge-ghost">Closed</span>}
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0">
          <PostBody
            post={post}
            currentUsername={currentUsername}
            canEdit={canManage}
            onEdit={handleStartEditRoot}
            onDelete={() => handleDelete(post.id, true)}
            editing={editingRoot}
            editTitle={editRootTitle}
            editContent={editRootContent}
            editInitialBlocks={editRootBlocks}
            editLegacyMarkdown={post.content}
            onTitleChange={setEditRootTitle}
            onEditChange={(blocks, markdown) => {
              setEditRootBlocks(blocks);
              setEditRootContent(markdown);
            }}
            onCancel={() => setEditingRoot(false)}
            onSave={handleSaveRoot}
            saving={updateMutation.isPending}
            onImageUpload={uploadImage}
            editorSnapshotRef={editRootSnapshotRef}
          />

          <div className="divider text-xs text-base-content/40">
            <MessageSquare className="h-3.5 w-3.5" />
            Discussion
          </div>

          <div className="mb-4 ml-4 space-y-2 border-l-2 border-base-300 pl-4">
            {repliesLoading ? (
              <div className="flex justify-center py-3">
                <span className="loading loading-spinner loading-sm" />
              </div>
            ) : replies.length > 0 ? (
              <>
                {replies.map((reply) => (
                  <PostBody
                    key={reply.id}
                    post={reply}
                    currentUsername={currentUsername}
                    onEdit={() => handleStartEditReply(reply)}
                    onDelete={() => handleDelete(reply.id, false)}
                    editing={editingReplyId === reply.id}
                    editContent={editReplyContent}
                    editInitialBlocks={editReplyBlocks}
                    editLegacyMarkdown={reply.content}
                    onEditChange={(blocks, markdown) => {
                      setEditReplyBlocks(blocks);
                      setEditReplyContent(markdown);
                    }}
                    onCancel={() => setEditingReplyId(null)}
                    onSave={handleSaveReply}
                    saving={updateMutation.isPending}
                    onImageUpload={uploadImage}
                    editorSnapshotRef={editReplySnapshotRef}
                  />
                ))}
                {replies.length >= replyLimit && (
                  <div className="flex justify-center py-2">
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => setReplyLimit((current) => current + REPLY_PAGE_SIZE)}
                    >
                      Load more
                    </button>
                  </div>
                )}
              </>
            ) : (
              <p className="py-2 text-xs text-base-content/40">No replies yet</p>
            )}
            {isGenerating && (
              <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 text-sm animate-pulse">
                <div className="flex items-center gap-2">
                  <QdashBotAvatar size={24} />
                  <span className="badge badge-sm badge-primary">qdash</span>
                  <span className="loading loading-dots loading-xs" />
                  <span className="text-xs text-base-content/60">{aiStatus}</span>
                </div>
              </div>
            )}
            {aiError && <div className="px-2 py-1 text-xs text-error">{aiError}</div>}
          </div>

          <div className="ml-4 pb-8 pl-4">
            {post.is_closed ? (
              <div className="rounded-lg border border-base-300 bg-base-200/60 p-3 text-sm text-base-content/60">
                This thread is closed.
              </div>
            ) : (
              <div>
                <ForumBlockEditor
                  key={replyKey}
                  onChange={(blocks, markdown) => {
                    setReplyBlocks(blocks);
                    setReplyText(markdown);
                  }}
                  onImageUpload={uploadImage}
                  snapshotRef={replyComposerSnapshotRef}
                />
                <div className="mt-2 flex items-center justify-between gap-2">
                  <span className="text-xs text-base-content/50">
                    Type <kbd className="kbd kbd-xs">/</kbd> for blocks. Use{" "}
                    <span className="font-mono">@username</span> to mention members.
                  </span>
                  <button
                    type="button"
                    className="btn btn-sm btn-primary"
                    onClick={handleAddReply}
                    disabled={!replyText.trim() || createMutation.isPending}
                  >
                    {createMutation.isPending ? (
                      <span className="loading loading-spinner loading-xs" />
                    ) : (
                      "Reply"
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <aside className="space-y-5 border-t border-base-300 pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
              <CategoryIcon className="h-3.5 w-3.5" />
              Category
            </div>
            {canManage ? (
              <select
                className="select select-bordered select-sm w-full"
                value={post.category}
                disabled={updateMutation.isPending}
                onChange={(event) => updateRootMetadata({ category: event.target.value })}
              >
                {categories.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            ) : (
              <span className={`badge badge-sm ${category.badgeClass}`}>{category.label}</span>
            )}
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
              <Crosshair className="h-3.5 w-3.5" />
              Target
            </div>
            {targetContext && (
              <Link
                href={dashboardTargetHref(targetContext)}
                className="btn btn-outline btn-sm w-full justify-start gap-2 rounded-md normal-case"
              >
                <Crosshair className="h-3.5 w-3.5" />
                <span className="min-w-0 truncate">
                  {formatTargetLabel(targetContext.targetType, targetContext.targetId)} ·{" "}
                  {targetContext.chipId}
                </span>
              </Link>
            )}
            {canManage ? (
              <div className="space-y-2">
                <select
                  className="select select-bordered select-xs w-full"
                  value={targetDraftChipId}
                  onChange={(event) => setTargetDraftChipId(event.target.value)}
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
                    onChange={(event) =>
                      setTargetDraftType(event.target.value === "coupling" ? "coupling" : "qubit")
                    }
                  >
                    <option value="qubit">Qubit</option>
                    <option value="coupling">Coupling</option>
                  </select>
                  <input
                    className="input input-bordered input-xs w-full"
                    value={targetDraftId}
                    onChange={(event) => setTargetDraftId(event.target.value)}
                    placeholder={targetDraftType === "coupling" ? "0-1" : "0"}
                  />
                </div>
                <div className="flex justify-end gap-1">
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs"
                    onClick={clearTargetMetadata}
                    disabled={updateMutation.isPending}
                  >
                    Clear
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary btn-xs"
                    onClick={saveTargetMetadata}
                    disabled={
                      updateMutation.isPending || !targetDraftChipId.trim() || !targetDraftId.trim()
                    }
                  >
                    Save
                  </button>
                </div>
              </div>
            ) : (
              !targetContext && (
                <span className="text-xs text-base-content/45">No linked target</span>
              )
            )}
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
              <CalendarDays className="h-3.5 w-3.5" />
              Cooldown
            </div>
            {canManage ? (
              <div className="space-y-2">
                <select
                  className="select select-bordered select-xs w-full"
                  value={cooldownDraftId}
                  onChange={(event) => setCooldownDraftId(event.target.value)}
                  disabled={!targetDraftChipId || updateMutation.isPending}
                >
                  <option value="">No cooldown</option>
                  {cooldowns.map((cooldown) => (
                    <option key={cooldown.cooldown_id} value={cooldown.cooldown_id}>
                      {cooldown.cooldown_id}
                      {formatCooldownPeriod(cooldown) ? ` · ${formatCooldownPeriod(cooldown)}` : ""}
                    </option>
                  ))}
                </select>
                {selectedCooldown && (
                  <div className="text-xs text-base-content/55">
                    {formatCooldownPeriod(selectedCooldown)}
                  </div>
                )}
                <div className="flex justify-end">
                  <button
                    type="button"
                    className="btn btn-primary btn-xs"
                    onClick={saveCooldownMetadata}
                    disabled={updateMutation.isPending}
                  >
                    Save
                  </button>
                </div>
              </div>
            ) : post.cooldown_id ? (
              <div className="space-y-1">
                <span className="badge badge-sm badge-outline">{post.cooldown_id}</span>
                {currentPostCooldown && (
                  <div className="text-xs text-base-content/55">
                    {formatCooldownPeriod(currentPostCooldown)}
                  </div>
                )}
              </div>
            ) : (
              <span className="text-xs text-base-content/45">No cooldown</span>
            )}
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
              <Tag className="h-3.5 w-3.5" />
              Labels
            </div>
            {canManage ? (
              <ForumLabelPicker
                selectedLabels={post.labels ?? []}
                onToggle={togglePostLabel}
                disabled={updateMutation.isPending}
              />
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {(post.labels ?? []).length > 0 ? (
                  (post.labels ?? []).map((label) => {
                    const labelDef = getForumLabel(label);
                    return (
                      <span key={label} className={`badge badge-sm ${labelDef.badgeClass}`}>
                        {labelDef.label}
                      </span>
                    );
                  })
                ) : (
                  <span className="text-xs text-base-content/45">No labels</span>
                )}
              </div>
            )}
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
              {post.is_closed ? (
                <Lock className="h-3.5 w-3.5" />
              ) : (
                <Unlock className="h-3.5 w-3.5" />
              )}
              Status
            </div>
            {canManage ? (
              post.is_closed ? (
                <button
                  className="btn btn-outline btn-sm w-full justify-start gap-2 rounded-md normal-case"
                  onClick={() => reopenMutation.mutate({ postId }, { onSuccess: invalidateThread })}
                >
                  <Unlock className="h-3.5 w-3.5" />
                  Reopen thread
                </button>
              ) : (
                <button
                  className="btn btn-outline btn-sm w-full justify-start gap-2 rounded-md normal-case"
                  onClick={() => closeMutation.mutate({ postId }, { onSuccess: invalidateThread })}
                >
                  <Lock className="h-3.5 w-3.5" />
                  Close thread
                </button>
              )
            ) : (
              <span className="text-sm text-base-content/70">
                {post.is_closed ? "Closed" : "Open"}
              </span>
            )}
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
              <UserRound className="h-3.5 w-3.5" />
              Author
            </div>
            <div className="flex items-center gap-2">
              <UserAvatar username={post.username} avatarKey={post.avatar_key} size={24} />
              <span className="text-sm font-medium">{post.username}</span>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
