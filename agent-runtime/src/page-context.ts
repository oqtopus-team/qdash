/**
 * What the user has open in QDash while they chat from the sidebar or the
 * floating window, and the edit tool it enables.
 *
 * The API forwards the page with every turn, so the section below is rebuilt
 * each time: an editor's buffer changes as the user types, and the model must
 * see the current text, saved or not. On the Workflow editor, on the metric
 * script editor and on a custom dashboard the user may edit, the model also
 * gets `propose_code_edit`: it proposes the complete new file (for a
 * dashboard, its draft as JSON), the chat shows a diff, and the user applies it
 * on the page and saves. The runtime never writes the flow, the script or the
 * dashboard itself.
 */
import type { JsonValue } from "@earendil-works/chord/json";
import { defineTool } from "@earendil-works/pi-durable";
import { Type } from "typebox";

export interface FlowEditorContext {
  name: string;
  chipId?: string;
  /** The editor's current text, unsaved changes included. */
  code: string;
  /** The buffer differs from the saved flow. */
  dirty?: boolean;
}

export interface MetricScriptEditorContext {
  scriptId: string;
  name: string;
  /** The editor's current text, unsaved changes included. */
  code: string;
  /** The buffer differs from the saved script. */
  dirty?: boolean;
}

/**
 * The custom dashboard the user may edit, with its unsaved draft. Sent only for a
 * dashboard the user can save: their own, or a new one not created yet.
 */
export interface DashboardEditorContext {
  /** The stored dashboard; absent for a new dashboard that exists only as a draft. */
  dashboardId?: string;
  name: string;
  description?: string;
  /** `private` or `project`; changed only from the dashboard's own sharing action. */
  visibility?: string;
  /** The chip the page shows now. */
  chipId?: string;
  /** The stored version the draft is based on. */
  version?: number;
  /** The draft as JSON: `{"panels": [...]}`, plus name, description, chip_id and template_id when new. */
  code: string;
  /** The draft differs from the saved dashboard. */
  dirty?: boolean;
}

export interface PageContext {
  /** The route, such as `/workflow/t1_check` or `/custom-dashboards/scripts/ms_…`. */
  path: string;
  title?: string;
  flow?: FlowEditorContext;
  metricScript?: MetricScriptEditorContext;
  dashboard?: DashboardEditorContext;
}

/** The editor a page shows, when it shows one the model can propose changes to. */
export type EditorContext =
  | { kind: "flow"; flow: FlowEditorContext }
  | { kind: "metric_script"; script: MetricScriptEditorContext }
  | { kind: "dashboard"; dashboard: DashboardEditorContext };

/** A change the model proposes to the open editor, as the UI receives it. */
export interface EditProposal {
  summary: string;
  code: string;
  /** Which editor the change is for. */
  target: "flow" | "metric_script" | "dashboard";
  /** The flow's name; for a metric script or a dashboard, its name. */
  flowName: string;
  chipId: string | null;
  /** The metric script the change is for (target `metric_script`). */
  scriptId?: string;
  scriptName?: string;
  /** The dashboard the change is for (target `dashboard`); null for a new dashboard. */
  dashboardId?: string | null;
  pagePath: string;
}

export const PAGE_SECTION = "qdash-page";
export const EDIT_TOOL = "propose_code_edit";
/** Longest editor text placed in the prompt; the rest is cut with a note. */
export const MAX_PAGE_CODE_CHARS = 24_000;

function text(value: unknown, max: number): string | undefined {
  return typeof value === "string" && value.trim() ? value.slice(0, max) : undefined;
}

function objectOf(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined;
}

