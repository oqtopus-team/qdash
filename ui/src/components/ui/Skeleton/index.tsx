/**
 * Skeleton components using DaisyUI's skeleton class
 * @see https://daisyui.com/components/skeleton/
 */

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
