import {
  BarChart3,
  BookMarked,
  Bot,
  Brain,
  CircleDot,
  ClipboardCheck,
  ClipboardList,
  Code,
  Cpu,
  Database,
  Files,
  House,
  Inbox,
  LayoutDashboard,
  LayoutGrid,
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
  badge?: number;
  visible?: boolean;
};

export type NavSection = {
  label: string;
  items: NavItem[];
};

interface NavigationOptions {
  canEdit: boolean;
  isAdmin: boolean;
  unreadNotifications?: number;
}

export function getNavigationSections({
  canEdit,
  isAdmin,
  unreadNotifications = 0,
}: NavigationOptions): NavSection[] {
  return [
    {
      label: "Overview",
      items: [
        { href: "/home", label: "Home", icon: House },
        { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
        { href: "/metrics", label: "Metrics", icon: LayoutGrid },
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
        { href: "/tasks", label: "Tasks", icon: ListTodo, visible: canEdit },
        { href: "/cryo", label: "Cryo", icon: Snowflake },
        { href: "/import", label: "Calibration DB", icon: Database },
      ],
    },
    {
      label: "Collaborate",
      items: [
        {
          href: "/inbox",
          label: "Inbox",
          icon: Inbox,
          badge: unreadNotifications,
        },
        { href: "/issues", label: "Issues", icon: CircleDot, match: "prefix" },
        {
          href: "/forum",
          label: "Forum",
          icon: MessagesSquare,
          match: "prefix",
        },
        {
          href: "/issue-knowledge",
          label: "Knowledge",
          icon: Brain,
          match: "prefix",
        },
        {
          href: "/ai-reviews",
          label: "AI Reviews",
          icon: ClipboardCheck,
          match: "prefix",
        },
        {
          href: "/task-knowledge",
          label: "Task Knowledge",
          icon: BookMarked,
          match: "prefix",
        },
      ],
    },
    {
      label: "Manage",
      items: [
        {
          href: "/files",
          label: "Files",
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
