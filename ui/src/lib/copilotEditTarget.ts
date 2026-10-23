import type { EditProposal, PageContext } from "@/types/copilotChat";

/** Old proposals without target metadata remain viewable, but cannot replace an editor buffer. */
export function matchesEditTarget(edit: EditProposal, page: PageContext | null): boolean {
  return Boolean(
    page?.flow &&
    edit.pagePath === page.path &&
    edit.flowName === page.flow.name &&
    edit.chipId === (page.flow.chipId ?? null),
  );
}