/** The page context of a request body, or `undefined` when it carries none the runtime understands. */
export function parsePageContext(value: unknown): PageContext | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const record = value as Record<string, unknown>;
  const path = text(record.path, 512);
  if (!path) return undefined;
  const title = text(record.title, 200);
  const page: PageContext = { path, ...(title ? { title } : {}) };
  const f = objectOf(record.flow);
  if (f) {
    const name = text(f.name, 200);
    if (name && typeof f.code === "string") {
      page.flow = {
        name,
        code: f.code,
        ...(text(f.chip_id ?? f.chipId, 100) ? { chipId: text(f.chip_id ?? f.chipId, 100) } : {}),
        ...(f.dirty === true ? { dirty: true } : {}),
      };
    }
  }
  const m = objectOf(record.metric_script ?? record.metricScript);
  if (m) {
    const scriptId = text(m.script_id ?? m.scriptId, 64);
    const name = text(m.name, 200);
    if (scriptId && name && typeof m.code === "string") {
      page.metricScript = { scriptId, name, code: m.code, ...(m.dirty === true ? { dirty: true } : {}) };
    }
  }
  const d = objectOf(record.dashboard);
  if (d && typeof d.code === "string") {
    const dashboardId = text(d.dashboard_id ?? d.dashboardId, 64);
    const description = text(d.description, 2000);
    const visibility = text(d.visibility, 20);
    const chipId = text(d.chip_id ?? d.chipId, 100);
    const version = typeof d.version === "number" && Number.isInteger(d.version) ? d.version : undefined;
    page.dashboard = {
      name: text(d.name, 200) ?? "",
      code: d.code,
      ...(dashboardId ? { dashboardId } : {}),
      ...(description ? { description } : {}),
      ...(visibility ? { visibility } : {}),
      ...(chipId ? { chipId } : {}),
      ...(version !== undefined ? { version } : {}),
      ...(d.dirty === true ? { dirty: true } : {}),
    };
  }
  return page;
}

/** The editor the page shows; the Workflow editor wins if a page ever carried more than one. */
export function editorOf(page: PageContext | undefined): EditorContext | undefined {
  if (page?.flow) return { kind: "flow", flow: page.flow };
  if (page?.metricScript) return { kind: "metric_script", script: page.metricScript };
  if (page?.dashboard) return { kind: "dashboard", dashboard: page.dashboard };
  return undefined;
}

export const DASHBOARD_PANEL_TYPES = ["qubit_metric", "coupling_metric", "metric_script", "markdown"] as const;
const MAX_DASHBOARD_PANELS = 50;
const NEW_DASHBOARD_KEYS = ["name", "description", "chip_id", "template_id", "panels"];

function isInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

/**
 * A proposed dashboard draft in the order the page writes it, or the problems that keep it
 * from being one. Checks the shape only; QDash validates scripts, revisions and metrics when
 * the user saves.
 */
