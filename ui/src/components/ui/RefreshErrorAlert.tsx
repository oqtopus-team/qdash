import { RefreshCw, TriangleAlert } from "lucide-react";

interface RefreshErrorAlertProps {
  /** What failed to refresh, stated so the reader knows the content shown is older. */
  message: string;
  onRetry: () => void;
  /** A retry is in flight: the button is disabled and shows progress. */
  retrying?: boolean;
  className?: string;
}

/**
 * Non-blocking notice for a failed background refetch. The previously loaded content stays on
 * screen below it; the notice only says it may be out of date and offers a retry.
 */
export function RefreshErrorAlert({
  message,
  onRetry,
  retrying = false,
  className = "",
}: RefreshErrorAlertProps) {
  return (
    <div
      role="alert"
      className={`alert alert-warning alert-soft alert-vertical py-2 text-sm sm:alert-horizontal ${className}`}
    >
      <TriangleAlert className="h-4 w-4" aria-hidden="true" />
      <span>{message}</span>
      <button type="button" className="btn btn-sm" onClick={onRetry} disabled={retrying}>
        {retrying ? (
          <span data-icon="inline-start" className="loading loading-spinner loading-xs" />
        ) : (
          <RefreshCw data-icon="inline-start" aria-hidden="true" />
        )}
        Retry
      </button>
    </div>
  );
}
