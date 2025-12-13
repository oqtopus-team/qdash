/**
 * Skeleton components using DaisyUI's skeleton class
 * @see https://daisyui.com/components/skeleton/
 */

interface SkeletonProps {
  className?: string;
  width?: string;
  height?: string;
}

/**
 * Base skeleton component using DaisyUI
 */
export function Skeleton({ className = "", width, height }: SkeletonProps) {
  const style: React.CSSProperties = {};
  if (width) style.width = width;
  if (height) style.height = height;

  return <div className={`skeleton ${className}`} style={style} />;
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
        <div
          key={i}
          className={`skeleton h-4 ${i === lines - 1 ? "w-3/4" : "w-full"}`}
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
      {hasImage && <div className="skeleton h-40 w-full rounded-t-lg" />}
      <div className="card-body p-4">
        <div className="skeleton h-5 w-3/5 mb-2" />
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
                <div className="skeleton h-4 w-4/5" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <tr key={rowIndex}>
              {Array.from({ length: columns }).map((_, colIndex) => (
                <td key={colIndex}>
                  <div
                    className={`skeleton h-3.5 ${colIndex === 0 ? "w-11/12" : "w-3/4"}`}
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
          <div className="skeleton h-5 w-36" />
          <div className="flex gap-2">
            <div className="skeleton h-8 w-20 rounded-lg" />
            <div className="skeleton h-8 w-20 rounded-lg" />
          </div>
        </div>
        <div className="skeleton w-full rounded-lg" style={{ height }} />
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
          {hasAvatar && <div className="skeleton h-10 w-10 rounded-full" />}
          <div className="flex-1 space-y-2">
            <div className="skeleton h-4 w-3/4" />
            <div className="skeleton h-3 w-1/2" />
          </div>
        </div>
      ))}
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
          <div className="skeleton h-3.5 w-2/5 mb-2" />
          <div className="skeleton h-8 w-3/5 mb-1" />
          <div className="skeleton h-3 w-1/2" />
        </div>
      ))}
    </div>
  );
}
