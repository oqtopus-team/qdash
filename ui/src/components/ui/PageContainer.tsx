import React from "react";

interface PageContainerProps {
  children: React.ReactNode;
  className?: string;
  /** Use max-width constraint for content-heavy pages */
  maxWidth?: boolean;
}

/**
 * Unified page container component for consistent padding and background.
 *
 * Usage:
 * ```tsx
 * <PageContainer>
 *   <PageHeader title="..." />
 *   {content}
 * </PageContainer>
 * ```
 */
export function PageContainer({ children, className = "", maxWidth = false }: PageContainerProps) {
  return (
    // The right gutter widens to `--agent-tab-inset` while the layout's Ask Agent tab floats
    // over that edge; max() keeps it from adding to the usual gutter.
    <div
      className={`w-full min-h-screen bg-base-100/50 pl-4 pr-[max(1rem,var(--agent-tab-inset,0px))] md:pl-6 md:pr-[max(1.5rem,var(--agent-tab-inset,0px))] py-6 md:py-8 ${className}`}
    >
      {maxWidth ? <div className="max-w-[1600px] mx-auto">{children}</div> : children}
    </div>
  );
}
