import { ReactNode } from "react";

interface ErrorCardProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  icon?: ReactNode;
  className?: string;
}

/**
 * Reusable error state component with consistent styling
 */
export function ErrorCard({
  title = "Error",
  message,
  onRetry,
  icon,
  className = "",
}: ErrorCardProps) {
  return (
    <div
      className={`card bg-base-100 shadow-xl rounded-xl p-8 border border-error/20 ${className}`}
    >
      <div className="flex flex-col items-center text-center space-y-4">
        {/* Error Icon */}
        {icon || (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-16 h-16 text-error"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="15" y1="9" x2="9" y2="15"></line>
            <line x1="9" y1="9" x2="15" y2="15"></line>
          </svg>
        )}

        {/* Error Title */}
        <h3 className="text-xl font-semibold text-error">{title}</h3>

        {/* Error Message */}
        <p className="text-base-content/70 max-w-md">{message}</p>

        {/* Retry Button */}
        {onRetry && (
          <div className="card-actions">
            <button
              className="btn btn-error btn-outline gap-2"
              onClick={onRetry}
              type="button"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="w-4 h-4"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="23 4 23 10 17 10"></polyline>
                <polyline points="1 20 1 14 7 14"></polyline>
                <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"></path>
              </svg>
              Try Again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
