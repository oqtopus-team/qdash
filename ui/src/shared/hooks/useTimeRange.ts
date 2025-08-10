import { useState, useEffect, useCallback } from 'react';
import { TimeRangeState } from '../types/analysis';

interface UseTimeRangeOptions {
  initialDays?: number;
  refreshIntervalSeconds?: number;
}

/**
 * Custom hook for managing time ranges with JST timezone support
 * Extracted from qubit detail page for reuse across analysis components
 */
export function useTimeRange(options: UseTimeRangeOptions = {}) {
  const { 
    initialDays = 7, 
    refreshIntervalSeconds = 30 
  } = options;

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
    startAt: formatJSTDate(new Date(Date.now() - initialDays * 24 * 60 * 60 * 1000)),
    isStartAtLocked: false,
    isEndAtLocked: false,
  }));

  // Auto-update times when not locked
  useEffect(() => {
    const timer = setInterval(() => {
      setTimeRange(prev => ({
        ...prev,
        endAt: prev.isEndAtLocked ? prev.endAt : formatJSTDate(new Date()),
        startAt: prev.isStartAtLocked || prev.isEndAtLocked 
          ? prev.startAt 
          : formatJSTDate(new Date(Date.now() - initialDays * 24 * 60 * 60 * 1000)),
      }));
    }, refreshIntervalSeconds * 1000);

    return () => clearInterval(timer);
  }, [formatJSTDate, initialDays, refreshIntervalSeconds]);

  // Update start time
  const updateStartAt = useCallback((value: string) => {
    setTimeRange(prev => ({
      ...prev,
      startAt: value,
      isStartAtLocked: true,
    }));
  }, []);

  // Update end time
  const updateEndAt = useCallback((value: string) => {
    setTimeRange(prev => ({
      ...prev,
      endAt: value,
      isEndAtLocked: true,
    }));
  }, []);

  // Toggle start time lock
  const toggleStartAtLock = useCallback(() => {
    setTimeRange(prev => {
      const newLocked = !prev.isStartAtLocked;
      return {
        ...prev,
        isStartAtLocked: newLocked,
        startAt: newLocked 
          ? prev.startAt 
          : formatJSTDate(new Date(Date.now() - initialDays * 24 * 60 * 60 * 1000)),
      };
    });
  }, [formatJSTDate, initialDays]);

  // Toggle end time lock
  const toggleEndAtLock = useCallback(() => {
    setTimeRange(prev => {
      const newLocked = !prev.isEndAtLocked;
      return {
        ...prev,
        isEndAtLocked: newLocked,
        endAt: newLocked ? prev.endAt : formatJSTDate(new Date()),
      };
    });
  }, [formatJSTDate]);

  // Get lock status description
  const getLockStatusDescription = useCallback(() => {
    const { isStartAtLocked, isEndAtLocked } = timeRange;
    
    if (!isStartAtLocked && !isEndAtLocked) {
      return `Both times auto-update every ${refreshIntervalSeconds} seconds`;
    }
    if (isStartAtLocked && isEndAtLocked) {
      return "Both times are fixed";
    }
    if (isStartAtLocked) {
      return "Start time is fixed, end time auto-updates";
    }
    return "End time is fixed, start time auto-updates";
  }, [timeRange, refreshIntervalSeconds]);

  return {
    timeRange,
    updateStartAt,
    updateEndAt,
    toggleStartAtLock,
    toggleEndAtLock,
    getLockStatusDescription,
    formatJSTDate,
  };
}