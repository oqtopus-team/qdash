"use client";

import {
  Activity,
  CalendarCheck2,
  CircuitBoard,
  MessageSquare,
  Network,
  Settings2,
  type LucideIcon,
} from "lucide-react";

import type { ForumCategoryResponse } from "@/schemas";

export type ForumLabelDefinition = {
  id: string;
  label: string;
  badgeClass: string;
  buttonClass: string;
};

export const FORUM_LABELS: ForumLabelDefinition[] = [
  {
    id: "discussion",
    label: "Discussion",
    badgeClass: "badge-warning",
    buttonClass: "btn-warning",
  },
  { id: "info", label: "Info", badgeClass: "badge-info", buttonClass: "btn-info" },
  { id: "resolved", label: "Resolved", badgeClass: "badge-success", buttonClass: "btn-success" },
];

const LEGACY_LABEL_ALIASES: Record<string, string> = { mtg: "discussion" };

export function getForumLabel(label: string): ForumLabelDefinition {
  const resolvedId = LEGACY_LABEL_ALIASES[label] ?? label;
  const definition = FORUM_LABELS.find((item) => item.id === resolvedId);
  return definition
    ? { ...definition, id: label }
    : {
        id: label,
        label,
        badgeClass: "badge-ghost",
        buttonClass: "btn-ghost",
      };
}

export function forumMarkerClass(label: string | undefined): string {
  if (label === "discussion") return "bg-warning text-warning-content";
  if (label === "resolved") return "bg-success text-success-content";
  return "bg-info text-info-content";
}

export function formatForumPostNumber(number: number | null | undefined): string | null {
  return typeof number === "number" && Number.isFinite(number) ? `#${number}` : null;
}

export function formatForumPostTitle(
  title: string | null | undefined,
  number: number | null | undefined,
): string {
  const displayNumber = formatForumPostNumber(number);
  const displayTitle = title || "Untitled topic";
  return displayNumber ? `${displayNumber} · ${displayTitle}` : displayTitle;
}

export type ForumCategoryDefinition = {
  id: string;
  label: string;
  shortLabel: string;
  description: string;
  badgeClass: string;
  icon: LucideIcon;
};

export const DEFAULT_FORUM_CATEGORIES: ForumCategoryDefinition[] = [
  {
    id: "qubit",
    label: "Qubit Health",
    shortLabel: "Qubit",
    description: "T1, T2, readout fidelity",
    badgeClass: "badge-success",
    icon: Activity,
  },
  {
    id: "coupling",
    label: "Coupling & CR",
    shortLabel: "Coupling",
    description: "Cross-resonance and pair behavior",
    badgeClass: "badge-info",
    icon: Network,
  },
  {
    id: "control",
    label: "Control Stack",
    shortLabel: "Control",
    description: "Control devices, wiring, IMPA",
    badgeClass: "badge-warning",
    icon: CircuitBoard,
  },
  {
    id: "system",
    label: "System & Policy",
    shortLabel: "System",
    description: "Fridge, chip, software, calibration rules",
    badgeClass: "badge-primary",
    icon: Settings2,
  },
  {
    id: "other",
    label: "Other",
    shortLabel: "Other",
    description: "General project discussions",
    badgeClass: "badge-secondary",
    icon: MessageSquare,
  },
];

const ICONS: Record<string, LucideIcon> = {
  activity: Activity,
  "calendar-check": CalendarCheck2,
  "circuit-board": CircuitBoard,
  "message-square": MessageSquare,
  network: Network,
  settings: Settings2,
};

function colorToBadgeClass(color: string) {
  return `badge-${color}`;
}

export function toForumCategoryDefinition(
  category: ForumCategoryResponse,
): ForumCategoryDefinition {
  return {
    id: category.key,
    label: category.name,
    shortLabel: category.name,
    description: category.description || "Project discussion",
    badgeClass: colorToBadgeClass(category.color ?? "neutral"),
    icon: ICONS[category.icon ?? "message-square"] ?? MessageSquare,
  };
}

export function getForumCategory(
  category: string,
  categories: ForumCategoryDefinition[] = DEFAULT_FORUM_CATEGORIES,
) {
  return (
    categories.find((item) => item.id === category) ??
    DEFAULT_FORUM_CATEGORIES.find((item) => item.id === category) ?? {
      id: category,
      label: category,
      shortLabel: category,
      description: "Project discussion",
      badgeClass: "badge-ghost",
      icon: MessageSquare,
    }
  );
}
