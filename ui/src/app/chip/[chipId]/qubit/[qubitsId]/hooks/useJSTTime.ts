import { useState, useCallback } from 'react';
import { TimeRangeState } from '../types';

/**
 * Custom hook for JST time formatting and management
 */
export function useJSTTime() {
  const formatJSTDate = useCallback((date: Date): string => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    const seconds = String(date.getSeconds()).padStart(2, "0");
    const milliseconds = String(date.getMilliseconds()).padStart(3, "0");
    return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}.${milliseconds}+09:00`;
  }, []);

  const getDefaultTimeRange = useCallback((daysBack: number = 30): TimeRangeState => ({
    startAt: formatJSTDate(new Date(Date.now() - daysBack * 24 * 60 * 60 * 1000)),
    endAt: formatJSTDate(new Date()),
    isStartAtLocked: false,
    isEndAtLocked: false,
  }), [formatJSTDate]);

  return {
    formatJSTDate,
    getDefaultTimeRange,
  };
}

/**
 * Custom hook for time range management with auto-update and locking
 */
export function useTimeRangeControls(initialDaysBack: number = 30) {
  const { formatJSTDate, getDefaultTimeRange } = useJSTTime();
  const [timeRange, setTimeRange] = useState<TimeRangeState>(() => 
    getDefaultTimeRange(initialDaysBack)
  );

  const updateStartAt = useCallback((value: string) => {
    setTimeRange(prev => ({
      ...prev,
      startAt: value,
      isStartAtLocked: true,
    }));
  }, []);

  const updateEndAt = useCallback((value: string) => {
    setTimeRange(prev => ({
      ...prev,
      endAt: value,
      isEndAtLocked: true,
    }));
  }, []);

  const toggleStartAtLock = useCallback(() => {
    setTimeRange(prev => {
      const newLocked = !prev.isStartAtLocked;
      return {
        ...prev,
        isStartAtLocked: newLocked,
        startAt: newLocked 
          ? prev.startAt 
          : formatJSTDate(new Date(Date.now() - initialDaysBack * 24 * 60 * 60 * 1000)),
      };
    });
  }, [formatJSTDate, initialDaysBack]);

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

  const resetTimeRange = useCallback(() => {
    setTimeRange(getDefaultTimeRange(initialDaysBack));
  }, [getDefaultTimeRange, initialDaysBack]);

  return {
    timeRange,
    updateStartAt,
    updateEndAt,
    toggleStartAtLock,
    toggleEndAtLock,
    resetTimeRange,
  };
}