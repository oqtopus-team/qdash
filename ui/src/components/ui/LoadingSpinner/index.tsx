"use client";

type LoadingSpinnerProps = {
  size?: "xs" | "sm" | "md" | "lg";
  color?: "primary" | "secondary" | "accent" | "neutral" | "info" | "success" | "warning" | "error";
};

export function LoadingSpinner({
  size = "lg",
  color = "primary",
}: LoadingSpinnerProps = {}) {
  return (
    <div className="flex justify-center items-center h-full">
      <span
        className={`loading loading-spinner loading-${size} text-${color}`}
        aria-label="Loading"
      />
    </div>
  );
}
