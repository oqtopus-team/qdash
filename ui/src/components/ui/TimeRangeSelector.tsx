"use client";

import type { RangeMode, TimeRange } from "@/hooks/url-state/types";

import { AbsoluteDateRangePicker } from "./AbsoluteDateRangePicker";

interface TimeRangeSelectorProps {
  rangeMode: RangeMode;
  timeRange: TimeRange;
  startDate: string | null;
  endDate: string | null;
  onRangeModeChange: (mode: RangeMode) => void;
  onTimeRangeChange: (range: TimeRange) => void;
  onStartDateChange: (date: string | null) => void;
  onEndDateChange: (date: string | null) => void;
}

export function TimeRangeSelector({
  rangeMode,
  timeRange,
  startDate,
  endDate,
  onRangeModeChange,
  onTimeRangeChange,
  onStartDateChange,
  onEndDateChange,
}: TimeRangeSelectorProps) {
  return (
    <>
      <select
        className="select select-sm select-bordered w-full sm:w-28"
        value={rangeMode}
        onChange={(e) => onRangeModeChange(e.target.value as RangeMode)}
      >
        <option value="relative">Relative</option>
        <option value="absolute">Absolute</option>
      </select>

      {rangeMode === "relative" ? (
        <div className="join h-8 sm:h-9">
          <button
            className={`join-item btn btn-sm h-full ${timeRange === "1d" ? "btn-primary" : ""}`}
            onClick={() => onTimeRangeChange("1d")}
          >
            1D
          </button>
          <button
            className={`join-item btn btn-sm h-full ${timeRange === "7d" ? "btn-primary" : ""}`}
            onClick={() => onTimeRangeChange("7d")}
          >
            7D
          </button>
          <button
            className={`join-item btn btn-sm h-full ${timeRange === "30d" ? "btn-primary" : ""}`}
            onClick={() => onTimeRangeChange("30d")}
          >
            30D
          </button>
        </div>
      ) : (
        <AbsoluteDateRangePicker
          startDate={startDate}
          endDate={endDate}
          onStartChange={onStartDateChange}
          onEndChange={onEndDateChange}
        />
      )}
    </>
  );
}
