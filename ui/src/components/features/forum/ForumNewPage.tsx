"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CalendarDays,
  ClipboardList,
  Crosshair,
  Send,
  Tag,
  UserRound,
} from "lucide-react";

import { useListChips } from "@/client/chip/chip";
import { useListCooldowns } from "@/client/cooldown/cooldown";
import {
  getListForumPostsQueryKey,
  useCreateForumPost,
  useListForumCategories,
} from "@/client/forum/forum";
import { useListProjectMembers } from "@/client/projects/projects";
import { SelectedLabel } from "@/components/ui/SelectedLabel";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { useForumAiReply } from "@/hooks/useForumAiReply";
import { useForumLabels } from "@/hooks/useForumLabels";
import { useImageUpload } from "@/hooks/useImageUpload";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTimeCompact } from "@/lib/utils/datetime";

import {
  DEFAULT_FORUM_CATEGORIES,
  getForumCategory,
  toForumCategoryDefinition,
} from "./categories";
import { ForumLabelPicker } from "./ForumLabelSelector";
import type { ForumBlockSnapshotGetter, ForumMentionCandidate } from "./ForumBlockEditor";

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

/** Splits comma-separated label params into a deduplicated list of trimmed keys. */
export function parseLabels(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const raw of values) {
    for (const item of raw.split(",")) {
      const trimmed = item.trim();
      if (!trimmed || seen.has(trimmed)) continue;
      seen.add(trimmed);
      result.push(trimmed);
    }
  }
  return result;
}

/** Zod schema for the new thread form; limits mirror the backend ForumPostCreate. */
const newThreadSchema = z.object({
  category: z
    .string()
    .trim()
    .min(1, "Category is required")
    .regex(
      /^[a-z0-9][a-z0-9_-]{0,63}$/,
      "Category must be lowercase letters, numbers, hyphens or underscores (64 characters max)",
    ),
  title: z
    .string()
    .trim()
    .min(1, "Title is required")
    .max(200, "Title must be 200 characters or fewer"),
  content: z
    .string()
    .trim()
    .min(1, "Content is required")
    .max(8000, "Content must be 8000 characters or fewer"),
  labels: z.array(z.string()),
  assigneeUsername: z.string().trim().max(64, "Assignee must be 64 characters or fewer"),
  chipId: z.string().trim().max(128, "Chip ID must be 128 characters or fewer"),
  targetType: z.enum(["qubit", "coupling"]),
  targetId: z.string().trim().max(128, "Target ID must be 128 characters or fewer"),
  cooldownId: z.string().trim().max(128, "Cooldown ID must be 128 characters or fewer"),
});

export type NewThreadFormValues = z.infer<typeof newThreadSchema>;

