import { useMemo, useCallback } from "react";
import { useFetchChipDates } from "@/client/chip/chip";

interface UseDateNavigationResult {
  availableDates: string[];
  navigateToPreviousDay: () => void;
  navigateToNextDay: () => void;
  canNavigatePrevious: boolean;
  canNavigateNext: boolean;
  formatDate: (dateStr: string) => string;
  isLoading: boolean;
  isError: boolean;
}

export function useDateNavigation(
  chipId: string,
  selectedDate: string,
  onDateChange?: (date: string) => void,
): UseDateNavigationResult {
  // Fetch available dates for navigation
  const {
    data: datesResponse,
    isLoading,
    isError,
  } = useFetchChipDates(chipId, {
    query: {
      enabled: !!chipId,
      staleTime: 300000, // 5 minutes - dates don't change frequently
    },
  });

  // Get available dates for navigation with optimized sorting
  const availableDates = useMemo(() => {
    const dates = ["latest"];
    if (datesResponse?.data?.data && Array.isArray(datesResponse.data.data)) {
      // Sort dates in descending order (newest first)
      const sortedDates = [...datesResponse.data.data].sort((a, b) =>
        b.localeCompare(a),
      );
      dates.push(...sortedDates);
    }
    return dates;
  }, [datesResponse?.data?.data]);

  // Format date string for display (YYYYMMDD -> YYYY/MM/DD)
  const formatDate = useCallback((dateStr: string): string => {
    if (dateStr === "latest") return "Latest";
    return `${dateStr.slice(0, 4)}/${dateStr.slice(4, 6)}/${dateStr.slice(
      6,
      8,
    )}`;
  }, []);

  // Optimize indexOf performance by caching the current index
  const currentIndex = useMemo(
    () => availableDates.indexOf(selectedDate),
    [availableDates, selectedDate],
  );

  // Navigation functions using cached index
  const navigateToPreviousDay = useCallback(() => {
    if (!onDateChange || currentIndex <= 0) return;
    onDateChange(availableDates[currentIndex - 1]);
  }, [availableDates, currentIndex, onDateChange]);

  const navigateToNextDay = useCallback(() => {
    if (!onDateChange || currentIndex >= availableDates.length - 1) return;
    onDateChange(availableDates[currentIndex + 1]);
  }, [availableDates, currentIndex, onDateChange]);

  const canNavigatePrevious = currentIndex > 0;
  const canNavigateNext = currentIndex < availableDates.length - 1;

  return {
    availableDates,
    navigateToPreviousDay,
    navigateToNextDay,
    canNavigatePrevious,
    canNavigateNext,
    formatDate,
    isLoading,
    isError,
  };
}
