"use client";

import { useRef, useState, type KeyboardEvent } from "react";

import { useQueryClient } from "@tanstack/react-query";
import { Plus, Tag } from "lucide-react";
import { toast } from "sonner";

import {
  getListForumLabelsQueryKey,
  getListForumPostsQueryKey,
  useCreateForumLabel,
} from "@/client/forum/forum";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import { useProject } from "@/contexts/ProjectContext";

import {
  getForumLabel,
  getForumLabelErrorMessage,
  NEUTRAL_FORUM_LABEL_COLOR,
  type ForumLabelDefinition,
} from "./categories";
import { ForumLabelBadge } from "./ForumLabelBadge";

export const MAX_FORUM_POST_LABELS = 10;

type ForumLabelPickerProps = {
  labels: ForumLabelDefinition[];
  selectedLabels: string[];
  onToggle: (label: string) => void;
  disabled?: boolean;
};

/** Filters labels by a case-insensitive match against name, key, or description. */
export function filterForumLabels(
  labels: ForumLabelDefinition[],
  query: string,
): ForumLabelDefinition[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return labels;
  return labels.filter(
    (item) =>
      item.label.toLowerCase().includes(normalized) ||
      item.id.toLowerCase().includes(normalized) ||
      item.description.toLowerCase().includes(normalized),
  );
}

/** Whether a "Create label" option should appear for the query, given the existing labels. */
export function shouldShowCreateForumLabelOption(
  query: string,
  labels: ForumLabelDefinition[],
): boolean {
  const trimmed = query.trim();
  if (!trimmed) return false;
  const normalized = trimmed.toLowerCase();
  return !labels.some(
    (item) => item.label.toLowerCase() === normalized || item.id.toLowerCase() === normalized,
  );
}

/** Counts the selected label keys that count toward the per-post limit, excluding system labels. */
export function countLimitedForumLabels(
  selected: string[],
  labels: ForumLabelDefinition[],
): number {
  return selected.filter((key) => !labels.find((item) => item.id === key)?.isSystem).length;
}

/** Whether the selection has reached the per-post label limit, ignoring system labels. */
export function isForumLabelLimitReached(
  selected: string[],
  labels: ForumLabelDefinition[],
): boolean {
  return countLimitedForumLabels(selected, labels) >= MAX_FORUM_POST_LABELS;
}

/** Action pressing Enter in the label search input should take: toggle the first filtered label, create a new one, or nothing. */
export type ForumLabelEnterAction =
  | { type: "toggle"; labelId: string }
  | { type: "create" }
  | { type: "none" };

/** Decides what pressing Enter in the label search input does, respecting the first filtered label's disabled state. */
export function getForumLabelEnterAction(
  filteredLabels: ForumLabelDefinition[],
  selectedLabels: string[],
  atLimit: boolean,
  showCreateOption: boolean,
): ForumLabelEnterAction {
  const first = filteredLabels[0];
  if (first) {
    const isSelected = selectedLabels.includes(first.id);
    return isSelected || !atLimit || first.isSystem
      ? { type: "toggle", labelId: first.id }
      : { type: "none" };
  }
  return showCreateOption ? { type: "create" } : { type: "none" };
}

/** Focuses the first enabled label or create menu item inside the dropdown content. */
function focusFirstForumLabelItem(container: HTMLElement | null) {
  const item = container?.querySelector<HTMLElement>(
    '[role="menuitemcheckbox"]:not([data-disabled]), [role="menuitem"]:not([data-disabled])',
  );
  item?.focus();
}

