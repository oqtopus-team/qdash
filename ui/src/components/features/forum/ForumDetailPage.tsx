"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Lock,
  MessageSquare,
  Pencil,
  Trash2,
  Unlock,
} from "lucide-react";

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
import { useListProjectMembers } from "@/client/projects/projects";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { MarkdownEditor } from "@/components/ui/MarkdownEditor";
import { QdashBotAvatar, UserAvatar } from "@/components/ui/UserAvatar";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { useForumAiReply } from "@/hooks/useForumAiReply";
import { useImageUpload } from "@/hooks/useImageUpload";
import { formatRelativeTime } from "@/lib/utils/datetime";
import type { ForumPostResponse } from "@/schemas";

import { getForumCategory, toForumCategoryDefinition } from "./categories";

const REPLY_PAGE_SIZE = 100;

function isEdited(createdAt: string, updatedAt: string): boolean {
  return (
    Math.abs(new Date(updatedAt).getTime() - new Date(createdAt).getTime()) >
    1000
  );
}

function PostBody({
  post,
  currentUsername,
  onEdit,
  onDelete,
  editing,
  editTitle,
  editContent,
  onTitleChange,
  onContentChange,
  onCancel,
  onSave,
  saving,
  onImageUpload,
}: {
  post: ForumPostResponse;
  currentUsername?: string;
  onEdit: () => void;
  onDelete: () => void;
  editing: boolean;
  editTitle?: string;
  editContent: string;
  onTitleChange?: (value: string) => void;
  onContentChange: (value: string) => void;
  onCancel: () => void;
  onSave: () => void;
  saving: boolean;
  onImageUpload?: (file: File) => Promise<string>;
}) {
  const canEdit = currentUsername === post.username;
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
            <UserAvatar
              username={post.username}
              avatarKey={post.avatar_key}
              size={24}
            />
          )}
          <span
            className={`badge badge-sm ${isAi ? "badge-primary" : "badge-neutral"}`}
          >
            {post.username}
          </span>
          <span className="text-xs text-base-content/40">
            {formatRelativeTime(post.created_at)}
          </span>
          {isEdited(post.created_at, post.updated_at) && (
            <span className="text-xs italic text-base-content/30">
              (edited)
            </span>
          )}
        </div>
        {canEdit && !editing && !isAi && (
          <div className="flex items-center gap-1">
            <button
              className="btn btn-ghost btn-xs p-0 h-auto min-h-0 text-base-content/40 hover:text-primary"
              onClick={onEdit}
              title="Edit"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
            <button
              className="btn btn-ghost btn-xs p-0 h-auto min-h-0 text-base-content/40 hover:text-error"
              onClick={onDelete}
              title="Delete"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>
      {editing ? (
        <div className="space-y-3">
          {onTitleChange && (
            <input
              className="input input-bordered input-sm w-full"
              value={editTitle ?? ""}
              onChange={(event) => onTitleChange(event.target.value)}
              placeholder="Thread title"
            />
          )}
          <MarkdownEditor
            value={editContent}
            onChange={onContentChange}
            onSubmit={onSave}
            rows={4}
            placeholder="Edit post..."
            onImageUpload={onImageUpload}
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
              {saving ? (
                <span className="loading loading-spinner loading-xs" />
              ) : (
                "Save"
              )}
            </button>
          </div>
        </div>
      ) : (
        <MarkdownContent
          content={post.content}
          className="text-sm text-base-content/80"
        />
      )}
    </div>
  );
}

