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
export function PageContainer({
  children,
  className = "",
  maxWidth = false,
}: PageContainerProps) {
  return (
    <div
      className={`w-full min-h-screen bg-base-100/50 px-4 md:px-6 py-6 md:py-8 ${className}`}
    >
      {maxWidth ? (
        <div className="max-w-[1600px] mx-auto">{children}</div>
      ) : (
        children
      )}
    </div>
  );
}
