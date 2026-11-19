import type { DashboardPanelModel, DashboardPanelModelType, PanelLayoutModel } from "@/schemas";

/** Width of the dashboard grid in columns; matches the backend's `GRID_COLUMNS`. */
const GRID_COLUMNS = 12;
/** Largest panel height in grid rows accepted by the backend. */
const MAX_PANEL_HEIGHT = 12;
/** Height of one grid row in px. */
const ROW_HEIGHT_PX = 120;
/** Gap between panels in px (Tailwind `gap-4`). */
const GRID_GAP_PX = 16;

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
export function sortPanels(panels: readonly DashboardPanelModel[]): DashboardPanelModel[] {
  return [...panels].sort((a, b) => a.layout.y - b.layout.y || a.layout.x - b.layout.x || 0);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

/** Clamp a layout into the grid so that `x + w <= 12` and all sizes stay in range. */
function clampLayout(layout: PanelLayoutModel): PanelLayoutModel {
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

/**
 * Push panels down until none overlaps another. The panel named by `pinnedId`
 * keeps its place; every other panel is placed in reading order below the
 * panels it collides with.
 */
export function resolveCollisions(
  panels: readonly DashboardPanelModel[],
  pinnedId?: string,
): DashboardPanelModel[] {
  const pinned = panels.find((panel) => panel.panel_id === pinnedId);
  const placed: DashboardPanelModel[] = pinned ? [pinned] : [];
  const rest = sortPanels(panels.filter((panel) => panel !== pinned));
  for (const panel of rest) {
    let layout = { ...panel.layout };
    let blocker = placed.find((other) => overlaps(layout, other.layout));
    while (blocker) {
      layout = { ...layout, y: blocker.layout.y + blocker.layout.h };
      blocker = placed.find((other) => overlaps(layout, other.layout));
    }
    placed.push(layout.y === panel.layout.y ? panel : { ...panel, layout });
  }
  // Keep the caller's order so React keys and the editor list stay stable.
  const byId = new Map(placed.map((panel) => [panel.panel_id, panel]));
  return panels.map((panel) => byId.get(panel.panel_id) ?? panel);
}

/** Default size of a new panel of `type`. */
function defaultPanelSize(type: DashboardPanelModelType): { w: number; h: number } {
  switch (type) {
    case "collision_check":
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