export function ForumDetailPage({ postId }: { postId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { isOwner, projectId } = useProject();
  const { uploadImage } = useImageUpload("forum");
  const currentUsername = user?.username;
  const [replyText, setReplyText] = useState("");
  const [editingRoot, setEditingRoot] = useState(false);
  const [editRootTitle, setEditRootTitle] = useState("");
  const [editRootContent, setEditRootContent] = useState("");
  const [editingReplyId, setEditingReplyId] = useState<string | null>(null);
  const [editReplyContent, setEditReplyContent] = useState("");
  const [replyLimit, setReplyLimit] = useState(REPLY_PAGE_SIZE);

  const { data: postResponse, isLoading: postLoading } = useGetForumPost(
    postId,
    { query: { staleTime: 30_000 } },
  );
  const post = postResponse?.data ?? null;
  const { data: repliesResponse, isLoading: repliesLoading } =
    useGetForumPostReplies(
      postId,
      { skip: 0, limit: replyLimit },
      { query: { enabled: !!post } },
    );
  const replies = repliesResponse?.data ?? [];
  const { data: categoriesResponse } = useListForumCategories(undefined, {
    query: { staleTime: 60_000 },
  });
  const categories = useMemo(
    () =>
      categoriesResponse?.data.categories.map(toForumCategoryDefinition) ?? [],
    [categoriesResponse?.data.categories],
  );

  const { data: membersResponse } = useListProjectMembers(projectId ?? "", {
    query: { enabled: !!projectId },
  });
  const mentionCandidates = useMemo(
    () => [
      { id: "qdash", label: "QDash" },
      {
        id: "project",
        label: "Project",
        secondaryLabel: "Notify all project members",
      },
      ...(membersResponse?.data.members
        ?.filter((member) => member.username !== currentUsername)
        .map((member) => ({
          id: member.username,
          label: member.display_name || member.username,
          secondaryLabel: member.organization ?? undefined,
          avatarKey: member.avatar_key,
        })) ?? []),
    ],
    [currentUsername, membersResponse?.data.members],
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

  const invalidateThread = () => {
    queryClient.invalidateQueries({
      queryKey: getGetForumPostQueryKey(postId),
    });
    queryClient.invalidateQueries({
      queryKey: getGetForumPostRepliesQueryKey(postId),
    });
    queryClient.invalidateQueries({ queryKey: getListForumPostsQueryKey() });
  };

  const handleStartEditRoot = () => {
    if (!post) return;
    setEditRootTitle(post.title ?? "");
    setEditRootContent(post.content);
    setEditingRoot(true);
  };

  const handleSaveRoot = async () => {
    if (!post || !editRootContent.trim()) return;
    await updateMutation.mutateAsync({
      postId: post.id,
      data: {
        title: editRootTitle.trim() || null,
        content: editRootContent.trim(),
      },
    });
    setEditingRoot(false);
    invalidateThread();
  };

  const handleAddReply = async () => {
    if (!post || !replyText.trim()) return;
    const trimmed = replyText.trim();
    await createMutation.mutateAsync({
      data: {
        category: post.category,
        title: null,
        content: trimmed,
        parent_id: post.id,
      },
    });
    setReplyText("");
    invalidateThread();
    if (/@qdash\b/i.test(trimmed)) {
      triggerAiReply(post.id, trimmed, invalidateThread);
    }
  };

  const handleStartEditReply = (reply: ForumPostResponse) => {
    setEditingReplyId(reply.id);
    setEditReplyContent(reply.content);
  };

  const handleSaveReply = async () => {
    if (!editingReplyId || !editReplyContent.trim()) return;
    await updateMutation.mutateAsync({
      postId: editingReplyId,
      data: { title: null, content: editReplyContent.trim() },
    });
    setEditingReplyId(null);
    invalidateThread();
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
  const canManage = isOwner || currentUsername === post.username;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <button
            className="btn btn-square btn-ghost btn-sm shrink-0"
            onClick={() => router.push("/forum")}
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className={`badge badge-sm ${category.badgeClass}`}>
                <CategoryIcon className="h-3 w-3" />
                {category.label}
              </span>
              {post.is_closed && (
                <span className="badge badge-sm badge-ghost">Closed</span>
              )}
            </div>
            {editingRoot ? (
              <input
                className="input input-bordered input-sm w-full"
                value={editRootTitle}
                onChange={(event) => setEditRootTitle(event.target.value)}
              />
            ) : (
              <h1 className="truncate text-xl font-bold">{post.title}</h1>
            )}
          </div>
        </div>
        {canManage &&
          (post.is_closed ? (
            <button
              className="btn btn-ghost btn-sm gap-1"
              onClick={() =>
                reopenMutation.mutate(
                  { postId },
                  { onSuccess: invalidateThread },
                )
              }
            >
              <Unlock className="h-3.5 w-3.5" />
              Reopen
            </button>
          ) : (
            <button
              className="btn btn-ghost btn-sm gap-1"
              onClick={() =>
                closeMutation.mutate(
                  { postId },
                  { onSuccess: invalidateThread },
                )
              }
            >
              <Lock className="h-3.5 w-3.5" />
              Close
            </button>
          ))}
      </div>

      <PostBody
        post={post}
        currentUsername={currentUsername}
        onEdit={handleStartEditRoot}
        onDelete={() => handleDelete(post.id, true)}
        editing={editingRoot}
        editTitle={editRootTitle}
        editContent={editRootContent}
        onTitleChange={setEditRootTitle}
        onContentChange={setEditRootContent}
        onCancel={() => setEditingRoot(false)}
        onSave={handleSaveRoot}
        saving={updateMutation.isPending}
        onImageUpload={uploadImage}
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
                onContentChange={setEditReplyContent}
                onCancel={() => setEditingReplyId(null)}
                onSave={handleSaveReply}
                saving={updateMutation.isPending}
                onImageUpload={uploadImage}
              />
            ))}
            {replies.length >= replyLimit && (
              <div className="flex justify-center py-2">
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() =>
                    setReplyLimit((current) => current + REPLY_PAGE_SIZE)
                  }
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
        {aiError && (
          <div className="px-2 py-1 text-xs text-error">{aiError}</div>
        )}
      </div>

      <div className="ml-4 pb-8 pl-4">
        {post.is_closed ? (
          <div className="rounded-lg border border-base-300 bg-base-200/60 p-3 text-sm text-base-content/60">
            This thread is closed.
          </div>
        ) : (
          <MarkdownEditor
            value={replyText}
            onChange={setReplyText}
            onSubmit={handleAddReply}
            placeholder="Write a reply. Use @username to mention project members."
            rows={3}
            submitLabel="Reply"
            isSubmitting={createMutation.isPending}
            mentionCandidates={mentionCandidates}
            onImageUpload={uploadImage}
          />
        )}
      </div>
    </div>
  );
}