export function parseDashboardDraft(
  code: string,
  isNew: boolean,
): { ok: true; code: string } | { ok: false; problems: string[] } {
  let value: unknown;
  try {
    value = JSON.parse(code);
  } catch (error) {
    return { ok: false, problems: [`not valid JSON: ${(error as Error).message}`] };
  }
  const draft = objectOf(value);
  if (!draft) return { ok: false, problems: ["the draft must be a JSON object"] };
  const problems: string[] = [];
  const allowed = isNew ? NEW_DASHBOARD_KEYS : ["panels"];
  for (const key of Object.keys(draft)) {
    if (!allowed.includes(key)) {
      problems.push(
        key === "visibility"
          ? "visibility is not part of a draft: the user shares a dashboard themselves"
          : `unknown key '${key}'; a ${isNew ? "new" : "saved"} dashboard's draft has ${allowed.join(", ")}`,
      );
    }
  }
  const out: Record<string, unknown> = {};
  if (isNew) {
    for (const key of ["name", "description"] as const) {
      if (draft[key] !== undefined && typeof draft[key] !== "string") problems.push(`${key} must be a string`);
    }
    for (const key of ["chip_id", "template_id"] as const) {
      if (draft[key] !== undefined && draft[key] !== null && typeof draft[key] !== "string") {
        problems.push(`${key} must be a string or null`);
      }
    }
    out.name = typeof draft.name === "string" ? draft.name : "";
    out.description = typeof draft.description === "string" ? draft.description : "";
    out.chip_id = typeof draft.chip_id === "string" && draft.chip_id ? draft.chip_id : null;
    out.template_id = typeof draft.template_id === "string" && draft.template_id ? draft.template_id : null;
  }
  const panels = draft.panels;
  if (panels === undefined) {
    // Read as "no panels", a missing list would drop every panel of the draft.
    problems.push("panels is required: send the complete list, or [] for none");
  } else if (!Array.isArray(panels)) {
    problems.push("panels must be a list");
  } else {
    if (panels.length > MAX_DASHBOARD_PANELS) problems.push(`at most ${MAX_DASHBOARD_PANELS} panels`);
    const ids = new Set<string>();
    out.panels = panels.map((raw, index) => {
      const panel = objectOf(raw);
      const where = `panels[${index}]`;
      if (!panel) {
        problems.push(`${where} must be an object`);
        return raw;
      }
      const id = panel.panel_id;
      if (typeof id !== "string" || !id || id.length > 64) problems.push(`${where}.panel_id must be a string of 1 to 64 characters`);
      else if (ids.has(id)) problems.push(`${where}.panel_id '${id}' is used twice`);
      else ids.add(id);
      if (!DASHBOARD_PANEL_TYPES.includes(panel.type as (typeof DASHBOARD_PANEL_TYPES)[number])) {
        problems.push(`${where}.type must be one of ${DASHBOARD_PANEL_TYPES.join(", ")}`);
      }
      if (panel.title !== undefined && typeof panel.title !== "string") problems.push(`${where}.title must be a string`);
      const layout = objectOf(panel.layout);
      if (
        !layout ||
        !isInt(layout.x) || !isInt(layout.y) || !isInt(layout.w) || !isInt(layout.h) ||
        layout.x < 0 || layout.y < 0 || layout.w < 1 || layout.h < 1 || layout.h > 12 || layout.x + layout.w > 12
      ) {
        problems.push(`${where}.layout must be {x, y, w, h} integers on the 12-column grid (x + w <= 12, 1 <= h <= 12)`);
      }
      if (panel.config !== undefined && !objectOf(panel.config)) problems.push(`${where}.config must be an object`);
      return {
        panel_id: id,
        type: panel.type,
        title: typeof panel.title === "string" ? panel.title : "",
        layout: layout ? { x: layout.x, y: layout.y, w: layout.w, h: layout.h } : panel.layout,
        config: objectOf(panel.config) ?? {},
      };
    });
  }
  if (problems.length) return { ok: false, problems };
  return { ok: true, code: `${JSON.stringify(out, null, 2)}\n` };
}

/** The editor text for the prompt, cut at MAX_PAGE_CODE_CHARS. */
function promptCode(code: string, what: string): string {
  const trimmed = code.replace(/\n+$/, "");
  if (trimmed.length <= MAX_PAGE_CODE_CHARS) return trimmed;
  return `${trimmed.slice(0, MAX_PAGE_CODE_CHARS)}\n# … cut: the ${what} is longer than ${MAX_PAGE_CODE_CHARS} characters`;
}

/** The system prompt section describing the page, rebuilt every turn. */
export function buildPageContextSection(page: PageContext | undefined): string | undefined {
  if (!page) return undefined;
  const where = page.title ? `"${page.title}" (${page.path})` : page.path;
  const lines = [`The user is looking at the QDash page ${where} while they talk to you.`];
  const editor = editorOf(page);
  if (editor?.kind === "flow") {
    const { name, chipId, dirty } = editor.flow;
    const code = promptCode(editor.flow.code, "flow");
    // A fence longer than any backtick run in the code, so a docstring's own
    // markdown example cannot close it and turn the rest of the file into prose.
    const fence = codeFence(code);
    lines.push(
      "",
      `They have the flow \`${name}\`${chipId ? ` (chip ${chipId})` : ""} open in the Workflow editor${dirty ? ", with unsaved changes" : ""}. The editor currently holds:`,
      "",
      `${fence}python`,
      code,
      fence,
      "",
      `To change this flow, call \`${EDIT_TOOL}\` with the complete new file and a one-line summary. The user sees a diff in the chat, applies it in the editor themselves, and saves when they are ready; do not save it for them and do not use qdash_save_flow for this flow unless they ask you to save. Answer questions about the code from this text; there is no need to fetch the flow.`,
    );
  } else if (editor?.kind === "metric_script") {
    const { scriptId, name, dirty } = editor.script;
    const code = promptCode(editor.script.code, "script");
    const fence = codeFence(code);
    lines.push(
      "",
      `They have the metric script \`${name}\` (${scriptId}) open in the Metric script editor${dirty ? ", with unsaved changes" : ""}. It is a Python module written against the \`qdash_metrics\` API; consult the qdash-metric-scripts skill for that API and its period, unit and pair semantics. The editor currently holds:`,
      "",
      `${fence}python`,
      code,
      fence,
      "",
      `To check this text, pass it as \`source\` to qdash_validate_metric_script, and to qdash_preview_metric_script on the user's chip and period (load them with tool_search when they are not offered); both run it on the server without saving anything. To change the script, call \`${EDIT_TOOL}\` with the complete new file and a one-line summary. The user sees a diff in the chat, applies it in the editor themselves, and saves when they are ready; do not use qdash_save_metric_script for this script unless they ask you to save, because a save from here would replace their draft. Answer questions about the code from this text; there is no need to fetch the script.`,
    );
  } else if (editor?.kind === "dashboard") {
    lines.push("", ...dashboardSection(editor.dashboard));
  }
  return lines.join("\n");
}

