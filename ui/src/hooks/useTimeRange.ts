import { useState, useCallback } from "react";

import type { TimeRangeState } from "@/types/analysis";

interface UseTimeRangeOptions {
  initialDays?: number;
}

/**
 * Custom hook for managing time ranges with JST timezone support
 * Manual refresh approach - no automatic updates to preserve user settings
 */
export function useTimeRange(options: UseTimeRangeOptions = {}) {
  const { initialDays = 7 } = options;

  // Format date with JST timezone
  const formatJSTDate = useCallback((date: Date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    const seconds = String(date.getSeconds()).padStart(2, "0");
    const milliseconds = String(date.getMilliseconds()).padStart(3, "0");
    return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}.${milliseconds}+09:00`;
  }, []);

  const [timeRange, setTimeRange] = useState<TimeRangeState>(() => ({
    endAt: formatJSTDate(new Date()),
    startAt: formatJSTDate(
      new Date(Date.now() - initialDays * 24 * 60 * 60 * 1000),
    ),
    isStartAtLocked: false,
    isEndAtLocked: false,
  }));

  // Manual refresh function
  const refreshTimeRange = useCallback(() => {
    setTimeRange((prev) => ({
      ...prev,
      endAt: prev.isEndAtLocked ? prev.endAt : formatJSTDate(new Date()),
      startAt:
        prev.isStartAtLocked || prev.isEndAtLocked
          ? prev.startAt
          : formatJSTDate(
              new Date(Date.now() - initialDays * 24 * 60 * 60 * 1000),
            ),
    }));
  }, [formatJSTDate, initialDays]);

  // Update start time
  const updateStartAt = useCallback((value: string) => {
    setTimeRange((prev) => ({
      ...prev,
      startAt: value,
      isStartAtLocked: true,
    }));
  }, []);

  // Update end time
  const updateEndAt = useCallback((value: string) => {
    setTimeRange((prev) => ({
      ...prev,
      endAt: value,
      isEndAtLocked: true,
    }));
  }, []);

  // Toggle start time lock
  const toggleStartAtLock = useCallback(() => {
    setTimeRange((prev) => {
      const newLocked = !prev.isStartAtLocked;
      return {
        ...prev,
        isStartAtLocked: newLocked,
        // Don't auto-update when toggling - preserve current value
      };
    });
  }, []);

  // Toggle end time lock
  const toggleEndAtLock = useCallback(() => {
    setTimeRange((prev) => {
      const newLocked = !prev.isEndAtLocked;
      return {
        ...prev,
        isEndAtLocked: newLocked,
        // Don't auto-update when toggling - preserve current value
      };
    });
  }, []);

  // Get lock status description
  const getLockStatusDescription = useCallback(() => {
    const { isStartAtLocked, isEndAtLocked } = timeRange;

    if (!isStartAtLocked && !isEndAtLocked) {
      return "Both times will update when refreshed manually";
    }
    if (isStartAtLocked && isEndAtLocked) {
      return "Both times are fixed";
    }
    if (isStartAtLocked) {
      return "Start time is fixed, end time will update when refreshed";
    }
    return "End time is fixed, start time will update when refreshed";
  }, [timeRange]);

  return {
    timeRange,
    updateStartAt,
    updateEndAt,
    toggleStartAtLock,
    toggleEndAtLock,
    refreshTimeRange,
    getLockStatusDescription,
    formatJSTDate,
  };
}
