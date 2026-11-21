"use client";

import { type ReactNode, useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";

import {
  type Compactor,
  type EventCallback,
  GridLayout,
  type Layout,
  type LayoutItem,
} from "react-grid-layout";

import type { DashboardPanelResponse, PanelLayoutModel } from "@/schemas";

import {
  DRAG_GRIP_CLASS,
  DRAG_HANDLE_CLASS,
  GRID_COLUMNS,
  GRID_GAP_PX,
  MAX_PANEL_HEIGHT,
  panelHeightPx,
  ROW_HEIGHT_PX,
  sameLayout,
  settlePlacements,
} from "./layout";

/** Content width in px below which panels stack full width in reading order. */
const STACK_BELOW_PX = 640;

/**
 * Controls inside a header that never start a drag. Plotly is listed too, so a chart's own
 * zoom, pan and selection keep working should a chart ever sit inside the handle.
 */
const DRAG_CANCEL = [
  `button:not(.${DRAG_GRIP_CLASS})`,
  "a",
  "input",
  "textarea",
  "select",
  "[role='menu']",
  "[role='menuitem']",
  "[contenteditable='true']",
  ".js-plotly-plot",
].join(", ");

// Stable configuration objects: the grid memoizes on their identity.
const GRID_CONFIG = {
  cols: GRID_COLUMNS,
  rowHeight: ROW_HEIGHT_PX,
  margin: [GRID_GAP_PX, GRID_GAP_PX] as [number, number],
  containerPadding: [0, 0] as [number, number],
};
const DRAG_ON = { enabled: true, handle: `.${DRAG_HANDLE_CLASS}`, cancel: DRAG_CANCEL };
const DRAG_OFF = { enabled: false };
const RESIZE_ON = { enabled: true, handles: ["sw", "se"] as ("sw" | "se")[] };
const RESIZE_OFF = { enabled: false, handles: [] };

type GridMode = "grid" | "stack";

function toLayout(item: LayoutItem): PanelLayoutModel {
  return { x: item.x, y: item.y, w: item.w, h: item.h };
}

/**
 * Width of the element the grid lives in, which follows the page content rather than the
 * viewport, so opening or resizing the Agent sidebar re-lays the panels. `null` until the
 * first measurement, which happens before the browser paints.
 */
function useContentWidth() {
  const [element, ref] = useState<HTMLDivElement | null>(null);
  const [width, setWidth] = useState<number | null>(null);

  useLayoutEffect(() => {
    if (!element) return;
    const measure = (next: number) => setWidth(Math.floor(next));
    measure(element.getBoundingClientRect().width);
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) measure(rect.width);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);

  return { ref, width };
}

interface DashboardGridProps<P extends DashboardPanelResponse> {
  /** Panels in reading order, which is also the DOM and tab order. */
  panels: readonly P[];
  /** Whether panels can be dragged and resized; only the owner's edit mode passes `true`. */
  editable: boolean;
  /** One panel's card; `dragEnabled` says whether its header acts as the drag handle. */
  renderPanel: (panel: P, dragEnabled: boolean) => ReactNode;
  /**
   * Called once when a drag or resize ends on a different cell, with the panel's new layout.
   * The caller resolves collisions the same way the live preview did; nothing else in the
   * grid, such as a mount, a width change or a stacked layout, reports a layout.
   */
  onLayoutCommit?: (panelId: string, layout: PanelLayoutModel) => void;
  "data-testid"?: string;
}

/**
 * The 12-column dashboard grid. At a content width of `STACK_BELOW_PX` and above, panels sit
 * at their stored cells through react-grid-layout; in edit mode their headers drag and their
 * bottom corners resize. Narrower, panels stack full width in reading order and nothing can
 * be dragged, so a phone or a squeezed window never rewrites the stored desktop layout.
 *
 * The stored layout is the only state: the grid shows `panels`, and a finished drag or resize
 * is reported through `onLayoutCommit` and comes back as new `panels`. Panels are never
 * compacted or rearranged on load; during a drag, panels that the moved one would cover are
 * pushed down from where they were when the drag started, in reading order.
 */
export function DashboardGrid<P extends DashboardPanelResponse>({
  panels,
  editable,
  renderPanel,
  onLayoutCommit,
  "data-testid": testId,
}: DashboardGridProps<P>) {
  const { ref, width } = useContentWidth();
  const mode: GridMode | null = width === null ? null : width >= STACK_BELOW_PX ? "grid" : "stack";
  const interactive = editable && mode === "grid";

  // The layout as it was when the current drag or resize started, and which panel moves.
  const activeRef = useRef<{ id: string; start: Layout } | null>(null);
  const commitRef = useRef(onLayoutCommit);
  useLayoutEffect(() => {
    commitRef.current = onLayoutCommit;
  });

  // Overlap is allowed so the library never pushes panels by itself; this compactor does it,
  // deterministically, from the drag's starting layout. Outside a drag it changes nothing.
  const compactor = useMemo<Compactor>(
    () => ({
      type: null,
      allowOverlap: true,
      compact(layout) {
        const active = activeRef.current;
        if (!active) return layout.map((item) => ({ ...item }));
        const start = new Map(active.start.map((item) => [item.i, item]));
        const settled = settlePlacements(
          layout.map((item) => ({
            id: item.i,
            layout: toLayout(item.i === active.id ? item : (start.get(item.i) ?? item)),
          })),
          active.id,
        );
        return layout.map((item, index) => ({ ...item, ...settled[index]?.layout }));
      },
    }),
    [],
  );

  const layout = useMemo<LayoutItem[]>(
    () =>
      panels.map((panel) => ({
        i: panel.panel_id,
        x: panel.layout.x,
        y: panel.layout.y,
        w: panel.layout.w,
        h: panel.layout.h,
        minW: 1,
        minH: 1,
        maxW: GRID_COLUMNS,
        maxH: MAX_PANEL_HEIGHT,
      })),
    [panels],
  );

  const handleStart = useCallback<EventCallback>((current, item) => {
    if (!item) return;
    activeRef.current = { id: item.i, start: current.map((entry) => ({ ...entry })) };
  }, []);

  const handleStop = useCallback<EventCallback>((current, _before, item) => {
    const active = activeRef.current;
    activeRef.current = null;
    if (!active || !item) return;
    const moved = current.find((entry) => entry.i === active.id) ?? item;
    const before = active.start.find((entry) => entry.i === active.id);
    const next = toLayout(moved);
    // A drop on the cell it started from is not an edit.
    if (before && sameLayout(next, toLayout(before))) return;
    commitRef.current?.(active.id, next);
  }, []);

  return (
    <div ref={ref} className="min-w-0" data-testid={testId} data-layout-mode={mode ?? undefined}>
      {mode === "grid" && width !== null && (
        <GridLayout
          className="dashboard-grid-layout"
          width={width}
          layout={layout}
          gridConfig={GRID_CONFIG}
          dragConfig={interactive ? DRAG_ON : DRAG_OFF}
          resizeConfig={interactive ? RESIZE_ON : RESIZE_OFF}
          compactor={compactor}
          onDragStart={handleStart}
          onDragStop={handleStop}
          onResizeStart={handleStart}
          onResizeStop={handleStop}
        >
          {panels.map((panel) => (
            <div key={panel.panel_id} data-editable={interactive || undefined}>
              {renderPanel(panel, interactive)}
            </div>
          ))}
        </GridLayout>
      )}
      {mode === "stack" && editable && (
        <p className="mb-2 text-xs text-base-content/60">
          Panels stack in a narrow view. Widen it to drag and resize them, or use each panel's menu;
          the stored layout does not change until you do.
        </p>
      )}
      {mode === "stack" && (
        <div className="flex flex-col gap-4">
          {panels.map((panel) => (
            <div key={panel.panel_id} style={{ height: panelHeightPx(panel.layout.h) }}>
              {renderPanel(panel, false)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
