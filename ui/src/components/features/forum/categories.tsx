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

export type ForumCategoryId = string;

export type ForumCategoryDefinition = {
  id: ForumCategoryId;
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
  category: ForumCategoryId,
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
