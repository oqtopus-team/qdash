"use client";

interface AbsoluteDateRangePickerProps {
  startDate: string | null;
  endDate: string | null;
  onStartChange: (value: string | null) => void;
  onEndChange: (value: string | null) => void;
}

export function AbsoluteDateRangePicker({
  startDate,
  endDate,
  onStartChange,
  onEndChange,
}: AbsoluteDateRangePickerProps) {
  const hasInvertedRange =
    startDate !== null && endDate !== null && startDate > endDate;

  return (
    <div className="flex flex-col gap-1 w-full sm:w-auto">
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
        <label className="flex items-center gap-2">
          <span className="label-text w-10 sm:w-auto">From</span>
          <input
            type="date"
            className="input input-sm input-bordered tabular-nums flex-1 sm:w-32"
            value={startDate ?? ""}
            onChange={(e) => onStartChange(e.target.value || null)}
            max={endDate ?? undefined}
            aria-label="Start date"
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="label-text w-10 sm:w-auto">To</span>
          <input
            type="date"
            className="input input-sm input-bordered tabular-nums flex-1 sm:w-32"
            value={endDate ?? ""}
            onChange={(e) => onEndChange(e.target.value || null)}
            min={startDate ?? undefined}
            aria-label="End date"
          />
        </label>
      </div>
      {hasInvertedRange && (
        <span className="text-xs text-error">
          Start date must be on or before end date
        </span>
      )}
    </div>
  );
}
