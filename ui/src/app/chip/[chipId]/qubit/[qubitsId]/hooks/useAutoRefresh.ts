import { useEffect, useCallback } from 'react';
import { useJSTTime } from './useJSTTime';
import { TimeRangeState } from '../types';

interface UseAutoRefreshOptions {
  intervalSeconds?: number;
  enabled?: boolean;
}

/**
 * Custom hook for automatic time range refresh
 */
export function useAutoRefresh(
  timeRange: TimeRangeState,
  onTimeRangeUpdate: (update: Partial<TimeRangeState>) => void,
  options: UseAutoRefreshOptions = {}
) {
  const { intervalSeconds = 30, enabled = true } = options;
  const { formatJSTDate } = useJSTTime();

  const updateTimes = useCallback(() => {
    const now = new Date();
    const updates: Partial<TimeRangeState> = {};

    if (!timeRange.isEndAtLocked) {
      updates.endAt = formatJSTDate(now);
    }

    if (!timeRange.isStartAtLocked && !timeRange.isEndAtLocked) {
      updates.startAt = formatJSTDate(
        new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
      );
    }

    if (Object.keys(updates).length > 0) {
      onTimeRangeUpdate(updates);
    }
  }, [
    timeRange.isStartAtLocked,
    timeRange.isEndAtLocked,
    formatJSTDate,
    onTimeRangeUpdate,
  ]);

  useEffect(() => {
    if (!enabled) return;

    const timer = setInterval(updateTimes, intervalSeconds * 1000);
    return () => clearInterval(timer);
  }, [enabled, intervalSeconds, updateTimes]);

  return { updateTimes };
}