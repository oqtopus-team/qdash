"use client";

/**
 * Environment badge component that displays the current environment name.
 * Uses NEXT_PUBLIC_ENV environment variable.
 */
export function EnvironmentBadge({ className }: { className?: string }) {
  const env = process.env.NEXT_PUBLIC_ENV;

  if (!env) {
    return null;
  }

  return (
    <div
      className={`badge badge-primary font-bold ${className ?? "badge-md"}`}
      title={`Environment: ${env}`}
    >
      {env}
    </div>
  );
}
