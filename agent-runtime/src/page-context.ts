/**
 * What the user has open in QDash while they chat from the sidebar or the
 * floating window, and the edit tool it enables.
 *
 * The API forwards the page with every turn, so the section below is rebuilt
 * each time: an editor's buffer changes as the user types, and the model must
 * see the current text, saved or not. On the Workflow editor and on the metric
 * script editor the model also gets `propose_code_edit`: it proposes the
 * complete new file, the chat shows a diff, and the user applies it in the
 * editor and saves. The runtime never writes the flow or the script itself.
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

export interface PageContext {
  /** The route, such as `/workflow/t1_check` or `/custom-dashboards/scripts/ms_…`. */
  path: string;
  title?: string;
  flow?: FlowEditorContext;
  metricScript?: MetricScriptEditorContext;
}

/** The editor a page shows, when it shows one the model can propose changes to. */
export type EditorContext =
  | { kind: "flow"; flow: FlowEditorContext }
  | { kind: "metric_script"; script: MetricScriptEditorContext };

/** A change the model proposes to the open editor, as the UI receives it. */
export interface EditProposal {
  summary: string;
  code: string;
  /** Which editor the change is for. */
  target: "flow" | "metric_script";
  /** The flow's name; for a metric script, the script's name. */
  flowName: string;
  chipId: string | null;
  /** The metric script the change is for (target `metric_script`). */
  scriptId?: string;
  scriptName?: string;
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
  return page;
}

/** The editor the page shows; the Workflow editor wins if a page ever carried both. */
export function editorOf(page: PageContext | undefined): EditorContext | undefined {
  if (page?.flow) return { kind: "flow", flow: page.flow };
  if (page?.metricScript) return { kind: "metric_script", script: page.metricScript };
  return undefined;
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
  }
  return lines.join("\n");
}

/** A markdown fence that the text cannot close: one backtick more than its longest run. */
export function codeFence(text: string): string {
  let longest = 0;
  for (const run of text.match(/`+/g) ?? []) longest = Math.max(longest, run.length);
  return "`".repeat(Math.max(3, longest + 1));
}

/** The edit tool for the editor the user has open; only offered while one is. */
export function buildProposeCodeEditTool(editor: EditorContext, pagePath: string) {
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