/** Dropdown for applying labels to a forum thread, with search and owner-only label creation. */
export function ForumLabelPicker({
  labels,
  selectedLabels,
  onToggle,
  disabled = false,
}: ForumLabelPickerProps) {
  const { isOwner } = useProject();
  const queryClient = useQueryClient();
  const createMutation = useCreateForumLabel();
  const [query, setQuery] = useState("");
  const contentRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const selectedDefinitions = selectedLabels.map((key) => getForumLabel(key, labels));
  const atLimit = isForumLabelLimitReached(selectedLabels, labels);
  const trimmedQuery = query.trim();
  const filteredLabels = filterForumLabels(labels, query);
  const showCreateOption = isOwner && shouldShowCreateForumLabelOption(query, labels);

  const handleCreateLabel = async () => {
    if (!showCreateOption || createMutation.isPending) return;
    try {
      const response = await createMutation.mutateAsync({
        data: { name: trimmedQuery, color: NEUTRAL_FORUM_LABEL_COLOR },
      });
      queryClient.invalidateQueries({ queryKey: getListForumLabelsQueryKey() });
      queryClient.invalidateQueries({ queryKey: getListForumPostsQueryKey() });
      if (!atLimit) onToggle(response.data.key);
      setQuery("");
    } catch (error) {
      toast.error(getForumLabelErrorMessage(error, "Failed to create label"));
    }
  };

  const handleSearchKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      event.stopPropagation();
      focusFirstForumLabelItem(contentRef.current);
      return;
    }
    if (event.key === "Enter") {
      event.stopPropagation();
      const action = getForumLabelEnterAction(
        filteredLabels,
        selectedLabels,
        atLimit,
        showCreateOption,
      );
      if (action.type === "toggle") {
        event.preventDefault();
        onToggle(action.labelId);
      } else if (action.type === "create") {
        event.preventDefault();
        void handleCreateLabel();
      }
      return;
    }
    event.stopPropagation();
  };

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <DropdownMenu
        onOpenChange={(open) => {
          if (open) {
            requestAnimationFrame(() => searchInputRef.current?.focus());
          } else {
            setQuery("");
          }
        }}
      >
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="btn btn-outline btn-sm gap-2 rounded-md normal-case"
            disabled={disabled}
          >
            <Tag className="h-4 w-4" />
            Labels
            {selectedLabels.length > 0 && (
              <span className="badge badge-sm badge-neutral">{selectedLabels.length}</span>
            )}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent ref={contentRef} align="start" className="max-h-80 w-72">
          <DropdownMenuLabel>Apply labels</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <div className="px-1 pb-1.5">
            <input
              ref={searchInputRef}
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={handleSearchKeyDown}
              placeholder="Filter labels"
              aria-label="Filter labels"
              className="input input-bordered input-xs w-full"
            />
          </div>
          {labels.length === 0 ? (
            <div className="px-2.5 py-2 text-xs text-base-content/45">No labels available</div>
          ) : filteredLabels.length === 0 ? (
            <div className="px-2.5 py-2 text-xs text-base-content/45">No labels found</div>
          ) : (
            filteredLabels.map((item) => {
              const selected = selectedLabels.includes(item.id);
              return (
                <DropdownMenuCheckboxItem
                  key={item.id}
                  checked={selected}
                  disabled={!selected && atLimit && !item.isSystem}
                  onCheckedChange={() => onToggle(item.id)}
                  onSelect={(event) => event.preventDefault()}
                >
                  <div className="flex min-w-0 flex-col gap-1 py-0.5">
                    <ForumLabelBadge label={item} />
                    {item.description && (
                      <span className="truncate text-xs text-base-content/50">
                        {item.description}
                      </span>
                    )}
                  </div>
                </DropdownMenuCheckboxItem>
              );
            })
          )}
          {showCreateOption && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                disabled={createMutation.isPending}
                onSelect={(event) => {
                  event.preventDefault();
                  void handleCreateLabel();
                }}
              >
                {createMutation.isPending ? (
                  <span className="loading loading-spinner loading-xs shrink-0" />
                ) : (
                  <Plus className="h-3.5 w-3.5 shrink-0" />
                )}
                <span className="min-w-0 flex-1 truncate">
                  Create new label <span className="font-medium">{`"${trimmedQuery}"`}</span>
                </span>
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      {selectedDefinitions.length > 0 ? (
        <div className="flex min-w-0 flex-wrap gap-1.5">
          {selectedDefinitions.map((item) => (
            <ForumLabelBadge key={item.id} label={item} />
          ))}
        </div>
      ) : (
        <span className="text-xs text-base-content/45">No labels</span>
      )}
    </div>
  );
}
