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

  it("allows a new flow without a chip but rejects legacy proposals without target metadata", () => {
    const draft: PageContext = {
      ...page,
      path: "/workflow/new",
      flow: { ...page.flow!, chipId: undefined },
    };
    expect(matchesEditTarget({ ...edit, chipId: null, pagePath: draft.path }, draft)).toBe(true);
    const legacy = { summary: "Update", code: "new", flowName: "t1" } as EditProposal;
    expect(matchesEditTarget(legacy, draft)).toBe(false);
  });
});
