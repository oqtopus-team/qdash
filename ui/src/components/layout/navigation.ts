import {
  BarChart3,
  BookMarked,
  Bot,
  ClipboardCheck,
  ClipboardList,
  Code,
  Cpu,
  Database,
  Files,
  Gauge,
  House,
  LayoutDashboard,
  ListTodo,
  MessagesSquare,
  Settings,
  ShieldCheck,
  Snowflake,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  title?: string;
  icon: LucideIcon;
  match?: "exact" | "prefix";
  visible?: boolean;
};

export type NavSection = {
  label: string;
  items: NavItem[];
};

interface NavigationOptions {
  canEdit: boolean;
  isAdmin: boolean;
}

export function getNavigationSections({ canEdit, isAdmin }: NavigationOptions): NavSection[] {
  return [
    {
      label: "Overview",
      items: [
        { href: "/home", label: "Home", icon: House },
        { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
        { href: "/metrics", label: "Metrics", icon: Gauge },
        { href: "/chip", label: "Chip", icon: Cpu },
        { href: "/analysis", label: "Analysis", icon: BarChart3 },
        { href: "/chat", label: "AI Chat", icon: Bot },
      ],
    },
    {
      label: "Operate",
      items: [
        {
          href: "/workflow",
          label: "Workflow",
          icon: Code,
          match: "prefix",
          visible: canEdit,
        },
        { href: "/execution", label: "Execution", icon: Zap },
        {
          href: "/task-results",
          label: "Task Results",
          icon: ClipboardList,
          match: "prefix",
        },
        {
          href: "/evaluations",
          label: "AI Evaluations",
          icon: ClipboardCheck,
          match: "prefix",
        },
        { href: "/tasks", label: "Tasks", icon: ListTodo, visible: canEdit },
        { href: "/cryo", label: "Cryo", icon: Snowflake },
        { href: "/import", label: "Calibration DB", icon: Database },
      ],
    },
    {
      label: "Collaborate",
      items: [
        {
          href: "/forum",
          label: "Forum",
          icon: MessagesSquare,
          match: "prefix",
        },
        {
          href: "/knowledge",
          label: "Knowledge",
          icon: BookMarked,
          match: "prefix",
        },
      ],
    },
    {
      label: "Manage",
      items: [
        {
          href: "/config",
          label: "Config",
          icon: Files,
          match: "prefix",
          visible: canEdit,
        },
        { href: "/settings", label: "Settings", icon: Settings },
        { href: "/admin", label: "Admin", icon: ShieldCheck, visible: isAdmin },
      ],
    },
  ];
}

/**
 * Destinations shown as tabs in the mobile tab bar, in display order. Each tab
 * is active on its own route and on every route nested under one of its bases;
 * `/executions/{id}` resolves to an execution page, so it belongs to Execution.
 * Every other destination stays in the header menu.
 */
const MOBILE_TAB_BASES: ReadonlyArray<{ href: string; bases: readonly string[] }> = [
  { href: "/dashboard", bases: ["/dashboard"] },
  { href: "/workflow", bases: ["/workflow"] },
  { href: "/execution", bases: ["/execution", "/executions"] },
  { href: "/chat", bases: ["/chat"] },
];

export type MobileTab = {
  item: NavItem;
  bases: readonly string[];
};

/** True when `pathname` is `base` itself or a route nested under it. */
export function isPathWithin(pathname: string, base: string): boolean {
  return pathname === base || pathname.startsWith(`${base}/`);
}

/**
 * Resolves the mobile tabs from the shared sections, so a tab carries the same
 * label, icon, and visibility as its sidebar row; a hidden row hides its tab.
 */
export function getMobileTabs(sections: NavSection[]): MobileTab[] {
  const items = new Map(sections.flatMap((section) => section.items).map((i) => [i.href, i]));
  return MOBILE_TAB_BASES.flatMap(({ href, bases }) => {
    const item = items.get(href);
    return item && item.visible !== false ? [{ item, bases }] : [];
  });
}

export function isMobileTabActive(tab: MobileTab, pathname: string): boolean {
  return tab.bases.some((base) => isPathWithin(pathname, base));
}

/** The sections without the destinations the mobile tab bar already shows. */
export function withoutMobileTabs(sections: NavSection[]): NavSection[] {
  const tabHrefs = new Set(MOBILE_TAB_BASES.map((tab) => tab.href));
  return sections.map((section) => ({
    ...section,
    items: section.items.filter((item) => !tabHrefs.has(item.href)),
  }));
}
