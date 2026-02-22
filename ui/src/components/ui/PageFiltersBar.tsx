import React from "react";

interface PageFiltersBarProps {
  children: React.ReactNode;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Unified filter bar component for consistent filter/selector layout across pages.
 *
 * Usage pattern:
 * ```tsx
 * <PageFiltersBar>
 *   <PageFiltersBar.Group>
 *     <ChipSelector ... />
 *     <DateSelector ... />
 *   </PageFiltersBar.Group>
 *   <PageFiltersBar.Group position="end">
 *     <MetricSelector ... />
 *   </PageFiltersBar.Group>
 * </PageFiltersBar>
 * ```
 */
export function PageFiltersBar({
  children,
  className = "",
}: PageFiltersBarProps) {
  return (
    <div
      className={`flex flex-col md:flex-row md:justify-between md:items-center gap-4 ${className}`}
    >
      {children}
    </div>
  );
}

interface FilterGroupProps {
  children: React.ReactNode;
  /** Position: 'start' (left) or 'end' (right) on desktop */
  position?: "start" | "end";
  /** Additional CSS classes */
  className?: string;
}

/**
 * Group of filters within the filter bar
 */
function FilterGroup({
  children,
  position = "start",
  className = "",
}: FilterGroupProps) {
  const positionClass = position === "end" ? "md:ml-auto" : "";

  return (
    <div
      className={`flex flex-col sm:flex-row gap-3 sm:gap-4 ${positionClass} ${className}`}
    >
      {children}
    </div>
  );
}

interface FilterItemProps {
  children: React.ReactNode;
  /** Label for the filter (optional, shown above on mobile) */
  label?: string;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Individual filter item with optional label
 */
function FilterItem({ children, label, className = "" }: FilterItemProps) {
  return (
    <div className={`w-full sm:w-auto ${className}`}>
      {label && (
        <label className="label py-1 sm:hidden">
          <span className="label-text text-xs text-base-content/60">
            {label}
          </span>
        </label>
      )}
      {children}
    </div>
  );
}

// Attach subcomponents
PageFiltersBar.Group = FilterGroup;
PageFiltersBar.Item = FilterItem;
