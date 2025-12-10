"use client";

/**
 * Environment badge component that displays the current environment name.
 * Uses NEXT_PUBLIC_ENV environment variable.
 */
export function EnvironmentBadge({
  size = "md",
}: {
  size?: "sm" | "md" | "lg";
}) {
  const env = process.env.NEXT_PUBLIC_ENV;

  if (!env) {
    return null;
  }

  const sizeClasses = {
    sm: "badge-sm text-xs px-2 py-0.5",
    md: "badge-md text-sm px-3 py-1",
    lg: "badge-lg text-base px-4 py-1.5",
  };

  return (
    <div
      className={`badge badge-primary font-bold ${sizeClasses[size]}`}
      title={`Environment: ${env}`}
    >
      {env}
    </div>
  );
}
