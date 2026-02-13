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

/**
 * Get adaptive minimum cell size based on grid dimensions.
 * Larger grids (e.g., 144Q = 12x12) get smaller minimum cell sizes
 * to ensure the grid fits on screen while remaining readable.
 */
export function getAdaptiveMinCellSize(
  gridSize: number,
  isMobile: boolean,
  viewportHeight?: number,
): number {
  const baseMin = getMinCellSize(isMobile, viewportHeight);

  // For grids larger than 8x8, progressively reduce minimum cell size
  if (gridSize <= 8) {
    return baseMin;
  } else if (gridSize <= 10) {
    // 64-100Q: reduce by 20%
    return Math.max(24, Math.floor(baseMin * 0.8));
  } else if (gridSize <= 12) {
    // 100-144Q: reduce by 35%
    return Math.max(20, Math.floor(baseMin * 0.65));
  } else {
    // >144Q: reduce by 50%
    return Math.max(16, Math.floor(baseMin * 0.5));
  }
}

/** Mobile breakpoint in pixels */
export const MOBILE_BREAKPOINT = 768;

/** Viewport height breakpoints for responsive grid adaptation */
export const VIEWPORT_HEIGHT_BREAKPOINTS = {
  /** Small: zoom-in / very compact displays */
  SMALL: 700,
  /** Medium: 14" displays with 125% scaling (~864px) */
  MEDIUM: 900,
} as const;

/** Responsive grid configs per viewport height tier */
const RESPONSIVE_CONFIGS = {
  SMALL: { gap: 4, padding: 16, minCellSize: 28 },
  MEDIUM: { gap: 6, padding: 20, minCellSize: 32 },
  LARGE: { gap: 8, padding: 32, minCellSize: 40 },
} as const;

/**
 * Get responsive grid constants based on viewport height.
 * Adapts gap, padding, and minCellSize for smaller viewports
 * (e.g. 14" displays with 125% scaling → ~864px effective height).
 */
export function getResponsiveGridConstants(viewportHeight: number): {
  gap: number;
  padding: number;
  minCellSize: number;
} {
  if (viewportHeight < VIEWPORT_HEIGHT_BREAKPOINTS.SMALL) {
    return RESPONSIVE_CONFIGS.SMALL;
  }
  if (viewportHeight < VIEWPORT_HEIGHT_BREAKPOINTS.MEDIUM) {
    return RESPONSIVE_CONFIGS.MEDIUM;
  }
  return RESPONSIVE_CONFIGS.LARGE;
}

/**
 * Get the gap size based on mobile state and optional viewport height
 */
export function getGridGap(isMobile: boolean, viewportHeight?: number): number {
  if (isMobile) return GRID_GAP.mobile;
  if (viewportHeight !== undefined) {
    return getResponsiveGridConstants(viewportHeight).gap;
  }
  return GRID_GAP.desktop;
}

/**
 * Get the padding size based on mobile state and optional viewport height
 */
export function getGridPadding(
  isMobile: boolean,
  viewportHeight?: number,
): number {
  if (isMobile) return GRID_PADDING.mobile;
  if (viewportHeight !== undefined) {
    return getResponsiveGridConstants(viewportHeight).padding;
  }
  return GRID_PADDING.desktop;
}

/**
 * Get the minimum cell size based on mobile state and optional viewport height
 */
export function getMinCellSize(
  isMobile: boolean,
  viewportHeight?: number,
): number {
  if (isMobile) return MIN_CELL_SIZE.mobile;
  if (viewportHeight !== undefined) {
    return getResponsiveGridConstants(viewportHeight).minCellSize;
  }
  return MIN_CELL_SIZE.desktop;
}

/**
 * Calculate the total grid width/height
 * Formula: n * cellSize + (n - 1) * gap
 */
export function calculateGridDimension(
  count: number,
  cellSize: number,
  isMobile: boolean,
  viewportHeight?: number,
): number {
  const gap = getGridGap(isMobile, viewportHeight);
  return count * cellSize + (count - 1) * gap;
}

/**
 * Calculate the total grid container width including padding (both sides).
 * Formula: n * cellSize + (n - 1) * gap + padding
 * Note: padding here is the full padding value; callers typically apply padding/2 per side.
 */
export function calculateGridContainerWidth(
  cols: number,
  cellSize: number,
  isMobile: boolean,
  viewportHeight?: number,
): number {
  const gap = getGridGap(isMobile, viewportHeight);
  const padding = getGridPadding(isMobile, viewportHeight);
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
  viewportHeight?: number;
  minCellSize?: number;
}): number {
  const {
    containerWidth,
    availableHeight,
    cols,
    rows,
    isMobile,
    viewportHeight,
    minCellSize: customMinSize,
  } = params;

  const gap = getGridGap(isMobile, viewportHeight);
  const minSize = customMinSize ?? getMinCellSize(isMobile, viewportHeight);

  const totalGapX = gap * (cols - 1);
  const totalGapY = gap * (rows - 1);

  // Calculate max cell size that fits both dimensions
  const maxCellByWidth = Math.floor((containerWidth - totalGapX) / cols);
  const maxCellByHeight = Math.floor((availableHeight - totalGapY) / rows);

  // Use smaller dimension, with min size constraint
  const calculatedSize = Math.min(maxCellByWidth, maxCellByHeight);
  return Math.max(minSize, calculatedSize);
}
