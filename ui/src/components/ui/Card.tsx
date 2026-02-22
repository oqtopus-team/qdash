import React from "react";

type CardVariant = "default" | "compact" | "elevated";
type CardPadding = "none" | "sm" | "md" | "lg";

interface CardProps {
  children: React.ReactNode;
  /** Card style variant */
  variant?: CardVariant;
  /** Padding size */
  padding?: CardPadding;
  /** Additional CSS classes */
  className?: string;
  /** Optional card title */
  title?: string;
  /** Optional card description */
  description?: string;
  /** Optional actions (buttons, etc.) to display in the header */
  actions?: React.ReactNode;
  /** Whether to use card-body wrapper for children */
  useBody?: boolean;
}

const variantStyles: Record<CardVariant, string> = {
  default: "bg-base-100 shadow-xl rounded-xl border border-base-300",
  compact: "bg-base-100 shadow-sm rounded-lg border border-base-300",
  elevated: "bg-base-100 shadow-2xl rounded-2xl border border-base-200",
};

const paddingStyles: Record<CardPadding, string> = {
  none: "",
  sm: "p-4",
  md: "p-4 sm:p-6",
  lg: "p-4 sm:p-8",
};

/**
 * Unified Card component for consistent card styling across the application.
 *
 * Usage:
 * ```tsx
 * // Basic card
 * <Card>Content</Card>
 *
 * // Card with title and actions
 * <Card title="Title" actions={<button>Action</button>}>
 *   Content
 * </Card>
 *
 * // Compact variant
 * <Card variant="compact" padding="sm">
 *   Compact content
 * </Card>
 * ```
 */
export function Card({
  children,
  variant = "default",
  padding = "md",
  className = "",
  title,
  description,
  actions,
  useBody = false,
}: CardProps) {
  const baseStyles = variantStyles[variant];
  const paddingStyle = paddingStyles[padding];

  const hasHeader = title || description || actions;

  const content = (
    <>
      {hasHeader && (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
          <div>
            {title && <h3 className="text-lg font-semibold">{title}</h3>}
            {description && (
              <p className="text-sm text-base-content/60">{description}</p>
            )}
          </div>
          {actions && <div className="flex-shrink-0">{actions}</div>}
        </div>
      )}
      {children}
    </>
  );

  return (
    <div className={`card ${baseStyles} ${className}`}>
      {useBody ? (
        <div className={`card-body ${paddingStyle}`}>{content}</div>
      ) : (
        <div className={paddingStyle}>{content}</div>
      )}
    </div>
  );
}
