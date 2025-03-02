"use client";

export function TimeSeriesView() {
  return (
    <div className="card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
      <div className="flex items-center gap-4 mb-6">
        <h2 className="text-2xl font-semibold">Time Series Analysis</h2>
      </div>
      <div className="alert alert-info">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          className="stroke-current shrink-0 w-6 h-6"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <span>Time series analysis will be available here</span>
      </div>
    </div>
  );
}
