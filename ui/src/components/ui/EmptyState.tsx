"use client";

import {
  BarChart3,
  Bot,
  Brain,
  CircleCheck,
  Clock,
  Cpu,
  Hourglass,
  Inbox,
  type LucideIcon,
  MessageSquare,
  Rocket,
  Search,
  Snowflake,
  TriangleAlert,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  brain: Brain,
  chart: BarChart3,
  "chart-bar": BarChart3,
  check: CircleCheck,
  clock: Clock,
  empty: Inbox,
  hourglass: Hourglass,
  "magnifying-glass": Search,
  microchip: Cpu,
  robot: Bot,
  rocket: Rocket,
  snowflake: Snowflake,
  "speech-balloon": MessageSquare,
  warning: TriangleAlert,
};

interface EmptyStateProps {
  /** Title text */
  title?: string;
  /** Description text */
  description?: string;
  /** Icon name; see ICONS. Unknown names fall back to an inbox. */
  emoji?: string;
  /** Custom action button */
  action?: React.ReactNode;
  /** Size variant */
  size?: "sm" | "md" | "lg";
  /** Additional CSS classes */
  className?: string;
}

/**
 * Empty state with a line icon, a title and an optional description and action.
 */
export function EmptyState({
  title = "No data",
  description,
  emoji = "empty",
  action,
  size = "md",
  className = "",
}: EmptyStateProps) {
  const sizeClasses = {
    sm: {
      container: "py-6",
      disc: "h-10 w-10",
      icon: "h-5 w-5",
      title: "text-sm",
      description: "text-xs",
    },
    md: {
      container: "py-10",
      disc: "h-12 w-12",
      icon: "h-6 w-6",
      title: "text-sm",
      description: "text-sm",
    },
    lg: {
      container: "py-16",
      disc: "h-14 w-14",
      icon: "h-7 w-7",
      title: "text-sm",
      description: "text-sm",
    },
  };

  const styles = sizeClasses[size];
  const Icon = ICONS[emoji] ?? Inbox;

  return (
    <div
      className={`flex flex-col items-center justify-center text-center ${styles.container} ${className}`}
    >
      <div
        className={`mb-4 flex items-center justify-center rounded-full bg-base-200 text-base-content/50 ${styles.disc}`}
      >
        <Icon className={styles.icon} aria-hidden="true" />
      </div>
      <h3 className={`font-medium text-base-content/70 ${styles.title}`}>{title}</h3>
      {description && (
        <p className={`mt-1 text-base-content/50 max-w-sm ${styles.description}`}>{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
