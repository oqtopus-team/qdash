"use client";

import { useEffect, useState } from "react";

import { toDateTimeLocal } from "@/lib/utils/datetime";

interface TimeRangeSelectorProps {
  startDate: string;
  endDate: string;
  onStartDateChange: (date: string) => void;
  onEndDateChange: (date: string) => void;
  onQuickRange: (days: number) => void;
}

export function TimeRangeSelector({
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
  onQuickRange,
}: TimeRangeSelectorProps) {
  const [localStart, setLocalStart] = useState(
    toDateTimeLocal(startDate),
  );
  const [localEnd, setLocalEnd] = useState(toDateTimeLocal(endDate));

  useEffect(() => {
    setLocalStart(toDateTimeLocal(startDate));
  }, [startDate]);

  useEffect(() => {
    setLocalEnd(toDateTimeLocal(endDate));
  }, [endDate]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium">Time Range</span>
        <div className="join">
          <button
            className="join-item btn btn-sm"
            onClick={() => onQuickRange(1)}
          >
            1D
          </button>
          <button
            className="join-item btn btn-sm"
            onClick={() => onQuickRange(7)}
          >
            7D
          </button>
          <button
            className="join-item btn btn-sm"
            onClick={() => onQuickRange(30)}
          >
            30D
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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