/** Page for composing a new forum thread. */
export function ForumNewPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { projectId } = useProject();
  const { uploadImage } = useImageUpload("forum");
  const { triggerAiReply } = useForumAiReply();
  const editorSnapshotRef = useRef<ForumBlockSnapshotGetter | null>(null);
  const submitLockRef = useRef(false);
  const createdRef = useRef(false);
  const fromQuery = searchParams.get("from");
  const forumReturnHref = fromQuery ? `/forum?${fromQuery.replace(/^\?/, "")}` : "/forum";

  const initialTargetType = normalizeTargetType(searchParams.get("target_type"));
  const contentBlocksRef = useRef<Record<string, unknown>[]>([]);
  const [serverError, setServerError] = useState<string | null>(null);
  // The task result this thread is about, when opened from a result page.
  const linkedTaskId = searchParams.get("task_id")?.trim() || null;

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    getValues,
    formState: { errors, isSubmitted, isSubmitting },
  } = useForm<NewThreadFormValues>({
    resolver: zodResolver(newThreadSchema),
    defaultValues: {
      category: searchParams.get("category") ?? "qubit",
      title: searchParams.get("title") ?? "",
      content: searchParams.get("content") ?? "",
      labels: parseLabels(searchParams.getAll("labels")),
      assigneeUsername: "",
      chipId: searchParams.get("chip_id") ?? "",
      targetType:
        initialTargetType ?? (searchParams.get("category") === "coupling" ? "coupling" : "qubit"),
      targetId: searchParams.get("target_id") ?? "",
      cooldownId: searchParams.get("cooldown_id") ?? "",
    },
  });
  const category = watch("category");
  const content = watch("content");
  const selectedLabels = watch("labels");
  const assigneeUsername = watch("assigneeUsername");
  const targetDraftChipId = watch("chipId");
  const targetDraftType = watch("targetType");
  const targetDraftId = watch("targetId");
  const cooldownDraftId = watch("cooldownId");

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
  const mentionCandidates: ForumMentionCandidate[] = useMemo(
    () => [
      { id: "qdash", label: "QDash" },
      { id: "project", label: "Project", secondaryLabel: "Notify all project members" },
      ...members
        .filter((member) => member.username !== user?.username)
        .map((member) => ({
          id: member.username,
          label: member.display_name || member.username,
          secondaryLabel: member.organization ?? undefined,
        })),
    ],
    [members, user?.username],
  );

  const createMutation = useCreateForumPost();
  const { labels } = useForumLabels();

  /** Toggles a label in the new-thread selection. */
  const toggleLabel = (label: string) => {
    const current = getValues("labels");
    const next = current.includes(label)
      ? current.filter((item) => item !== label)
      : [...current, label];
    setValue("labels", next);
  };

  /** Resets the target chip, type, id and cooldown to their defaults. */
  const clearTargetMetadata = () => {
    setValue("chipId", "", { shouldValidate: isSubmitted });
    setValue("targetType", "qubit", { shouldValidate: isSubmitted });
    setValue("targetId", "", { shouldValidate: isSubmitted });
    setValue("cooldownId", "", { shouldValidate: isSubmitted });
  };

  /** Creates the thread and surfaces API failures as a server error. */
  const submit = async (values: NewThreadFormValues) => {
    setServerError(null);
    const hasTarget = !!values.chipId && !!values.targetId;
    try {
      const response = await createMutation.mutateAsync({
        data: {
          category: values.category,
          title: values.title,
          content: values.content,
          content_blocks: contentBlocksRef.current,
          parent_id: null,
          labels: values.labels,
          assignee_username: values.assigneeUsername || null,
          chip_id: hasTarget ? values.chipId : null,
          target_type: hasTarget ? values.targetType : null,
          target_id: hasTarget ? values.targetId : null,
          cooldown_id: values.cooldownId || null,
          task_id: linkedTaskId,
        },
      });
      createdRef.current = true;
      queryClient.invalidateQueries({ queryKey: getListForumPostsQueryKey() });
      if (/@qdash\b/i.test(values.content)) {
        triggerAiReply(response.data.id, values.content, () => {
          queryClient.invalidateQueries({ queryKey: getListForumPostsQueryKey() });
        });
      }
      const detailHref = fromQuery
        ? `/forum/${response.data.id}?from=${encodeURIComponent(fromQuery)}`
        : `/forum/${response.data.id}`;
      router.push(detailHref);
    } catch (err) {
      setServerError(getApiErrorMessage(err, "Failed to create thread"));
    }
  };

  /** Prevents Enter in a single-line input from implicitly submitting the form. */
  const handleFormKeyDown = (event: React.KeyboardEvent<HTMLFormElement>) => {
    if (
      event.key === "Enter" &&
      event.target instanceof HTMLInputElement &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
    }
  };

  /** Takes the editor snapshot, syncs it into the form, then validates and submits. */
  const handleCreate = async (event?: React.BaseSyntheticEvent) => {
    event?.preventDefault();
    if (submitLockRef.current) return;
    submitLockRef.current = true;
    try {
      const snapshot = await editorSnapshotRef.current?.();
      if (snapshot) {
        contentBlocksRef.current = snapshot.blocks;
        setValue("content", snapshot.markdown);
      }
      await handleSubmit(submit)(event);
    } finally {
      // Keep the lock after creation until navigation unmounts the page.
      if (!createdRef.current) submitLockRef.current = false;
    }
  };

  const chipField = register("chipId");
  const titleField = register("title");
  /** Returns the error element id for aria-describedby when the field is invalid. */
  const descriptionIds = (id: string, invalid: boolean) => (invalid ? `${id}-error` : undefined);

  return (
    <form
      className="mx-auto max-w-6xl"
      onSubmit={handleCreate}
      onKeyDown={handleFormKeyDown}
      noValidate
    >
      <div className="mb-6 flex min-w-0 items-start gap-3">
        <button
          type="button"
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
              id="forum-new-title"
              className={`input input-bordered input-sm min-w-0 flex-1 text-xl font-bold${errors.title ? " input-error" : ""}`}
              {...titleField}
              aria-label="Thread title"
              aria-invalid={Boolean(errors.title)}
              aria-describedby={descriptionIds("forum-new-title", Boolean(errors.title))}
              placeholder="Thread title"
            />
          </div>
          {errors.title && (
            <p id="forum-new-title-error" className="mt-1 text-xs text-error">
              {errors.title.message}
            </p>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-base-content/50">
            <span>Opened by {user?.username ?? "you"}</span>
            <span>New forum thread</span>
            {linkedTaskId && (
              <Link
                href={`/task-results/${encodeURIComponent(linkedTaskId)}`}
                className="badge badge-outline gap-1"
                title={linkedTaskId}
              >
                <ClipboardList className="h-3 w-3" />
                about task result {linkedTaskId.slice(0, 8)}
              </Link>
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0 pb-8">
          <div
            role="group"
            aria-label="Content"
            aria-invalid={Boolean(errors.content)}
            aria-describedby={errors.content ? "forum-new-content-error" : undefined}
            className="rounded-lg border border-base-300 bg-base-100 p-4"
          >
            <ForumBlockEditor
              legacyMarkdown={content}
              onChange={(blocks, markdown) => {
                contentBlocksRef.current = blocks;
                setValue("content", markdown, { shouldValidate: isSubmitted });
              }}
              onImageUpload={uploadImage}
              snapshotRef={editorSnapshotRef}
              mentionCandidates={mentionCandidates}
            />
            {errors.content && (
              <p id="forum-new-content-error" role="alert" className="mt-2 text-xs text-error">
                {errors.content.message}
              </p>
            )}
            {serverError && (
              <div role="alert" className="alert alert-error mt-2 py-2 text-sm">
                {serverError}
              </div>
            )}
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-xs text-base-content/50">
                Type <kbd className="kbd kbd-xs">/</kbd> for blocks. Use{" "}
                <span className="font-mono">@username</span> to mention members.
              </span>
              <button
                type="submit"
                className="btn btn-sm btn-primary gap-2"
                disabled={isSubmitting || createMutation.isPending}
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
            <label
              htmlFor="forum-new-category"
              className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50"
            >
              <CategoryIcon className="h-3.5 w-3.5" />
              Category
            </label>
            <select
              id="forum-new-category"
              className={`select select-bordered select-sm w-full${errors.category ? " select-error" : ""}`}
              value={category}
              onChange={(event) =>
                setValue("category", event.target.value, { shouldValidate: isSubmitted })
              }
              aria-invalid={Boolean(errors.category)}
              aria-describedby={descriptionIds("forum-new-category", Boolean(errors.category))}
            >
              <SelectedLabel />
              {categories.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
            {errors.category && (
              <p id="forum-new-category-error" className="text-xs text-error">
                {errors.category.message}
              </p>
            )}
          </section>

          <section className="space-y-2">
            <label
              htmlFor="forum-new-chip"
              className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50"
            >
              <Crosshair className="h-3.5 w-3.5" />
              Target
            </label>
            <div className="space-y-2">
              <select
                id="forum-new-chip"
                className={`select select-bordered select-xs w-full${errors.chipId ? " select-error" : ""}`}
                name={chipField.name}
                value={targetDraftChipId}
                onChange={(event) => {
                  setValue("chipId", event.target.value, { shouldValidate: isSubmitted });
                  setValue("cooldownId", "", { shouldValidate: isSubmitted });
                }}
                aria-invalid={Boolean(errors.chipId)}
                aria-describedby={descriptionIds("forum-new-chip", Boolean(errors.chipId))}
              >
                <SelectedLabel />
                <option value="">Select chip</option>
                {chips.map((chip) => (
                  <option key={chip.chip_id} value={chip.chip_id}>
                    {chip.chip_id}
                  </option>
                ))}
              </select>
              <div className="grid grid-cols-[96px_1fr] gap-2">
                <select
                  aria-label="Target type"
                  className="select select-bordered select-xs w-full"
                  value={targetDraftType}
                  onChange={(event) => {
                    const nextType = event.target.value === "coupling" ? "coupling" : "qubit";
                    setValue("targetType", nextType, { shouldValidate: isSubmitted });
                    if (nextType === "coupling" && category === "qubit") {
                      setValue("category", "coupling", { shouldValidate: isSubmitted });
                    }
                    if (nextType === "qubit" && category === "coupling") {
                      setValue("category", "qubit", { shouldValidate: isSubmitted });
                    }
                  }}
                >
                  <option value="qubit">Qubit</option>
                  <option value="coupling">Coupling</option>
                </select>
                <input
                  id="forum-new-target-id"
                  aria-label="Target ID"
                  className={`input input-bordered input-xs w-full${errors.targetId ? " input-error" : ""}`}
                  {...register("targetId")}
                  aria-invalid={Boolean(errors.targetId)}
                  aria-describedby={descriptionIds("forum-new-target-id", Boolean(errors.targetId))}
                  placeholder={targetDraftType === "coupling" ? "0-1" : "0"}
                />
              </div>
              {errors.chipId && (
                <p id="forum-new-chip-error" className="text-xs text-error">
                  {errors.chipId.message}
                </p>
              )}
              {errors.targetId && (
                <p id="forum-new-target-id-error" className="text-xs text-error">
                  {errors.targetId.message}
                </p>
              )}
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
            <label
              htmlFor="forum-new-cooldown"
              className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50"
            >
              <CalendarDays className="h-3.5 w-3.5" />
              Cooldown
            </label>
            <select
              id="forum-new-cooldown"
              className={`select select-bordered select-xs w-full${errors.cooldownId ? " select-error" : ""}`}
              value={cooldownDraftId}
              onChange={(event) =>
                setValue("cooldownId", event.target.value, { shouldValidate: isSubmitted })
              }
              aria-invalid={Boolean(errors.cooldownId)}
              aria-describedby={descriptionIds("forum-new-cooldown", Boolean(errors.cooldownId))}
              disabled={!targetDraftChipId}
            >
              <SelectedLabel />
              <option value="">No cooldown</option>
              {cooldowns.map((cooldown) => (
                <option key={cooldown.cooldown_id} value={cooldown.cooldown_id}>
                  {cooldown.cooldown_id}
                  {formatCooldownPeriod(cooldown) ? ` - ${formatCooldownPeriod(cooldown)}` : ""}
                </option>
              ))}
            </select>
            {errors.cooldownId && (
              <p id="forum-new-cooldown-error" className="text-xs text-error">
                {errors.cooldownId.message}
              </p>
            )}
            {selectedCooldown && (
              <div className="text-xs text-base-content/55">
                {formatCooldownPeriod(selectedCooldown)}
              </div>
            )}
          </section>

          <section className="space-y-2">
            <label
              htmlFor="forum-new-assignee"
              className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50"
            >
              <UserRound className="h-3.5 w-3.5" />
              Assignee
            </label>
            <select
              id="forum-new-assignee"
              className={`select select-bordered select-xs w-full${errors.assigneeUsername ? " select-error" : ""}`}
              value={assigneeUsername}
              onChange={(event) =>
                setValue("assigneeUsername", event.target.value, { shouldValidate: isSubmitted })
              }
              aria-invalid={Boolean(errors.assigneeUsername)}
              aria-describedby={descriptionIds(
                "forum-new-assignee",
                Boolean(errors.assigneeUsername),
              )}
            >
              <SelectedLabel />
              <option value="">Unassigned</option>
              {members.map((member) => (
                <option key={member.username} value={member.username}>
                  {member.display_name
                    ? `${member.display_name} (@${member.username})`
                    : member.username}
                </option>
              ))}
            </select>
            {errors.assigneeUsername && (
              <p id="forum-new-assignee-error" className="text-xs text-error">
                {errors.assigneeUsername.message}
              </p>
            )}
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase text-base-content/50">
              <Tag className="h-3.5 w-3.5" />
              Labels
            </div>
            <ForumLabelPicker
              labels={labels}
              selectedLabels={selectedLabels}
              onToggle={toggleLabel}
              disabled={isSubmitting || createMutation.isPending}
            />
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
    </form>
  );
}
