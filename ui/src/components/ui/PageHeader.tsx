import React from "react";

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}

/**
 * Unified page header component for consistent styling across pages.
 *
 * Usage:
 * ```tsx
 * <PageHeader
 *   title="Page Title"
 *   description="Optional description text"
 *   actions={<button className="btn btn-primary">Action</button>}
 * />
 * ```
 */
export function PageHeader({
  title,
  description,
  actions,
  className = "",
}: PageHeaderProps) {
  return (
    <div
      className={`flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-4 sm:mb-6 ${className}`}
    >
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold">{title}</h1>
        {description && (
          <p className="text-sm text-base-content/70 mt-1">{description}</p>
        )}
      </div>
      {actions && <div className="flex-shrink-0">{actions}</div>}
    </div>
  );
}