function dashboardSection(dashboard: DashboardEditorContext): string[] {
  const isNew = !dashboard.dashboardId;
  const code = promptCode(dashboard.code, "draft");
  const fence = codeFence(code);
  const facts = [
    dashboard.visibility ? `visibility ${dashboard.visibility}` : null,
    dashboard.version !== undefined ? `draft based on version ${dashboard.version}` : null,
    dashboard.chipId ? `the page shows chip ${dashboard.chipId}` : null,
  ].filter(Boolean);
  const head = isNew
    ? `They are composing a new custom dashboard${dashboard.name ? ` \`${dashboard.name}\`` : ""}. It exists only as a draft in their browser and is created when they press Save${facts.length ? ` (${facts.join(", ")})` : ""}${dashboard.dirty ? "" : "; the draft is still empty"}.`
    : `They have the custom dashboard \`${dashboard.name}\` (${dashboard.dashboardId}) open and may edit it${facts.length ? ` (${facts.join(", ")})` : ""}${dashboard.dirty ? ", with unsaved changes" : ""}.`;
  return [
    head,
    ...(dashboard.description ? [`Its description: ${dashboard.description.slice(0, 500)}`] : []),
    "The draft currently holds:",
    "",
    `${fence}json`,
    code,
    fence,
    "",
    `To change the dashboard, call \`${EDIT_TOOL}\` with the complete new draft as JSON in \`code\` and a one-line summary. The user sees a diff in the chat, applies it to the page's draft, reviews the panels, and saves when they are ready. Do not use qdash_save_custom_dashboard for this dashboard unless they ask you to save, because a save from here would replace their draft; never change its sharing.`,
    isNew
      ? "A new draft holds name, description, chip_id (the default chip, or null for the newest chip), template_id and panels. template_id names a starter template (qdash_query custom_dashboard_templates); its panels are copied in when the dashboard is created, so set panels to [] when you use one; the page then previews the template's panels without creating anything. When the project has no shared script for the template's script panels, Save also adds one, and the page says so before the user saves."
      : "A saved dashboard's draft holds only panels; its name, description and default chip are changed in Dashboard settings.",
    "Each panel is {panel_id, type, title, layout: {x, y, w, h}, config} on a 12-column grid (x + w <= 12, h of 1 to 12 rows of 120 px). Types and their config: qubit_metric and coupling_metric {metric} (a metric key from qdash_get_chip_metrics); markdown {content}; metric_script {script_id, script_revision, metric_id, period, params, view, direction, hops}, where the script and its metric come from qdash_query metric_scripts and metric_script, and period is {kind: \"relative\", days} or {kind: \"absolute\", start, end} with timezones. Keep the panel_id and the pinned script_revision of every panel you do not mean to change; move a pin only when the user asks. A metric_script panel needs a saved script: when none computes what the user wants, write it and save it with qdash_save_metric_script, which asks the user to confirm, before you propose a panel for it; a draft never creates a script, apart from a starter template's shared script on Save. QDash checks scripts, revisions and metrics when the user saves, and a project-visible dashboard can only use project scripts.",
  ];
}

