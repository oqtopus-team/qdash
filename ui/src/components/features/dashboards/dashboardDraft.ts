import type { DashboardPanelModel, DashboardPanelResponse } from "@/schemas";

/**
 * A dashboard's unsaved draft as the Agent reads and proposes it: JSON with the
 * panels, and for a new dashboard that is not created yet also its name, description,
 * default chip and starter template. The page owns the draft; a proposal only replaces it
 * once the user applies it, and only the page's Save writes it to QDash. Visibility is never
 * part of a draft, so sharing stays an explicit action.
 */

/** Route of a dashboard that exists only as a draft. */
export const NEW_DASHBOARD_PATH = "/dashboards/new";

/** Backend limit on panels per dashboard. */
export const MAX_PANELS = 50;

const PANEL_TYPES = ["qubit_metric", "coupling_metric", "metric_script", "markdown"] as const;

/** What a new dashboard's draft holds besides its panels. */
export interface NewDashboardMeta {
  name: string;
  description: string;
  chip_id: string | null;
  /** Starter template whose panels QDash copies in on creation, when the draft has none. */
  template_id: string | null;
}

export const EMPTY_NEW_DASHBOARD: NewDashboardMeta = {
  name: "",
  description: "",
  chip_id: null,
  template_id: null,
};

/** Starter requests the empty Agent chat offers on a dashboard; picking one sends it. */
export function dashboardSuggestions(isNew: boolean, empty: boolean): string[] {
  if (isNew || empty) {
    return [
      "Build a frequency collision map from the starter template",
      "Show the median ZX90 fidelity per coupling over the last 14 days",
      "Chart the daily median ZX90 fidelity of Q0→Q1 over the last 4 weeks",
      "Show T1 and T2 echo per qubit side by side",
    ];
  }
  return [
    "Add a note panel that explains how to read this dashboard",
    "Arrange the panels so the maps sit side by side",
  ];
}

/** A panel as the API stores it, in a fixed key order so diffs show only real changes. */
export function toPanelModel(
  panel: DashboardPanelResponse | DashboardPanelModel,
): DashboardPanelModel {
  return {
    panel_id: panel.panel_id,
    type: panel.type,
    title: panel.title ?? "",
    layout: { x: panel.layout.x, y: panel.layout.y, w: panel.layout.w, h: panel.layout.h },
    config: panel.config ?? {},
  };
}

/** The draft as the Agent sees it. */
export function serializeDashboardDraft(
  panels: readonly (DashboardPanelResponse | DashboardPanelModel)[],
  meta: NewDashboardMeta | null,
): string {
  const body = meta
    ? {
        name: meta.name,
        description: meta.description,
        chip_id: meta.chip_id,
        template_id: meta.template_id,
        panels: panels.map(toPanelModel),
      }
    : { panels: panels.map(toPanelModel) };
  return `${JSON.stringify(body, null, 2)}\n`;
}

export type ParsedDashboardDraft =
  | { ok: true; panels: DashboardPanelResponse[]; meta: NewDashboardMeta | null }
  | { ok: false; problem: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

/**
 * A proposed draft as panels the page can show, or why it cannot be applied. Checks the
 * shape only; QDash checks scripts, revisions and metrics when the user saves. Panels that
 * keep their ID and script keep the script annotations of the current draft, so the "newer
 * revision" hint stays.
 */
export function parseDashboardDraft(
  code: string,
  isNew: boolean,
  current: readonly DashboardPanelResponse[],
): ParsedDashboardDraft {
  let value: unknown;
  try {
    value = JSON.parse(code);
  } catch {
    return { ok: false, problem: "The proposed draft is not valid JSON" };
  }
  if (!isRecord(value)) return { ok: false, problem: "The proposed draft is not a JSON object" };
  const allowed = isNew ? ["name", "description", "chip_id", "template_id", "panels"] : ["panels"];
  const unknown = Object.keys(value).find((key) => !allowed.includes(key));
  if (unknown) {
    return {
      ok: false,
      problem:
        unknown === "visibility"
          ? "The proposed draft changes sharing; share the dashboard yourself from its actions"
          : `The proposed draft has an unknown field "${unknown}"`,
    };
  }
  // A missing list is refused rather than read as "no panels", which would drop every panel.
  if (!("panels" in value)) {
    return { ok: false, problem: "The proposed draft has no panels list" };
  }
  const rawPanels = value.panels;
  if (!Array.isArray(rawPanels))
    return { ok: false, problem: "The proposed panels are not a list" };
  if (rawPanels.length > MAX_PANELS) {
    return { ok: false, problem: `A dashboard holds at most ${MAX_PANELS} panels` };
  }
  const known = new Map(current.map((panel) => [panel.panel_id, panel]));
  const ids = new Set<string>();
  const panels: DashboardPanelResponse[] = [];
  for (const [index, raw] of rawPanels.entries()) {
    const where = `Panel ${index + 1}`;
    if (!isRecord(raw)) return { ok: false, problem: `${where} is not an object` };
    const { panel_id: id, type, title, layout, config } = raw;
    if (typeof id !== "string" || !id || id.length > 64 || ids.has(id)) {
      return { ok: false, problem: `${where} needs a unique ID` };
    }
    ids.add(id);
    if (!PANEL_TYPES.includes(type as (typeof PANEL_TYPES)[number])) {
      return { ok: false, problem: `${where} has an unknown type` };
    }
    if (
      !isRecord(layout) ||
      !isInt(layout.x) ||
      !isInt(layout.y) ||
      !isInt(layout.w) ||
      !isInt(layout.h) ||
      layout.x < 0 ||
      layout.y < 0 ||
      layout.w < 1 ||
      layout.h < 1 ||
      layout.h > 12 ||
      layout.x + layout.w > 12
    ) {
      return { ok: false, problem: `${where} does not fit the 12-column grid` };
    }
    if (config !== undefined && !isRecord(config)) {
      return { ok: false, problem: `${where} has an invalid config` };
    }
    const panel: DashboardPanelResponse = {
      panel_id: id,
      type: type as DashboardPanelResponse["type"],
      title: typeof title === "string" ? title : "",
      layout: { x: layout.x, y: layout.y, w: layout.w, h: layout.h },
      config: config ?? {},
    };
    const before = known.get(id);
    if (
      before &&
      before.type === panel.type &&
      before.config?.script_id === panel.config?.script_id
    ) {
      if (before.script_name !== undefined) panel.script_name = before.script_name;
      if (before.latest_revision !== undefined) panel.latest_revision = before.latest_revision;
    }
    panels.push(panel);
  }
  if (!isNew) return { ok: true, panels, meta: null };
  const text = (key: string) => (typeof value[key] === "string" ? (value[key] as string) : "");
  const optional = (key: string) => {
    const entry = value[key];
    return typeof entry === "string" && entry.trim() ? entry.trim() : null;
  };
  return {
    ok: true,
    panels,
    meta: {
      name: text("name").slice(0, 200),
      description: text("description").slice(0, 2000),
      chip_id: optional("chip_id"),
      template_id: optional("template_id"),
    },
  };
}
