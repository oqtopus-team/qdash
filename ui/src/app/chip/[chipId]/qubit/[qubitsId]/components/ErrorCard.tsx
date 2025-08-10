interface ErrorCardProps {
  message: string;
  onRetry?: () => void;
  title?: string;
}

export function ErrorCard({ message, onRetry, title = "Error" }: ErrorCardProps) {
  return (
    <div className="card bg-base-100 shadow-xl rounded-xl p-6 border border-error/20">
      <div className="alert alert-error">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="stroke-current shrink-0 h-6 w-6"
          fill="none"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <div className="flex-1">
          <h3 className="font-bold">{title}</h3>
          <div className="text-sm">{message}</div>
        </div>
        {onRetry && (
          <button
            className="btn btn-sm btn-outline btn-error"
            onClick={onRetry}
            aria-label="Retry loading data"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
}