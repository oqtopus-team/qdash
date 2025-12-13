/**
 * Grid layout utilities for consistent grid sizing across components
 */

/** Grid gap in pixels based on mobile/desktop */
export const GRID_GAP = {
  mobile: 4,
  desktop: 8,
} as const;

/** Grid padding in pixels based on mobile/desktop */
export const GRID_PADDING = {
  mobile: 16,
  desktop: 32,
} as const;

/** Minimum cell size in pixels based on mobile/desktop */
export const MIN_CELL_SIZE = {
  mobile: 28,
  desktop: 40,
} as const;

/** Mobile breakpoint in pixels */
export const MOBILE_BREAKPOINT = 768;

/**
 * Get the gap size based on mobile state
 */
export function getGridGap(isMobile: boolean): number {
  return isMobile ? GRID_GAP.mobile : GRID_GAP.desktop;
}

/**
 * Get the padding size based on mobile state
 */
export function getGridPadding(isMobile: boolean): number {
  return isMobile ? GRID_PADDING.mobile : GRID_PADDING.desktop;
}

/**
 * Get the minimum cell size based on mobile state
 */
export function getMinCellSize(isMobile: boolean): number {
  return isMobile ? MIN_CELL_SIZE.mobile : MIN_CELL_SIZE.desktop;
}

/**
 * Calculate the total grid width/height
 * Formula: n * cellSize + (n - 1) * gap
 */
export function calculateGridDimension(
  count: number,
  cellSize: number,
  isMobile: boolean,
): number {
  const gap = getGridGap(isMobile);
  return count * cellSize + (count - 1) * gap;
}

/**
 * Calculate the total grid container width including padding
 * Formula: n * cellSize + (n - 1) * gap + 2 * padding
 */
export function calculateGridContainerWidth(
  cols: number,
  cellSize: number,
  isMobile: boolean,
): number {
  const gap = getGridGap(isMobile);
  const padding = getGridPadding(isMobile);
  return cols * cellSize + (cols - 1) * gap + padding;
}

/**
 * Check if viewport is mobile width
 */
export function checkIsMobile(viewportWidth: number): boolean {
  return viewportWidth < MOBILE_BREAKPOINT;
}

/**
 * Calculate optimal cell size to fit grid in available space
 */
export function calculateCellSize(params: {
  containerWidth: number;
  availableHeight: number;
  cols: number;
  rows: number;
  isMobile: boolean;
  minCellSize?: number;
}): number {
  const {
    containerWidth,
    availableHeight,
    cols,
    rows,
    isMobile,
    minCellSize: customMinSize,
  } = params;

  const gap = getGridGap(isMobile);
  const minSize = customMinSize ?? getMinCellSize(isMobile);

  const totalGapX = gap * (cols - 1);
  const totalGapY = gap * (rows - 1);

  // Calculate max cell size that fits both dimensions
  const maxCellByWidth = Math.floor((containerWidth - totalGapX) / cols);
  const maxCellByHeight = Math.floor((availableHeight - totalGapY) / rows);

  // Use smaller dimension, with min size constraint
  const calculatedSize = Math.min(maxCellByWidth, maxCellByHeight);
  return Math.max(minSize, calculatedSize);
}
