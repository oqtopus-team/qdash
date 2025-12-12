"use client";

import { FluentEmoji } from "./FluentEmoji";

interface EmptyStateProps {
  /** Title text */
  title?: string;
  /** Description text */
  description?: string;
  /** Emoji name from FluentEmoji */
  emoji?: string;
  /** Custom action button */
  action?: React.ReactNode;
  /** Size variant */
  size?: "sm" | "md" | "lg";
  /** Additional CSS classes */
  className?: string;
}

/**
 * Empty state component with FluentEmoji illustration
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
      emoji: 48,
      title: "text-sm",
      description: "text-xs",
    },
    md: {
      container: "py-10",
      emoji: 64,
      title: "text-base",
      description: "text-sm",
    },
    lg: {
      container: "py-16",
      emoji: 80,
      title: "text-lg",
      description: "text-base",
    },
  };

  const styles = sizeClasses[size];

  return (
    <div
      className={`flex flex-col items-center justify-center text-center ${styles.container} ${className}`}
    >
      <div className="mb-4 opacity-80">
        <FluentEmoji name={emoji} size={styles.emoji} />
      </div>
      <h3 className={`font-medium text-base-content/70 ${styles.title}`}>
        {title}
      </h3>
      {description && (
        <p
          className={`mt-1 text-base-content/50 max-w-sm ${styles.description}`}
        >
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/**
 * Pre-configured empty states for common scenarios
 */
export const EmptyStates = {
  noData: (props?: Partial<EmptyStateProps>) => (
    <EmptyState
      title="No data available"
      description="There's nothing to show here yet."
      emoji="empty"
      {...props}
    />
  ),
  noResults: (props?: Partial<EmptyStateProps>) => (
    <EmptyState
      title="No results found"
      description="Try adjusting your search or filters."
      emoji="magnifying-glass"
      {...props}
    />
  ),
  noTasks: (props?: Partial<EmptyStateProps>) => (
    <EmptyState
      title="No tasks"
      description="Create a new task to get started."
      emoji="rocket"
      {...props}
    />
  ),
  error: (props?: Partial<EmptyStateProps>) => (
    <EmptyState
      title="Something went wrong"
      description="Please try again later."
      emoji="warning"
      {...props}
    />
  ),
  loading: (props?: Partial<EmptyStateProps>) => (
    <EmptyState
      title="Loading..."
      description="Please wait while we fetch the data."
      emoji="hourglass"
      {...props}
    />
  ),
};
