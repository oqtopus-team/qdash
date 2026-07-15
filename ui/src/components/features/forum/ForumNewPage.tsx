"use client";

import { useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CalendarDays, Crosshair, Send, Tag, UserRound } from "lucide-react";

import { useListChips } from "@/client/chip/chip";
import { useListCooldowns } from "@/client/cooldown/cooldown";
import {
  getListForumPostsQueryKey,
  useCreateForumPost,
  useListForumCategories,
} from "@/client/forum/forum";
import { useListProjectMembers } from "@/client/projects/projects";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { useForumAiReply } from "@/hooks/useForumAiReply";
import { useImageUpload } from "@/hooks/useImageUpload";
import { formatDateTimeCompact } from "@/lib/utils/datetime";

import {
  DEFAULT_FORUM_CATEGORIES,
  getForumCategory,
  toForumCategoryDefinition,
} from "./categories";
import { ForumLabelPicker } from "./ForumLabelSelector";
import type { ForumBlockSnapshotGetter } from "./ForumBlockEditor";

const ForumBlockEditor = dynamic(
  () => import("./ForumBlockEditor").then((m) => ({ default: m.ForumBlockEditor })),
  { ssr: false },
);

function normalizeTargetType(value: string | null | undefined): "qubit" | "coupling" | null {
  return value === "qubit" || value === "coupling" ? value : null;
}

function formatCooldownPeriod(
  cooldown: { started_at?: string | null; ended_at?: string | null } | undefined,
): string {
  if (!cooldown?.started_at) return "";
  const start = formatDateTimeCompact(cooldown.started_at);
  const end = cooldown.ended_at ? formatDateTimeCompact(cooldown.ended_at) : "ongoing";
  return `${start} - ${end}`;
}

function parseLabels(value: string | null): string[] {
  return (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 1);
}

