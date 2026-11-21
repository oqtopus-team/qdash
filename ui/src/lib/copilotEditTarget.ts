import type { EditProposal, PageContext } from "@/types/copilotChat";

/** The editor of a flow not yet saved: its name and chip are form fields that change after a turn. */
const NEW_FLOW_PATH = "/workflow/new";

/**
 * Whether a proposal was made for the editor the page shows now. A saved flow
 * is identified by its route, name and chip; the New flow page has one editor
 * and nothing saved, so the route alone identifies it. A metric script is
 * identified by its route and script ID, and a dashboard by its route and
 * dashboard ID (a new one, not created yet, by its route). Old proposals without
 * target metadata remain viewable, but cannot replace an editor buffer.
 */
export function matchesEditTarget(edit: EditProposal, page: PageContext | null): boolean {
  if (!page || typeof edit.pagePath !== "string" || edit.pagePath !== page.path) return false;
  if (edit.target === "dashboard") {
    return (
      Boolean(page.dashboard) &&
      (edit.dashboardId ?? null) === (page.dashboard?.dashboardId ?? null)
    );
  }
  if (edit.target === "metric_script") {
    // A metric script is identified by its route and ID; its name can change in the editor.
    return Boolean(page.metricScript) && edit.scriptId === page.metricScript?.scriptId;
  }
  if (!page.flow) return false;
  if (page.path === NEW_FLOW_PATH) return true;
  return edit.flowName === page.flow.name && edit.chipId === (page.flow.chipId ?? null);
}

/** The text of the editor a proposal was made for, when the page shows that editor now. */
export function editTargetCode(edit: EditProposal, page: PageContext | null): string | null {
  if (!matchesEditTarget(edit, page)) return null;
  if (edit.target === "dashboard") return page?.dashboard?.code ?? null;
  return (edit.target === "metric_script" ? page?.metricScript?.code : page?.flow?.code) ?? null;
}
