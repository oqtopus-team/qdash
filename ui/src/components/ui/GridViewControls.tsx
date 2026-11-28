"use client";

import type { CSSProperties, HTMLAttributes, ReactNode, Ref } from "react";

import { Lock, ZoomIn } from "lucide-react";
import {
  TransformComponent,
  TransformWrapper,
  type ReactZoomPanPinchProps,
} from "react-zoom-pan-pinch";

import { GridFullscreenButton } from "@/components/ui/GridFullscreenButton";
import { GridZoomControls } from "@/components/ui/GridZoomControls";
import { LockedGridScroller } from "@/components/ui/LockedGridScroller";
import { ViewSwitch, type ViewSwitchItem } from "@/components/ui/ViewSwitch";
import type { GridRegion, GridViewMode } from "@/hooks/useGridViewState";

const GRID_VIEW_ITEMS: readonly ViewSwitchItem<GridViewMode>[] = [
  {
    value: "pan-zoom",
    label: <span className="hidden sm:inline">Zoom</span>,
    icon: <ZoomIn aria-hidden="true" />,
    ariaLabel: "Zoom",
    title: "Zoom",
  },
  {
    value: "region",
    label: <span className="hidden sm:inline">Lock</span>,
    icon: <Lock aria-hidden="true" />,
    ariaLabel: "Lock",
    title: "Lock",
  },
];

interface GridViewModeSwitchProps {
  value: GridViewMode;
  onValueChange: (mode: GridViewMode) => void;
}

/** Zoom/Lock switch of a qubit or coupling grid. */
export function GridViewModeSwitch({ value, onValueChange }: GridViewModeSwitchProps) {
  return (
    <ViewSwitch
      ariaLabel="Grid view"
      size="sm"
      value={value}
      onValueChange={onValueChange}
      items={GRID_VIEW_ITEMS}
    />
  );
}

interface GridRegionButtonProps {
  region: GridRegion;
  isHovered: boolean;
  /** Positioning classes, which differ between grid-placed and absolute overlays. */
  className: string;
  /** Classes applied only while hovered, such as a raised z-index. */
  hoveredClassName?: string;
  style: CSSProperties;
  onHoverChange: (region: GridRegion | null) => void;
  onSelect: (region: GridRegion) => void;
}

/** One selectable region in the overlay that zooms a locked grid into a region. */
function GridRegionButton({
  region,
  isHovered,
  className,
  hoveredClassName = "",
  style,
  onHoverChange,
  onSelect,
}: GridRegionButtonProps) {
  return (
    <button
      className={`${className} transition-colors duration-200 rounded-lg flex items-center justify-center ${
        isHovered
          ? `bg-primary/30 border-2 border-primary ${hoveredClassName}`.trimEnd()
          : "bg-primary/5 border-2 border-primary/20 hover:border-primary/40 hover:bg-primary/10"
      }`}
      style={style}
      onMouseEnter={() => onHoverChange(region)}
      onMouseLeave={() => onHoverChange(null)}
      onClick={() => onSelect(region)}
      title={`Zoom to region (${region.row + 1}, ${region.col + 1})`}
    >
      <span className="text-xs font-medium text-white bg-black/50 px-2 py-1 rounded">
        {region.row},{region.col}
      </span>
    </button>
  );
}

interface GridRegionOverlayProps {
  /** Regions per side of the square grid. */
  numRegions: number;
  /** Cells per side of one region. */
  regionSize: number;
  hoveredRegion: GridRegion | null;
  onHoverChange: (region: GridRegion | null) => void;
  onSelect: (region: GridRegion) => void;
}

function regionsOf(numRegions: number): GridRegion[] {
  return Array.from({ length: numRegions * numRegions }, (_, index) => ({
    row: Math.floor(index / numRegions),
    col: index % numRegions,
  }));
}

function isSameRegion(a: GridRegion | null, b: GridRegion): boolean {
  return a?.row === b.row && a?.col === b.col;
}

interface GridTemplateRegionOverlayProps extends GridRegionOverlayProps {
  /** Grid padding from `useGridLayout`; the overlay insets by half of it, like the grid. */
  padding: number;
  gap: number;
  cols: number;
  rows: number;
  cellSize: number;
}