export function ForumNewPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { projectId } = useProject();
  const { uploadImage } = useImageUpload("forum");
  const { triggerAiReply } = useForumAiReply();
  const editorSnapshotRef = useRef<ForumBlockSnapshotGetter | null>(null);
  const fromQuery = searchParams.get("from");
  const forumReturnHref = fromQuery ? `/forum?${fromQuery.replace(/^\?/, "")}` : "/forum";

  const initialTargetType = normalizeTargetType(searchParams.get("target_type"));
  const [category, setCategory] = useState(searchParams.get("category") ?? "qubit");
  const [title, setTitle] = useState(searchParams.get("title") ?? "");
  const [content, setContent] = useState(searchParams.get("content") ?? "");
  const [contentBlocks, setContentBlocks] = useState<Record<string, unknown>[]>([]);
  const [selectedLabels, setSelectedLabels] = useState<string[]>(() =>
    parseLabels(searchParams.get("labels")),
  );
  const [targetDraftChipId, setTargetDraftChipId] = useState(searchParams.get("chip_id") ?? "");
  const [targetDraftType, setTargetDraftType] = useState<"qubit" | "coupling">(
    initialTargetType ?? (searchParams.get("category") === "coupling" ? "coupling" : "qubit"),
  );
  const [targetDraftId, setTargetDraftId] = useState(searchParams.get("target_id") ?? "");
  const [cooldownDraftId, setCooldownDraftId] = useState(searchParams.get("cooldown_id") ?? "");
  const [assigneeUsername, setAssigneeUsername] = useState("");

  const { data: categoriesResponse } = useListForumCategories(undefined, {
    query: { staleTime: 60_000 },
  });
  const categories = useMemo(
    () =>
      categoriesResponse?.data.categories.map(toForumCategoryDefinition) ??
      DEFAULT_FORUM_CATEGORIES,
    [categoriesResponse?.data.categories],
  );
  const selectedCategory = getForumCategory(category, categories);
  const CategoryIcon = selectedCategory.icon;

  const { data: chipsResponse } = useListChips({ query: { staleTime: 60_000 } });
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
    { query: { enabled: !!targetDraftChipId, staleTime: 60_000 } },
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

  const { data: membersResponse } = useListProjectMembers(projectId ?? "", {
    query: { enabled: !!projectId, staleTime: 60_000 },
  });
  const members = useMemo(
    () => (membersResponse?.data.members ?? []).filter((member) => member.status === "active"),
    [membersResponse?.data.members],
  );

  const createMutation = useCreateForumPost();

  const toggleLabel = (label: string) => {
    setSelectedLabels((current) => (current.includes(label) ? [] : [label]));
  };

  const clearTargetMetadata = () => {
    setTargetDraftChipId("");
    setTargetDraftType("qubit");
    setTargetDraftId("");
    setCooldownDraftId("");
  };

  const handleCreate = async () => {
    const snapshot = await editorSnapshotRef.current?.();
    const trimmedTitle = title.trim();
    const trimmedContent = (snapshot?.markdown ?? content).trim();
    const nextBlocks = snapshot?.blocks ?? contentBlocks;
    if (!trimmedTitle || !trimmedContent) return;

    const chipId = targetDraftChipId.trim();
    const targetId = targetDraftId.trim();
    const hasTarget = !!chipId && !!targetId;
    const response = await createMutation.mutateAsync({
      data: {
        category,
        title: trimmedTitle,
        content: trimmedContent,
        content_blocks: nextBlocks,
        parent_id: null,
        labels: selectedLabels,
        assignee_username: assigneeUsername || null,
        chip_id: hasTarget ? chipId : null,
        target_type: hasTarget ? targetDraftType : null,
        target_id: hasTarget ? targetId : null,
        cooldown_id: cooldownDraftId || null,
      },
    });
    queryClient.invalidateQueries({ queryKey: getListForumPostsQueryKey() });
    if (/@qdash\b/i.test(trimmedContent)) {
      triggerAiReply(response.data.id, trimmedContent, () => {
        queryClient.invalidateQueries({ queryKey: getListForumPostsQueryKey() });
      });
    }
    const detailHref = fromQuery
      ? `/forum/${response.data.id}?from=${encodeURIComponent(fromQuery)}`
      : `/forum/${response.data.id}`;
    router.push(detailHref);
  };

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex min-w-0 items-start gap-3">
        <button
          className="btn btn-square btn-ghost btn-sm shrink-0"
          onClick={() => router.push(forumReturnHref)}
          title="Back to Forum"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-start gap-2">
            <span className="badge badge-outline mt-1 shrink-0">Draft</span>
            <input
              className="input input-bordered input-sm min-w-0 flex-1 text-xl font-bold"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Thread title"
            />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-base-content/50">
            <span>Opened by {user?.username ?? "you"}</span>
            <span>New forum thread</span>
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0 pb-8">
          <div className="rounded-lg border border-base-300 bg-base-100 p-4">
            <ForumBlockEditor
              legacyMarkdown={content}
              onChange={(blocks, markdown) => {
                setContentBlocks(blocks);
                setContent(markdown);
              }}
              onImageUpload={uploadImage}
              snapshotRef={editorSnapshotRef}
            />
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-xs text-base-content/50">
                Type <kbd className="kbd kbd-xs">/</kbd> for blocks. Use{" "}
                <span className="font-mono">@username</span> to mention members.
              </span>
              <button
                type="button"
                className="btn btn-sm btn-primary gap-2"
                onClick={handleCreate}
                disabled={!title.trim() || !content.trim() || createMutation.isPending}
              >
                {createMutation.isPending ? (
                  <span className="loading loading-spinner loading-xs" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                Post
              </button>
            </div>
          </div>
        </div>

        <aside className="space-y-5 border-t border-base-300 pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
              <CategoryIcon className="h-3.5 w-3.5" />
              Category
            </div>
            <select
              className="select select-bordered select-sm w-full"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              {categories.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
              <Crosshair className="h-3.5 w-3.5" />
              Target
            </div>
            <div className="space-y-2">
              <select
                className="select select-bordered select-xs w-full"
                value={targetDraftChipId}
                onChange={(event) => {
                  setTargetDraftChipId(event.target.value);
                  setCooldownDraftId("");
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
                  onChange={(event) => {
                    const nextType = event.target.value === "coupling" ? "coupling" : "qubit";
                    setTargetDraftType(nextType);
                    if (nextType === "coupling" && category === "qubit") setCategory("coupling");
                    if (nextType === "qubit" && category === "coupling") setCategory("qubit");
                  }}
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
              <div className="flex justify-end">
                <button
                  type="button"
                  className="btn btn-ghost btn-xs"
                  onClick={clearTargetMetadata}
                  disabled={!targetDraftChipId && !targetDraftId && !cooldownDraftId}
                >
                  Clear
                </button>
              </div>
            </div>
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
              <CalendarDays className="h-3.5 w-3.5" />
              Cooldown
            </div>
            <select
              className="select select-bordered select-xs w-full"
              value={cooldownDraftId}
              onChange={(event) => setCooldownDraftId(event.target.value)}
              disabled={!targetDraftChipId}
            >
              <option value="">No cooldown</option>
              {cooldowns.map((cooldown) => (
                <option key={cooldown.cooldown_id} value={cooldown.cooldown_id}>
                  {cooldown.cooldown_id}
                  {formatCooldownPeriod(cooldown) ? ` - ${formatCooldownPeriod(cooldown)}` : ""}
                </option>
              ))}
            </select>
            {selectedCooldown && (
              <div className="text-xs text-base-content/55">
                {formatCooldownPeriod(selectedCooldown)}
              </div>
            )}
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
              <UserRound className="h-3.5 w-3.5" />
              Assignee
            </div>
            <select
              className="select select-bordered select-xs w-full"
              value={assigneeUsername}
              onChange={(event) => setAssigneeUsername(event.target.value)}
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
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
              <Tag className="h-3.5 w-3.5" />
              Labels
            </div>
            <ForumLabelPicker selectedLabels={selectedLabels} onToggle={toggleLabel} />
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
              <UserRound className="h-3.5 w-3.5" />
              Author
            </div>
            <div className="flex items-center gap-2">
              <UserAvatar
                username={user?.username ?? "you"}
                avatarKey={user?.avatar_key}
                size={24}
              />
              <span className="text-sm font-medium">{user?.username ?? "you"}</span>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
