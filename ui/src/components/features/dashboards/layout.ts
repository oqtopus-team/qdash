import type { DashboardPanelModel, DashboardPanelModelType, PanelLayoutModel } from "@/schemas";

/** Width of the dashboard grid in columns; matches the backend's `GRID_COLUMNS`. */
export const GRID_COLUMNS = 12;
/** Largest panel height in grid rows accepted by the backend. */
export const MAX_PANEL_HEIGHT = 12;
/** Height of one grid row in px. */
export const ROW_HEIGHT_PX = 120;
/** Gap between panels in px (Tailwind `gap-4`). */
export const GRID_GAP_PX = 16;

/** Class of the panel header region that starts a drag in edit mode. */
export const DRAG_HANDLE_CLASS = "dashboard-drag-handle";
/** Class of the focusable grip inside the handle; it moves and resizes from the keyboard. */
export const DRAG_GRIP_CLASS = "dashboard-drag-grip";

export type LayoutAction =
  | "left"
  | "right"
  | "up"
  | "down"
  | "wider"
  | "narrower"
  | "taller"
  | "shorter";

/** Panels in reading order: top to bottom, then left to right. */
export function sortPanels<T extends DashboardPanelModel>(panels: readonly T[]): T[] {
  return [...panels].sort((a, b) => a.layout.y - b.layout.y || a.layout.x - b.layout.x || 0);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

/** Clamp a layout into the grid so that `x + w <= 12` and all sizes stay in range. */
export function clampLayout(layout: PanelLayoutModel): PanelLayoutModel {
  const w = clamp(Math.round(layout.w), 1, GRID_COLUMNS);
  const h = clamp(Math.round(layout.h), 1, MAX_PANEL_HEIGHT);
  const x = clamp(Math.round(layout.x), 0, GRID_COLUMNS - w);
  const y = Math.max(0, Math.round(layout.y));
  return { x, y, w, h };
}

/** Apply one step of a move or resize to a layout. */
export function applyLayoutAction(
  layout: PanelLayoutModel,
  action: LayoutAction,
): PanelLayoutModel {
  const { x, y, w, h } = layout;
  switch (action) {
    case "left":
      return clampLayout({ x: x - 1, y, w, h });
    case "right":
      return clampLayout({ x: x + 1, y, w, h });
    case "up":
      return clampLayout({ x, y: y - 1, w, h });
    case "down":
      return clampLayout({ x, y: y + 1, w, h });
    case "wider":
      // Grow to the right, or to the left when the panel touches the right edge.
      if (x + w < GRID_COLUMNS) return clampLayout({ x, y, w: w + 1, h });
      return clampLayout({ x: x - 1, y, w: w + 1, h });
    case "narrower":
      return clampLayout({ x, y, w: w - 1, h });
    case "taller":
      return clampLayout({ x, y, w, h: h + 1 });
    case "shorter":
      return clampLayout({ x, y, w, h: h - 1 });
  }
}

/** Whether an action would change the layout at all, for disabling menu items. */
export function canApplyLayoutAction(layout: PanelLayoutModel, action: LayoutAction): boolean {
  const next = applyLayoutAction(layout, action);
  return next.x !== layout.x || next.y !== layout.y || next.w !== layout.w || next.h !== layout.h;
}

function overlaps(a: PanelLayoutModel, b: PanelLayoutModel): boolean {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

/** Whether two layouts are the same cell rectangle. */
export function sameLayout(a: PanelLayoutModel, b: PanelLayoutModel): boolean {
  return a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h;
}

/** A layout keyed by the panel it belongs to. */
export interface Placement {
  id: string;
  layout: PanelLayoutModel;
}

/**
 * Push placements down until none overlaps another. The placement named by `pinnedId`
 * keeps its place; every other one is placed in reading order below the placements it
 * collides with. Placements that do not move keep their identity, and the result keeps
 * the input order.
 */
export function settlePlacements<T extends Placement>(items: readonly T[], pinnedId?: string): T[] {
  const pinned = items.find((item) => item.id === pinnedId);
  const placed: T[] = pinned ? [pinned] : [];
  const rest = items
    .filter((item) => item !== pinned)
    .sort((a, b) => a.layout.y - b.layout.y || a.layout.x - b.layout.x || 0);
  for (const item of rest) {
    let layout = { ...item.layout };
    let blocker = placed.find((other) => overlaps(layout, other.layout));
    while (blocker) {
      layout = { ...layout, y: blocker.layout.y + blocker.layout.h };
      blocker = placed.find((other) => overlaps(layout, other.layout));
    }
    placed.push(layout.y === item.layout.y ? item : { ...item, layout });
  }
  const byId = new Map(placed.map((item) => [item.id, item]));
  return items.map((item) => byId.get(item.id) ?? item);
}

/**
 * Push panels down until none overlaps another. The panel named by `pinnedId`
 * keeps its place; every other panel is placed in reading order below the
 * panels it collides with.
 */
export function resolveCollisions<T extends DashboardPanelModel>(
  panels: readonly T[],
  pinnedId?: string,
): T[] {
  const settled = settlePlacements(
    panels.map((panel) => ({ id: panel.panel_id, layout: panel.layout })),
    pinnedId,
  );
  // Keep the caller's order and unmoved panels so React keys and the editor list stay stable.
  return panels.map((panel, index) => {
    const layout = settled[index]?.layout ?? panel.layout;
    return layout === panel.layout ? panel : { ...panel, layout };
  });
}

/** Default size of a new panel of `type`. */
function defaultPanelSize(type: DashboardPanelModelType): { w: number; h: number } {
  switch (type) {
    case "metric_script":
      return { w: 6, h: 4 };
    case "markdown":
      return { w: 12, h: 2 };
    default:
      return { w: 6, h: 3 };
  }
}

/** Layout of a new panel: full left edge, below every existing panel. */
export function nextPanelLayout(
  panels: readonly DashboardPanelModel[],
  type: DashboardPanelModelType,
): PanelLayoutModel {
  const bottom = panels.reduce((max, panel) => Math.max(max, panel.layout.y + panel.layout.h), 0);
  return { x: 0, y: bottom, ...defaultPanelSize(type) };
}

/** Height in px of a panel spanning `h` grid rows, gaps included. */
export function panelHeightPx(h: number): number {
  return h * ROW_HEIGHT_PX + (h - 1) * GRID_GAP_PX;
}
