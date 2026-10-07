"use client";

import {
  Activity,
  CalendarCheck2,
  CheckCircle2,
  CircuitBoard,
  HelpCircle,
  MessageSquare,
  Network,
  Search,
  Tag,
  Settings2,
  type LucideIcon,
} from "lucide-react";

import type { ForumCategoryResponse, ForumLabelResponse } from "@/schemas";

/** Neutral fallback color for labels that no longer exist in the project. */
export const NEUTRAL_FORUM_LABEL_COLOR = "#6b7280";

export type ForumLabelDefinition = {
  id: string;
  label: string;
  description: string;
  color: string;
  isSystem: boolean;
};

export function toForumLabelDefinition(label: ForumLabelResponse): ForumLabelDefinition {
  return {
    id: label.key,
    label: label.name,
    description: label.description ?? "",
    color: label.color,
    isSystem: label.is_system ?? false,
  };
}

export function getForumLabel(
  key: string,
  labels: ForumLabelDefinition[] = [],
): ForumLabelDefinition {
  return (
    labels.find((item) => item.id === key) ?? {
      id: key,
      label: key,
      description: "",
      color: NEUTRAL_FORUM_LABEL_COLOR,
      isSystem: false,
    }
  );
}

export type ForumStatusDefinition = {
  id: string;
  label: string;
  badgeClass: string;
  icon: LucideIcon;
};

export const FORUM_STATUSES: ForumStatusDefinition[] = [
  { id: "open", label: "Open", badgeClass: "badge-info", icon: MessageSquare },
  { id: "investigating", label: "Investigating", badgeClass: "badge-warning", icon: Search },
  { id: "identified", label: "Identified", badgeClass: "badge-secondary", icon: Tag },
  { id: "resolved", label: "Resolved", badgeClass: "badge-success", icon: CheckCircle2 },
];

export function getForumStatus(status: string | null | undefined): ForumStatusDefinition {
  return (
    FORUM_STATUSES.find((item) => item.id === status) ?? {
      id: status ?? "open",
      label: status ?? "Open",
      badgeClass: "badge-ghost",
      icon: HelpCircle,
    }
  );
}

export function isForumTerminalStatus(status: string | null | undefined): boolean {
  return status === "resolved";
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
