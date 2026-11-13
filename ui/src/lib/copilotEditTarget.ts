import type { EditProposal, PageContext } from "@/types/copilotChat";

/** The editor of a flow not yet saved: its name and chip are form fields that change after a turn. */
const NEW_FLOW_PATH = "/workflow/new";

/**
 * Whether a proposal was made for the editor the page shows now. A saved flow
 * is identified by its route, name and chip; the New flow page has one editor
 * and nothing saved, so the route alone identifies it. Old proposals without
 * target metadata remain viewable, but cannot replace an editor buffer.
 */
export function matchesEditTarget(edit: EditProposal, page: PageContext | null): boolean {
  if (!page?.flow || typeof edit.pagePath !== "string" || edit.pagePath !== page.path) return false;
  if (page.path === NEW_FLOW_PATH) return true;
  return edit.flowName === page.flow.name && edit.chipId === (page.flow.chipId ?? null);
}