/** A markdown fence that the text cannot close: one backtick more than its longest run. */
export function codeFence(text: string): string {
  let longest = 0;
  for (const run of text.match(/`+/g) ?? []) longest = Math.max(longest, run.length);
  return "`".repeat(Math.max(3, longest + 1));
}

/** The edit tool for the editor the user has open; only offered while one is. */
export function buildProposeCodeEditTool(editor: EditorContext, pagePath: string) {
  if (editor.kind === "dashboard") return buildProposeDashboardDraftTool(editor.dashboard, pagePath);
  const isScript = editor.kind === "metric_script";
  const what = isScript
    ? `the metric script \`${editor.script.name}\` the user has open in the Metric script editor`
    : `the flow \`${editor.flow.name}\` the user has open in the Workflow editor`;
  return defineTool({
    name: EDIT_TOOL,
    description:
      `Propose a change to ${what}. Pass the complete new file; ` +
      "the user sees a diff against the editor and applies it there. Nothing is saved by this call, and the turn ends after it.",
    parameters: Type.Object({
      summary: Type.String({ description: "One line on what changes and why." }),
      code: Type.String({
        description: isScript
          ? "The complete new Python source of the metric script (a qdash_metrics module)."
          : "The complete new Python source of the flow module.",
      }),
    }),
    replay: "safe",
    execute: async (params) => {
      const edit: EditProposal =
        editor.kind === "metric_script"
          ? {
              summary: params.summary, code: params.code, target: "metric_script",
              flowName: editor.script.name, chipId: null,
              scriptId: editor.script.scriptId, scriptName: editor.script.name, pagePath,
            }
          : {
              summary: params.summary, code: params.code, target: "flow",
              flowName: editor.flow.name, chipId: editor.flow.chipId ?? null, pagePath,
            };
      return {
        output: [
          {
            type: "text",
            text: "The proposed code is shown to the user as a diff. Stop here; they apply it in the editor, and the next turn's page context carries whatever the editor holds then.",
          },
        ],
        details: { edit } as unknown as JsonValue,
        control: { terminate: true as const },
      };
    },
  });
}

/** The edit tool on a custom dashboard: the same proposal, with the draft as JSON instead of a file. */
function buildProposeDashboardDraftTool(dashboard: DashboardEditorContext, pagePath: string) {
  const isNew = !dashboard.dashboardId;
  const what = isNew
    ? "the new custom dashboard the user is composing"
    : `the custom dashboard \`${dashboard.name}\` the user has open`;
  return defineTool({
    name: EDIT_TOOL,
    description:
      `Propose a change to ${what}. Pass the complete new draft as JSON; ` +
      "the user sees a diff against the page's draft and applies it there. Nothing is saved or shared by this call, and the turn ends after it.",
    parameters: Type.Object({
      summary: Type.String({ description: "One line on what changes and why." }),
      code: Type.String({
        description: isNew
          ? "The complete new draft as a JSON object: {name, description, chip_id, template_id, panels}."
          : 'The complete new draft as a JSON object: {"panels": [...]}, every panel included.',
      }),
    }),
    replay: "safe",
    execute: async (params) => {
      const parsed = parseDashboardDraft(params.code, isNew);
      if (!parsed.ok) {
        throw new Error(`The dashboard draft is invalid; nothing was shown to the user:\n- ${parsed.problems.slice(0, 12).join("\n- ")}`);
      }
      const edit: EditProposal = {
        summary: params.summary,
        code: parsed.code,
        target: "dashboard",
        flowName: dashboard.name,
        chipId: null,
        dashboardId: dashboard.dashboardId ?? null,
        pagePath,
      };
      return {
        output: [
          {
            type: "text",
            text: "The proposed draft is shown to the user as a diff. Stop here; they apply it to the dashboard draft and save it themselves, and the next turn's page context carries whatever the draft holds then.",
          },
        ],
        details: { edit } as unknown as JsonValue,
        control: { terminate: true as const },
      };
    },
  });
}