/** Region-zoom overlay laid on a CSS grid of cells, placing each region on grid lines. */
export function GridTemplateRegionOverlay({
  numRegions,
  regionSize,
  hoveredRegion,
  onHoverChange,
  onSelect,
  padding,
  gap,
  cols,
  rows,
  cellSize,
}: GridTemplateRegionOverlayProps) {
  return (
    <div
      className="absolute inset-0 pointer-events-none z-20"
      style={{ padding: `${padding / 2}px` }}
    >
      <div
        className="grid w-full h-full"
        style={{
          gap: `${gap}px`,
          gridTemplateColumns: `repeat(${cols}, minmax(${cellSize}px, 1fr))`,
          gridTemplateRows: `repeat(${rows}, minmax(${cellSize}px, 1fr))`,
        }}
      >
        {regionsOf(numRegions).map((region, index) => (
          <GridRegionButton
            key={index}
            region={region}
            isHovered={isSameRegion(hoveredRegion, region)}
            className="pointer-events-auto"
            hoveredClassName="z-10"
            style={{
              gridColumn: `${region.col * regionSize + 1} / span ${regionSize}`,
              gridRow: `${region.row * regionSize + 1} / span ${regionSize}`,
            }}
            onHoverChange={onHoverChange}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}

interface PositionedRegionOverlayProps extends GridRegionOverlayProps {
  cellSize: number;
  gap: number;
}

/** Region-zoom overlay of absolutely positioned regions over a pixel-positioned grid. */
export function PositionedRegionOverlay({
  numRegions,
  regionSize,
  hoveredRegion,
  onHoverChange,
  onSelect,
  cellSize,
  gap,
}: PositionedRegionOverlayProps) {
  const pitch = regionSize * (cellSize + gap);
  return (
    <>
      {regionsOf(numRegions).map((region, index) => (
        <GridRegionButton
          key={index}
          region={region}
          isHovered={isSameRegion(hoveredRegion, region)}
          className="absolute z-20"
          style={{
            top: region.row * pitch,
            left: region.col * pitch,
            width: pitch - gap,
            height: pitch - gap,
          }}
          onHoverChange={onHoverChange}
          onSelect={onSelect}
        />
      ))}
    </>
  );
}

interface GridRegionBackBarProps {
  region: GridRegion;
  onBack: () => void;
  /** Extra description after the region number, such as the qubit range. */
  detail?: ReactNode;
  className?: string;
}

/** Return-to-full-view bar shown while a locked grid is zoomed into a region. */
export function GridRegionBackBar({ region, onBack, detail, className }: GridRegionBackBarProps) {
  return (
    <div className={className ? `flex items-center gap-4 ${className}` : "flex items-center gap-4"}>
      <button onClick={onBack} className="btn btn-sm btn-ghost">
        ← Back to Full View
      </button>
      <span className="text-sm text-base-content/70">
        Region {region.row + 1},{region.col + 1}
        {detail}
      </span>
    </div>
  );
}

interface GridViewportProps {
  viewMode: GridViewMode;
  /** Grid padding from `useGridLayout`; the viewport pads by a quarter of it. */
  padding: number;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
  onTransform: ReactZoomPanPinchProps["onTransform"];
  /** Capture handlers from `usePanClickGuard`. */
  panClickGuard: HTMLAttributes<HTMLDivElement>;
  /** Measured container from `useGridLayout`, when the viewport is the measured element. */
  viewportRef?: Ref<HTMLDivElement>;
  /** Extra classes for the pan-and-zoom surface. */
  panZoomClassName?: string;
  children: ReactNode;
}

/**
 * Grid surface with the fullscreen button: pan and zoom in the Zoom view, and a scroller
 * that keeps the default cell size in the Lock view.
 */
export function GridViewport({
  viewMode,
  padding,
  isFullscreen,
  onToggleFullscreen,
  onTransform,
  panClickGuard,
  viewportRef,
  panZoomClassName,
  children,
}: GridViewportProps) {
  return (
    <div
      className={`flex-1 relative flex justify-center ${
        viewMode === "pan-zoom"
          ? `${panZoomClassName ?? ""} bg-base-200/30 border-2 border-dashed border-base-300 rounded-lg`
          : "items-start overflow-hidden bg-base-200/60 rounded-lg"
      }`}
      style={{ padding: `${Math.max(4, padding / 4)}px` }}
      ref={viewportRef}
    >
      <GridFullscreenButton isFullscreen={isFullscreen} onToggle={onToggleFullscreen} />
      {viewMode === "pan-zoom" ? (
        <TransformWrapper
          initialScale={1}
          minScale={0.3}
          maxScale={4}
          wheel={{ step: 0.08 }}
          pinch={{ step: 5 }}
          doubleClick={{ mode: "zoomIn", step: 0.7 }}
          panning={{ velocityDisabled: true }}
          smooth={false}
          limitToBounds={false}
          centerOnInit={true}
          onTransform={onTransform}
        >
          <GridZoomControls isFullscreen={isFullscreen} className="top-12" />
          <TransformComponent
            contentProps={panClickGuard}
            wrapperStyle={{ width: "100%", height: "100%" }}
            contentStyle={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
            }}
          >
            {children}
          </TransformComponent>
        </TransformWrapper>
      ) : (
        <LockedGridScroller>{children}</LockedGridScroller>
      )}
    </div>
  );
}
