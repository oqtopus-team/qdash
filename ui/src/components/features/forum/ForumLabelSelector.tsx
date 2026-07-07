"use client";

import { Check, Tag } from "lucide-react";

import { FORUM_LABELS, getForumLabel } from "./categories";

type ForumLabelSelectorProps = {
  selectedLabels: string[];
  onToggle: (label: string) => void;
  size?: "xs" | "sm";
  disabled?: boolean;
};

export function ForumLabelSelector({
  selectedLabels,
  onToggle,
  size = "xs",
  disabled = false,
}: ForumLabelSelectorProps) {
  const sizeClass = size === "sm" ? "btn-sm h-8 min-h-8" : "btn-xs h-7 min-h-7";

  return (
    <div className="flex flex-wrap gap-1.5">
      {FORUM_LABELS.map((item) => {
        const selected = selectedLabels.includes(item.id);
        return (
          <button
            key={item.id}
            type="button"
            aria-pressed={selected}
            disabled={disabled}
            className={`btn ${sizeClass} rounded-md border px-2 font-medium normal-case ${
              selected ? item.buttonClass : "btn-ghost border-base-300 bg-base-100"
            }`}
            onClick={() => onToggle(item.id)}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

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
      <div className="dropdown dropdown-bottom">
        <button
          type="button"
          tabIndex={0}
          className="btn btn-outline btn-sm gap-2 rounded-md normal-case"
          disabled={disabled}
        >
          <Tag className="h-4 w-4" />
          Labels
          {selectedLabels.length > 0 && (
            <span className="badge badge-sm badge-neutral">{selectedLabels.length}</span>
          )}
        </button>
        <div
          tabIndex={0}
          className="dropdown-content z-[20] mt-2 w-64 rounded-lg border border-base-300 bg-base-100 p-2 shadow-xl"
        >
          <div className="border-b border-base-300 px-2 pb-2 text-xs font-semibold text-base-content/70">
            Apply labels
          </div>
          <div className="mt-1 max-h-64 overflow-auto">
            {FORUM_LABELS.map((item) => {
              const selected = selectedLabels.includes(item.id);
              return (
                <button
                  key={item.id}
                  type="button"
                  className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-base-200"
                  onClick={() => onToggle(item.id)}
                >
                  <span className="flex h-4 w-4 items-center justify-center">
                    {selected && <Check className="h-4 w-4" />}
                  </span>
                  <span className={`badge badge-sm ${item.badgeClass}`}>{item.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
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
