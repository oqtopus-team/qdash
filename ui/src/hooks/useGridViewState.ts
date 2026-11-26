"use client";

import { useCallback, useEffect, useState } from "react";

/** `pan-zoom` renders the grid with pan and zoom; `region` locks it at its cell size. */
export type GridViewMode = "pan-zoom" | "region";

/** Row and column of a square region of the grid, in region units. */
export interface GridRegion {
  row: number;
  col: number;
}

/**
 * View state shared by the chip and metrics grids: the Zoom/Lock view mode and, in the
 * locked view, the optional zoom into one square region.
 *
 * Region zoom assumes a square grid, so a non-square grid leaves it.
 */
export function useGridViewState(isSquareGrid: boolean) {
  const [viewMode, setViewMode] = useState<GridViewMode>("pan-zoom");
  const [regionSelectionEnabled, setRegionSelectionEnabled] = useState(false);
  const [zoomMode, setZoomMode] = useState<"full" | "region">("full");
  const [selectedRegion, setSelectedRegion] = useState<GridRegion | null>(null);
  const [hoveredRegion, setHoveredRegion] = useState<GridRegion | null>(null);

  // Lock works for every topology, but region zoom assumes a square grid; leave it when the
  // grid is not square.
  useEffect(() => {
    if (!isSquareGrid) {
      setZoomMode("full");
      setSelectedRegion(null);
      setRegionSelectionEnabled(false);
    }
  }, [isSquareGrid]);

  const changeViewMode = useCallback((mode: GridViewMode) => {
    setViewMode(mode);
    if (mode === "pan-zoom") {
      setZoomMode("full");
      setSelectedRegion(null);
      setRegionSelectionEnabled(false);
    }
  }, []);

  const zoomToRegion = useCallback((region: GridRegion) => {
    setSelectedRegion(region);
    setZoomMode("region");
  }, []);

  const showFullGrid = useCallback(() => {
    setZoomMode("full");
    setSelectedRegion(null);
  }, []);

  return {
    viewMode,
    changeViewMode,
    zoomMode,
    selectedRegion,
    zoomToRegion,
    showFullGrid,
    hoveredRegion,
    setHoveredRegion,
    regionSelectionEnabled,
    setRegionSelectionEnabled,
  };
}
