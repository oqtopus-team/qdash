"use client";

interface SkeletonProps {
  className?: string;
  variant?: "text" | "circular" | "rectangular" | "rounded";
  width?: string | number;
  height?: string | number;
  animation?: "pulse" | "wave" | "none";
}

/**
 * Skeleton loading placeholder component
 * Uses DaisyUI's skeleton class with custom animations
 */
export function Skeleton({
  className = "",
  variant = "text",
  width,
  height,
  animation = "pulse",
}: SkeletonProps) {
  const baseClass = "bg-base-300";

  const variantClasses = {
    text: "rounded h-4",
    circular: "rounded-full",
    rectangular: "rounded-none",
    rounded: "rounded-lg",
  };

  const animationClasses = {
    pulse: "animate-pulse",
    wave: "skeleton",
    none: "",
  };

  const style: React.CSSProperties = {};
  if (width) style.width = typeof width === "number" ? `${width}px` : width;
  if (height)
    style.height = typeof height === "number" ? `${height}px` : height;

  return (
    <div
      className={`${baseClass} ${variantClasses[variant]} ${animationClasses[animation]} ${className}`}
      style={style}
    />
  );
}

/**
 * Skeleton for text content - multiple lines
 */
export function SkeletonText({
  lines = 3,
  className = "",
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          variant="text"
          width={i === lines - 1 ? "75%" : "100%"}
        />
      ))}
    </div>
  );
}

/**
 * Skeleton for card content
 */
export function SkeletonCard({
  className = "",
  hasImage = false,
  lines = 3,
}: {
  className?: string;
  hasImage?: boolean;
  lines?: number;
}) {
  return (
    <div className={`card bg-base-200 shadow-sm ${className}`}>
      {hasImage && (
        <Skeleton variant="rectangular" height={160} className="w-full" />
      )}
      <div className="card-body p-4">
        <Skeleton variant="text" height={20} width="60%" className="mb-2" />
        <SkeletonText lines={lines} />
      </div>
    </div>
  );
}

/**
 * Skeleton for table rows
 */
export function SkeletonTable({
  rows = 5,
  columns = 4,
  className = "",
}: {
  rows?: number;
  columns?: number;
  className?: string;
}) {
  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="table w-full">
        <thead>
          <tr>
            {Array.from({ length: columns }).map((_, i) => (
              <th key={i}>
                <Skeleton variant="text" height={16} width="80%" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <tr key={rowIndex}>
              {Array.from({ length: columns }).map((_, colIndex) => (
                <td key={colIndex}>
                  <Skeleton
                    variant="text"
                    height={14}
                    width={colIndex === 0 ? "90%" : "70%"}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Skeleton for metric/stat cards grid
 */
export function SkeletonMetricGrid({
  count = 4,
  className = "",
}: {
  count?: number;
  className?: string;
}) {
  return (
    <div
      className={`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 ${className}`}
    >
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="card bg-base-200 shadow-sm p-4">
          <Skeleton variant="text" height={14} width="40%" className="mb-2" />
          <Skeleton variant="text" height={32} width="60%" className="mb-1" />
          <Skeleton variant="text" height={12} width="50%" />
        </div>
      ))}
    </div>
  );
}

/**
 * Skeleton for chart/plot area
 */
export function SkeletonChart({
  height = 300,
  className = "",
}: {
  height?: number;
  className?: string;
}) {
  return (
    <div className={`card bg-base-200 shadow-sm ${className}`}>
      <div className="card-body p-4">
        <div className="flex justify-between items-center mb-4">
          <Skeleton variant="text" height={20} width={150} />
          <div className="flex gap-2">
            <Skeleton variant="rounded" height={32} width={80} />
            <Skeleton variant="rounded" height={32} width={80} />
          </div>
        </div>
        <Skeleton variant="rounded" height={height} className="w-full" />
      </div>
    </div>
  );
}

/**
 * Skeleton for list items
 */
export function SkeletonList({
  items = 5,
  hasAvatar = false,
  className = "",
}: {
  items?: number;
  hasAvatar?: boolean;
  className?: string;
}) {
  return (
    <div className={`space-y-3 ${className}`}>
      {Array.from({ length: items }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 p-2">
          {hasAvatar && <Skeleton variant="circular" width={40} height={40} />}
          <div className="flex-1 space-y-2">
            <Skeleton variant="text" height={16} width="70%" />
            <Skeleton variant="text" height={12} width="50%" />
          </div>
        </div>
      ))}
    </div>
  );
}
