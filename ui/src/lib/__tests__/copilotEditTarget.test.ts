import { describe, expect, it } from "vitest";
import { matchesEditTarget } from "../copilotEditTarget";
import type { EditProposal, PageContext } from "@/types/copilotChat";

const edit: EditProposal = {
  summary: "Update flow",
  code: "new",
  flowName: "t1",
  chipId: "chip1",
  pagePath: "/workflow/t1",
};
const page: PageContext = {
  title: "Workflow editor: t1",
  path: "/workflow/t1",
  flow: { name: "t1", chipId: "chip1", code: "old", dirty: true },
};

describe("matchesEditTarget", () => {
  it("requires the same flow, chip and route", () => {
    expect(matchesEditTarget(edit, page)).toBe(true);
    expect(matchesEditTarget({ ...edit, flowName: "t2" }, page)).toBe(false);
    expect(matchesEditTarget({ ...edit, chipId: "chip2" }, page)).toBe(false);
    expect(matchesEditTarget({ ...edit, pagePath: "/workflow/new" }, page)).toBe(false);
    expect(matchesEditTarget(edit, null)).toBe(false);
  });

  it("identifies the New flow editor by its route alone, since name and chip are typed later", () => {
    const draft: PageContext = {
      ...page,
      path: "/workflow/new",
      flow: { ...page.flow!, chipId: undefined },
    };
    expect(matchesEditTarget({ ...edit, chipId: null, pagePath: draft.path }, draft)).toBe(true);
    // Proposed before the user named the flow or picked a chip.
    const early = { ...edit, flowName: "new_flow", chipId: null, pagePath: draft.path };
    expect(matchesEditTarget(early, draft)).toBe(true);
    expect(matchesEditTarget(early, { ...draft, flow: { ...draft.flow!, chipId: "chip1" } })).toBe(
      true,
    );
    // But not a proposal made for a saved flow's editor.
    expect(matchesEditTarget(edit, draft)).toBe(false);
    const legacy = { summary: "Update", code: "new", flowName: "t1" } as EditProposal;
    expect(matchesEditTarget(legacy, draft)).toBe(false);
  });
});
