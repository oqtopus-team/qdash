"use client";

import { Tag } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";

import { getForumLabel, type ForumLabelDefinition } from "./categories";
import { ForumLabelBadge } from "./ForumLabelBadge";

export const MAX_FORUM_POST_LABELS = 10;

type ForumLabelPickerProps = {
  labels: ForumLabelDefinition[];
  selectedLabels: string[];
  onToggle: (label: string) => void;
  disabled?: boolean;
};

export function ForumLabelPicker({
  labels,
  selectedLabels,
  onToggle,
  disabled = false,
}: ForumLabelPickerProps) {
  const selectedDefinitions = selectedLabels.map((key) => getForumLabel(key, labels));
  const atLimit = selectedLabels.length >= MAX_FORUM_POST_LABELS;

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <DropdownMenu>
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
        <DropdownMenuContent align="start" className="max-h-80 w-72">
          <DropdownMenuLabel>Apply labels</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {labels.length === 0 && (
            <div className="px-2.5 py-2 text-xs text-base-content/45">No labels available</div>
          )}
          {labels.map((item) => {
            const selected = selectedLabels.includes(item.id);
            return (
              <DropdownMenuCheckboxItem
                key={item.id}
                checked={selected}
                disabled={!selected && atLimit}
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
          })}
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
