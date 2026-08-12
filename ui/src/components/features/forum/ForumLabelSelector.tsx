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

import { FORUM_LABELS, getForumLabel } from "./categories";

type ForumLabelPickerProps = {
  selectedLabels: string[];
  onToggle: (label: string) => void;
  disabled?: boolean;
};

export function ForumLabelPicker({
  selectedLabels,
  onToggle,
  disabled = false,
}: ForumLabelPickerProps) {
  const selectedDefinitions = selectedLabels.map(getForumLabel);

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
        <DropdownMenuContent align="start" className="max-h-72 w-64">
          <DropdownMenuLabel>Apply labels</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {FORUM_LABELS.map((item) => {
            const selected = selectedLabels.includes(item.id);
            return (
              <DropdownMenuCheckboxItem
                key={item.id}
                checked={selected}
                onCheckedChange={() => onToggle(item.id)}
                onSelect={(event) => event.preventDefault()}
              >
                <span className={`badge badge-sm ${item.badgeClass}`}>{item.label}</span>
              </DropdownMenuCheckboxItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
      {selectedDefinitions.length > 0 ? (
        <div className="flex min-w-0 flex-wrap gap-1.5">
          {selectedDefinitions.map((item) => (
            <span key={item.id} className={`badge badge-sm ${item.badgeClass}`}>
              {item.label}
            </span>
          ))}
        </div>
      ) : (
        <span className="text-xs text-base-content/45">No labels</span>
      )}
    </div>
  );
}
