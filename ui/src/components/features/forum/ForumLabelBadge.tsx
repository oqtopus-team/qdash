"use client";

import type { ForumLabelDefinition } from "./categories";

/** Picks readable black/white text for a given hex background color (YIQ heuristic). */
export function getReadableTextColor(hex: string): string {
  const normalized = hex.replace("#", "").trim();
  const expanded =
    normalized.length === 3
      ? normalized
          .split("")
          .map((char) => char + char)
          .join("")
      : normalized;
  if (!/^[0-9a-fA-F]{6}$/.test(expanded)) return "#ffffff";
  const r = Number.parseInt(expanded.slice(0, 2), 16);
  const g = Number.parseInt(expanded.slice(2, 4), 16);
  const b = Number.parseInt(expanded.slice(4, 6), 16);
  const yiq = (r * 299 + g * 587 + b * 114) / 1000;
  return yiq >= 128 ? "#111827" : "#ffffff";
}

type ForumLabelBadgeProps = {
  label: ForumLabelDefinition;
  size?: "xs" | "sm";
  className?: string;
};

export function ForumLabelBadge({ label, size = "sm", className = "" }: ForumLabelBadgeProps) {
  return (
    <span
      className={`badge badge-${size} border-transparent font-medium ${className}`}
      style={{ backgroundColor: label.color, color: getReadableTextColor(label.color) }}
      title={label.description || label.label}
    >
      {label.label}
    </span>
  );
}
