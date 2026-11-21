import { describe, expect, it } from "vitest";
import { editTargetCode, matchesEditTarget } from "../copilotEditTarget";
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

  it("identifies a dashboard by its route and ID, and a new one by its route", () => {
    const boardPage: PageContext = {
      title: "Dashboard: Review",
      path: "/dashboards/dash-1",
      dashboard: { dashboardId: "dash-1", name: "Review", code: '{"panels":[]}' },
    };
    const boardEdit: EditProposal = {
      summary: "Add a map",
      code: '{"panels":[1]}',
      target: "dashboard",
      flowName: "Review",
      chipId: null,
      dashboardId: "dash-1",
      pagePath: "/dashboards/dash-1",
    };
    expect(matchesEditTarget(boardEdit, boardPage)).toBe(true);
    expect(editTargetCode(boardEdit, boardPage)).toBe('{"panels":[]}');
    // Another dashboard, or the same route without an editable draft (a viewer).
    expect(matchesEditTarget({ ...boardEdit, dashboardId: "dash-2" }, boardPage)).toBe(false);
    expect(matchesEditTarget(boardEdit, { ...boardPage, dashboard: undefined })).toBe(false);
    // A proposal for a new draft does not apply to the dashboard it became.
    const newEdit = { ...boardEdit, dashboardId: null, pagePath: "/dashboards/new" };
    expect(matchesEditTarget(newEdit, boardPage)).toBe(false);
    const newPage: PageContext = {
      title: "New dashboard",
      path: "/dashboards/new",
      dashboard: { name: "", code: "{}" },
    };
    expect(matchesEditTarget(newEdit, newPage)).toBe(true);
    expect(matchesEditTarget(boardEdit, newPage)).toBe(false);
  });

  it("identifies a metric script editor by its route and script ID", () => {
    const scriptPage: PageContext = {
      title: "Metric script: ZX90",
      path: "/dashboards/scripts/ms_1",
      metricScript: { scriptId: "ms_1", name: "ZX90", code: "old script", dirty: false },
    };
    const scriptEdit: EditProposal = {
      summary: "Count observations",
      code: "new script",
      target: "metric_script",
      flowName: "ZX90",
      chipId: null,
      scriptId: "ms_1",
      scriptName: "ZX90",
      pagePath: "/dashboards/scripts/ms_1",
    };
    expect(matchesEditTarget(scriptEdit, scriptPage)).toBe(true);
    expect(editTargetCode(scriptEdit, scriptPage)).toBe("old script");
    // The script was renamed in the editor; the ID still matches.
    const renamed = { ...scriptPage, metricScript: { ...scriptPage.metricScript!, name: "New" } };
    expect(matchesEditTarget(scriptEdit, renamed)).toBe(true);
    expect(matchesEditTarget({ ...scriptEdit, scriptId: "ms_2" }, scriptPage)).toBe(false);
    expect(
      matchesEditTarget({ ...scriptEdit, pagePath: "/dashboards/scripts/ms_2" }, scriptPage),
    ).toBe(false);
    // A flow proposal never lands in a script editor, nor a script proposal in a flow editor.
    expect(matchesEditTarget({ ...edit, pagePath: scriptPage.path }, scriptPage)).toBe(false);
    expect(matchesEditTarget({ ...scriptEdit, pagePath: page.path }, page)).toBe(false);
    expect(editTargetCode(edit, page)).toBe("old");
    expect(editTargetCode(scriptEdit, page)).toBeNull();
  });
});
