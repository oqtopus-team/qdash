"use client";

import {
  useState,
  useEffect,
  useCallback,
  useRef,
  type RefObject,
} from "react";

import {
  calculateCellSize,
  calculateGridContainerWidth,
  calculateGridDimension,
  checkIsMobile,
  getGridGap,
  getGridPadding,
} from "@/utils/gridLayout";

interface UseGridLayoutParams {
  /** Number of columns in the grid */
  cols: number;
  /** Number of rows in the grid */
  rows: number;
  /** Custom minimum cell size (optional) */
  minCellSize?: number;
  /** Height to reserve for header/controls (default: 300 mobile, 350 desktop) */
  reservedHeight?: { mobile: number; desktop: number };
  /** Additional dependencies that should trigger recalculation */
  deps?: unknown[];
}

interface UseGridLayoutResult {
  /** Reference to attach to the container element */
  containerRef: RefObject<HTMLDivElement>;
  /** Calculated cell size in pixels */
  cellSize: number;
  /** Whether the viewport is mobile width */
  isMobile: boolean;
  /** Gap between cells in pixels */
  gap: number;
  /** Padding for grid container in pixels */
  padding: number;
  /** Calculate grid dimension (width or height) without padding */
  getGridDimension: (count: number) => number;
  /** Calculate grid container width with padding */
  getContainerWidth: (cols: number) => number;
  /** Force recalculation of sizes */
  updateSize: () => void;
}

/**
 * Get dynamic reserved height based on viewport height.
 * Smaller viewports get reduced reserved height to maximize grid space.
 */
function getDynamicReservedHeight(
  viewportHeight: number,
  isMobile: boolean,
  base: { mobile: number; desktop: number },
): number {
  if (isMobile) return base.mobile;
  if (viewportHeight < 700) return Math.min(base.desktop, 220);
  if (viewportHeight < 900) return Math.min(base.desktop, 280);
  return base.desktop;
}

/**
 * Custom hook for managing responsive grid layout
 * Handles cell size calculation, resize events, and provides utility functions
 */
export function useGridLayout({
  cols,
  rows,
  minCellSize,
  reservedHeight = { mobile: 300, desktop: 350 },
  deps = [],
}: UseGridLayoutParams): UseGridLayoutResult {
  const containerRef = useRef<HTMLDivElement>(null);
  const [cellSize, setCellSize] = useState(60);
  const [isMobile, setIsMobile] = useState(false);
  const [viewportHeight, setViewportHeight] = useState(
    typeof window !== "undefined" ? window.innerHeight : 1080,
  );

  const updateSize = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    const viewportWidth = window.innerWidth;
    const vh = window.innerHeight;
    const mobile = checkIsMobile(viewportWidth);
    setIsMobile(mobile);
    setViewportHeight(vh);

    const containerPadding = mobile ? 16 : 32;
    const containerWidth =
      Math.min(container.offsetWidth, viewportWidth) - containerPadding * 2;
    const dynamicReserved = getDynamicReservedHeight(
      vh,
      mobile,
      reservedHeight,
    );
    const availableHeight = vh - dynamicReserved;

    const newCellSize = calculateCellSize({
      containerWidth,
      availableHeight,
      cols,
      rows,
      isMobile: mobile,
      minCellSize,
    });

    setCellSize(newCellSize);
  }, [cols, rows, minCellSize, reservedHeight.mobile, reservedHeight.desktop]);

  // Initial calculation and resize listener
  useEffect(() => {
    const timeoutId = setTimeout(updateSize, 0);
    window.addEventListener("resize", updateSize);
    return () => {
      clearTimeout(timeoutId);
      window.removeEventListener("resize", updateSize);
    };
  }, [updateSize]);

  // Recalculate when dependencies change
  useEffect(() => {
    updateSize();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [updateSize, ...deps]);

  const gap = getGridGap(isMobile, viewportHeight);
  const padding = getGridPadding(isMobile, viewportHeight);

  const getGridDimension = useCallback(
    (count: number) => calculateGridDimension(count, cellSize, isMobile),
    [cellSize, isMobile],
  );

  const getContainerWidth = useCallback(
    (colCount: number) =>
      calculateGridContainerWidth(colCount, cellSize, isMobile),
    [cellSize, isMobile],
  );

  return {
    containerRef,
    cellSize,
    isMobile,
    gap,
    padding,
    getGridDimension,
    getContainerWidth,
    updateSize,
  };
}
