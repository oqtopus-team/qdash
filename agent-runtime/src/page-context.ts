/**
 * What the user has open in QDash while they chat from the sidebar or the
 * floating window, and the edit tool it enables.
 *
 * The API forwards the page with every turn, so the section below is rebuilt
 * each time: the Workflow editor's buffer changes as the user types, and the
 * model must see the current text, saved or not. On the Workflow editor the
 * model also gets `propose_code_edit`: it proposes the complete new file, the
 * chat shows a diff, and the user applies it in the editor and saves. The
 * runtime never writes the flow itself.
 */
import type { JsonValue } from "@earendil-works/chord";
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

export interface PageContext {
  /** The route, such as `/workflow/t1_check`. */
  path: string;
  title?: string;
  flow?: FlowEditorContext;
}

/** A change the model proposes to the open editor, as the UI receives it. */
export interface EditProposal {
  summary: string;
  code: string;
  flowName: string;
  chipId: string | null;
  pagePath: string;
}

export const PAGE_SECTION = "qdash-page";
export const EDIT_TOOL = "propose_code_edit";
/** Longest flow text placed in the prompt; the rest is cut with a note. */
export const MAX_PAGE_CODE_CHARS = 24_000;

function text(value: unknown, max: number): string | undefined {
  return typeof value === "string" && value.trim() ? value.slice(0, max) : undefined;
}

/** The page context of a request body, or `undefined` when it carries none the runtime understands. */
export function parsePageContext(value: unknown): PageContext | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const record = value as Record<string, unknown>;
  const path = text(record.path, 512);
  if (!path) return undefined;
  const title = text(record.title, 200);
  const page: PageContext = { path, ...(title ? { title } : {}) };
  const flow = record.flow;
  if (flow && typeof flow === "object" && !Array.isArray(flow)) {
    const f = flow as Record<string, unknown>;
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
  return page;
}

/** The system prompt section describing the page, rebuilt every turn. */
export function buildPageContextSection(page: PageContext | undefined): string | undefined {
  if (!page) return undefined;
  const where = page.title ? `"${page.title}" (${page.path})` : page.path;
  const lines = [`The user is looking at the QDash page ${where} while they talk to you.`];
  if (page.flow) {
    const { name, chipId, dirty } = page.flow;
    let code = page.flow.code.replace(/\n+$/, "");
    if (code.length > MAX_PAGE_CODE_CHARS) {
      code = `${code.slice(0, MAX_PAGE_CODE_CHARS)}\n# … cut: the flow is longer than ${MAX_PAGE_CODE_CHARS} characters`;
    }
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
  }
  return lines.join("\n");
}

/** A markdown fence that the text cannot close: one backtick more than its longest run. */
export function codeFence(text: string): string {
  let longest = 0;
  for (const run of text.match(/`+/g) ?? []) longest = Math.max(longest, run.length);
  return "`".repeat(Math.max(3, longest + 1));
}

/** The edit tool for the flow the user has open; only offered while one is. */
export function buildProposeCodeEditTool(flow: FlowEditorContext, pagePath: string) {
  return defineTool({
    name: EDIT_TOOL,
    description:
      `Propose a change to the flow \`${flow.name}\` the user has open in the Workflow editor. Pass the complete new file; ` +
      "the user sees a diff against the editor and applies it there. Nothing is saved by this call, and the turn ends after it.",
    parameters: Type.Object({
      summary: Type.String({ description: "One line on what changes and why." }),
      code: Type.String({ description: "The complete new Python source of the flow module." }),
    }),
    replay: "safe",
    execute: async (params) => {
      const edit: EditProposal = {
        summary: params.summary, code: params.code, flowName: flow.name,
        chipId: flow.chipId ?? null, pagePath,
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
