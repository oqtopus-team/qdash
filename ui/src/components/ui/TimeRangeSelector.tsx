"use client";

import { useEffect, useState } from "react";

import { CalendarRange, ChevronDown } from "lucide-react";

interface TimeRangeSelectorProps {
  startDate: string;
  endDate: string;
  onStartDateChange: (date: string) => void;
  onEndDateChange: (date: string) => void;
  onQuickRange: (days: number) => void;
  collapsible?: boolean;
}

export function TimeRangeSelector({
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
  onQuickRange,
  collapsible = false,
}: TimeRangeSelectorProps) {
  // `startDate` / `endDate` are already datetime-local strings in the display
  // timezone (e.g. "2026-06-21T15:30"), produced by useRangeModeUrlState /
  // dateToDateTimeLocal. They must be shown verbatim in the
  // <input type="datetime-local">. Do NOT pass them through toDateTimeLocal():
  // that helper treats a timezone-less string as UTC and shifts it into the
  // display timezone, double-applying the offset (+9h for JST). See issue #1107.
  const [localStart, setLocalStart] = useState(startDate);
  const [localEnd, setLocalEnd] = useState(endDate);
  const [showCustomRange, setShowCustomRange] = useState(!collapsible);

  useEffect(() => {
    setLocalStart(startDate);
  }, [startDate]);

  useEffect(() => {
    setLocalEnd(endDate);
  }, [endDate]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">Time Range</span>
        <div className="join">
          <button
            type="button"
            className="join-item btn btn-sm"
            onClick={() => {
              onQuickRange(1);
              if (collapsible) setShowCustomRange(false);
            }}
          >
            1D
          </button>
          <button
            type="button"
            className="join-item btn btn-sm"
            onClick={() => {
              onQuickRange(7);
              if (collapsible) setShowCustomRange(false);
            }}
          >
            7D
          </button>
          <button
            type="button"
            className="join-item btn btn-sm"
            onClick={() => {
              onQuickRange(30);
              if (collapsible) setShowCustomRange(false);
            }}
          >
            30D
          </button>
        </div>
        {collapsible && (
          <button
            type="button"
            className={`btn btn-sm gap-1.5 ${showCustomRange ? "btn-ghost bg-base-200" : "btn-ghost"}`}
            aria-expanded={showCustomRange}
            aria-controls="custom-time-range"
            onClick={() => setShowCustomRange((visible) => !visible)}
          >
            <CalendarRange className="h-4 w-4" aria-hidden="true" />
            Custom
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform ${showCustomRange ? "rotate-180" : ""}`}
              aria-hidden="true"
            />
          </button>
        )}
      </div>

      <div
        id="custom-time-range"
        className={`${showCustomRange ? "grid" : "hidden"} grid-cols-1 gap-4 sm:grid-cols-2`}
      >
        <div className="form-control w-full">
          <label className="label">
            <span className="label-text">From</span>
          </label>
          <input
            type="datetime-local"
            className="input input-bordered w-full"
            value={localStart}
            onChange={(e) => {
              setLocalStart(e.target.value);
              onStartDateChange(e.target.value);
            }}
            max={localEnd}
            aria-label="Start date and time"
          />
        </div>
        <div className="form-control w-full">
          <label className="label">
            <span className="label-text">To</span>
          </label>
          <input
            type="datetime-local"
            className="input input-bordered w-full"
            value={localEnd}
            onChange={(e) => {
              setLocalEnd(e.target.value);
              onEndDateChange(e.target.value);
            }}
            min={localStart}
            aria-label="End date and time"
          />
        </div>
      </div>
    </div>
  );
}
