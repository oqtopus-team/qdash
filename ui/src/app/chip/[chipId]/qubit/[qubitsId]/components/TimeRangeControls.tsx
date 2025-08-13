import type { TimeRangeState } from "../types";

import { DateTimePicker } from "@/app/components/DateTimePicker";

interface TimeRangeControlsProps {
  timeRange: TimeRangeState;
  onStartAtChange: (value: string) => void;
  onEndAtChange: (value: string) => void;
  onToggleStartAtLock: () => void;
  onToggleEndAtLock: () => void;
  disabled?: boolean;
}

export function TimeRangeControls({
  timeRange,
  onStartAtChange,
  onEndAtChange,
  onToggleStartAtLock,
  onToggleEndAtLock,
  disabled = false,
}: TimeRangeControlsProps) {
  const { startAt, endAt, isStartAtLocked, isEndAtLocked } = timeRange;

  return (
    <div className="space-y-4">
      <span className="text-sm font-medium block">Time Range</span>
      <div className="grid grid-cols-2 gap-4">
        <div className="flex items-start gap-2">
          <div className="flex-1">
            <DateTimePicker
              label="From"
              value={startAt}
              onChange={onStartAtChange}
              disabled={disabled}
            />
          </div>
          <button
            className={`btn btn-sm mt-8 gap-2 ${
              isStartAtLocked ? "btn-primary" : "btn-ghost"
            }`}
            onClick={onToggleStartAtLock}
            title={isStartAtLocked ? "Unlock start time" : "Lock start time"}
            disabled={disabled}
            aria-label={
              isStartAtLocked ? "Unlock start time" : "Lock start time"
            }
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
              {isStartAtLocked ? (
                <>
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </>
              ) : (
                <>
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 9.9-1" />
                </>
              )}
            </svg>
            <span>{isStartAtLocked ? "Fixed" : "Auto"}</span>
          </button>
        </div>
        <div className="flex items-start gap-2">
          <div className="flex-1">
            <DateTimePicker
              label="To"
              value={endAt}
              onChange={onEndAtChange}
              disabled={disabled}
            />
          </div>
          <button
            className={`btn btn-sm mt-8 gap-2 ${
              isEndAtLocked ? "btn-primary" : "btn-ghost"
            }`}
            onClick={onToggleEndAtLock}
            title={isEndAtLocked ? "Unlock end time" : "Lock end time"}
            disabled={disabled}
            aria-label={isEndAtLocked ? "Unlock end time" : "Lock end time"}
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
              {isEndAtLocked ? (
                <>
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </>
              ) : (
                <>
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 9.9-1" />
                </>
              )}
            </svg>
            <span>{isEndAtLocked ? "Fixed" : "Auto"}</span>
          </button>
        </div>
      </div>
      <div className="mt-2 text-xs text-base-content/70 flex items-center gap-1">
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
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12" y2="8" />
        </svg>
        {!isStartAtLocked && !isEndAtLocked
          ? "Both times auto-update every 30 seconds"
          : isStartAtLocked && isEndAtLocked
            ? "Both times are fixed"
            : isStartAtLocked
              ? "Start time is fixed, end time auto-updates"
              : "End time is fixed, start time auto-updates"}
      </div>
    </div>
  );
}
