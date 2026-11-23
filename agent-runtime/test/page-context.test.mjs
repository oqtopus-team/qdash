import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildPageContextSection,
  buildProposeCodeEditTool,
  codeFence,
  editorOf,
  MAX_PAGE_CODE_CHARS,
  parseDashboardDraft,
  parsePageContext,
} from "../src/page-context.ts";

test("a page context is taken only in the shape the API sends", () => {
  assert.equal(parsePageContext(undefined), undefined);
  assert.equal(parsePageContext({ title: "no path" }), undefined);
  assert.deepEqual(parsePageContext({ path: "/chip", title: "Chip" }), { path: "/chip", title: "Chip" });
  assert.deepEqual(
    parsePageContext({ path: "/workflow/t1", flow: { name: "t1", chip_id: "64Qv3", code: "x = 1\n", dirty: true } }),
    { path: "/workflow/t1", flow: { name: "t1", chipId: "64Qv3", code: "x = 1\n", dirty: true } },
  );
  // A flow without code is just a page.
  assert.deepEqual(parsePageContext({ path: "/workflow/t1", flow: { name: "t1" } }), { path: "/workflow/t1" });
});

test("a metric script page is taken in the API's snake_case shape and the UI's camelCase one", () => {
  const path = "/dashboards/scripts/ms_0123456789ab";
  const expected = { path, metricScript: { scriptId: "ms_0123456789ab", name: "ZX90", code: "x = 1\n", dirty: true } };
  assert.deepEqual(
    parsePageContext({ path, flow: null, metric_script: { script_id: "ms_0123456789ab", name: "ZX90", code: "x = 1\n", dirty: true } }),
    expected,
  );
  assert.deepEqual(
    parsePageContext({ path, metricScript: { scriptId: "ms_0123456789ab", name: "ZX90", code: "x = 1\n", dirty: true } }),
    expected,
  );
  // A script without an ID or code is just a page.
  assert.deepEqual(parsePageContext({ path, metric_script: { name: "ZX90", code: "x" } }), { path });
  assert.deepEqual(parsePageContext({ path, metric_script: { script_id: "ms_1", name: "ZX90" } }), { path });
});

test("on the metric script editor the section carries the draft and the propose-not-save rule", () => {
  const section = buildPageContextSection({
    path: "/dashboards/scripts/ms_1",
    title: "ZX90",
    metricScript: { scriptId: "ms_1", name: "ZX90", code: "from qdash_metrics import metric\n", dirty: true },
  });
  assert.match(section, /metric script `ZX90` \(ms_1\) open in the Metric script editor, with unsaved changes/);
  assert.match(section, /`qdash_metrics` API; consult the qdash-metric-scripts skill/);
  assert.match(section, /```python\nfrom qdash_metrics import metric\n```/);
  assert.match(section, /qdash_validate_metric_script, and to qdash_preview_metric_script/);
  assert.match(section, /call `propose_code_edit` with the complete new file/);
  assert.match(section, /do not use qdash_save_metric_script for this script unless they ask/);
  assert.doesNotMatch(section, /Workflow editor|qdash_save_flow/);
  const long = buildPageContextSection({ path: "/s", metricScript: { scriptId: "ms_1", name: "s", code: "x".repeat(MAX_PAGE_CODE_CHARS + 10) } });
  assert.match(long, /cut: the script is longer than/);
});

test("the section names the page, and on the editor carries the code and the edit rule", () => {
  assert.equal(buildPageContextSection(undefined), undefined);
  assert.match(buildPageContextSection({ path: "/chip", title: "Chip 64Qv3" }), /looking at the QDash page "Chip 64Qv3" \(\/chip\)/);
  const section = buildPageContextSection({
    path: "/workflow/t1",
    flow: { name: "t1", chipId: "64Qv3", code: "from prefect import flow\n", dirty: true },
  });
  assert.match(section, /flow `t1` \(chip 64Qv3\) open in the Workflow editor, with unsaved changes/);
  assert.match(section, /```python\nfrom prefect import flow\n```/);
  assert.match(section, /call `propose_code_edit` with the complete new file/);
  assert.match(section, /do not use qdash_save_flow for this flow unless they ask/);
  const long = buildPageContextSection({ path: "/w", flow: { name: "w", code: "x".repeat(MAX_PAGE_CODE_CHARS + 10) } });
  assert.match(long, /cut: the flow is longer than/);
});

test("a flow whose docstring holds a markdown fence cannot close the prompt's fence", () => {
  const code = '"""Usage:\n\n```bash\nqdash run\n```\n"""\nx = 1\n';
  assert.equal(codeFence(code), "````");
  assert.equal(codeFence("x = 1"), "```");
  assert.equal(codeFence("`````inside"), "``````");
  const section = buildPageContextSection({ path: "/workflow/w", flow: { name: "w", code } });
  assert.match(section, /````python\n"""Usage:/);
  assert.match(section, /\n"""\nx = 1\n````\n/);
});

test("the edit tool ends the turn with the proposal in its details", async () => {
  const tool = buildProposeCodeEditTool({ kind: "flow", flow: { name: "t1", chipId: "chip1", code: "" } }, "/workflow/t1");
  assert.equal(tool.name, "propose_code_edit");
  const result = await tool.execute({ summary: "Add T2", code: "new code" }, {}, {});
  assert.deepEqual(result.details, { edit: { summary: "Add T2", code: "new code", target: "flow", flowName: "t1", chipId: "chip1", pagePath: "/workflow/t1" } });
  assert.deepEqual(result.control, { terminate: true });
  assert.match(result.output[0].text, /shown to the user as a diff/);
});

test("a proposal for a metric script names the script the way the UI matches it", async () => {
  const page = parsePageContext({
    path: "/dashboards/scripts/ms_1",
    metric_script: { script_id: "ms_1", name: "ZX90", code: "x = 1\n" },
  });
  const editor = editorOf(page);
  assert.equal(editor.kind, "metric_script");
  const tool = buildProposeCodeEditTool(editor, page.path);
  assert.match(tool.description, /metric script `ZX90`/);
  const result = await tool.execute({ summary: "Use the median", code: "y = 2\n" }, {}, {});
  assert.deepEqual(result.details, {
    edit: {
      summary: "Use the median",
      code: "y = 2\n",
      target: "metric_script",
      flowName: "ZX90",
      chipId: null,
      scriptId: "ms_1",
      scriptName: "ZX90",
      pagePath: "/dashboards/scripts/ms_1",
    },
  });
  assert.deepEqual(result.control, { terminate: true });
  assert.equal(editorOf({ path: "/chip" }), undefined);
});

const dashboardDraft = `${JSON.stringify(
  { panels: [{ panel_id: "a", type: "markdown", title: "Notes", layout: { x: 0, y: 0, w: 12, h: 2 }, config: { content: "x" } }] },
  null,
  2,
)}\n`;

test("a dashboard page is taken in the API's snake_case shape and the UI's camelCase one", () => {
  const path = "/dashboards/dash-1";
  const expected = {
    path,
    dashboard: { dashboardId: "dash-1", name: "Review", visibility: "private", chipId: "chip-1", version: 3, code: "{}", dirty: true },
  };
  assert.deepEqual(
    parsePageContext({
      path,
      flow: null,
      metric_script: null,
      dashboard: { dashboard_id: "dash-1", name: "Review", description: null, visibility: "private", chip_id: "chip-1", version: 3, code: "{}", dirty: true },
    }),
    expected,
  );
  assert.deepEqual(
    parsePageContext({ path, dashboard: { dashboardId: "dash-1", name: "Review", visibility: "private", chipId: "chip-1", version: 3, code: "{}", dirty: true } }),
    expected,
  );
  // A new dashboard has no ID; a dashboard without a draft is just a page.
  assert.deepEqual(parsePageContext({ path: "/dashboards/new", dashboard: { name: "", code: "{}" } }), {
    path: "/dashboards/new",
    dashboard: { name: "", code: "{}" },
  });
  assert.deepEqual(parsePageContext({ path, dashboard: { dashboard_id: "dash-1", name: "Review" } }), { path });
  assert.equal(editorOf(parsePageContext({ path, dashboard: { name: "", code: "{}" } })).kind, "dashboard");
});

test("on a dashboard the section carries the draft and the propose-not-save, never-share rule", () => {
  const section = buildPageContextSection({
    path: "/dashboards/dash-1",
    title: "Dashboard: Review",
    dashboard: { dashboardId: "dash-1", name: "Review", visibility: "project", version: 3, chipId: "chip-1", code: dashboardDraft, dirty: true },
  });
  assert.match(section, /dashboard `Review` \(dash-1\) open and may edit it \(visibility project, draft based on version 3, the page shows chip chip-1\), with unsaved changes/);
  assert.match(section, /```json\n\{\n  "panels"/);
  assert.match(section, /call `propose_code_edit` with the complete new draft as JSON/);
  assert.match(section, /Do not use qdash_save_dashboard for this dashboard unless they ask you to save/);
  assert.match(section, /never change its sharing/);
  assert.match(section, /draft holds only panels/);
  assert.match(section, /Keep the panel_id and the pinned script_revision/);
  const fresh = buildPageContextSection({ path: "/dashboards/new", dashboard: { name: "", code: "{}" } });
  assert.match(fresh, /composing a new dashboard\. It exists only as a draft in their browser and is created when they press Save; the draft is still empty/);
  assert.match(fresh, /template_id names a starter template/);
});

test("a dashboard proposal is checked, written in the page's order, and ends the turn", async () => {
  const page = parsePageContext({ path: "/dashboards/dash-1", dashboard: { dashboard_id: "dash-1", name: "Review", code: dashboardDraft } });
  const tool = buildProposeCodeEditTool(editorOf(page), page.path);
  assert.equal(tool.name, "propose_code_edit");
  assert.match(tool.description, /dashboard `Review`/);
  assert.match(tool.description, /Nothing is saved or shared by this call/);
  const proposed = { panels: [{ config: { content: "y" }, layout: { h: 2, w: 6, y: 0, x: 0 }, type: "markdown", panel_id: "a" }] };
  const result = await tool.execute({ summary: "Halve the note", code: JSON.stringify(proposed) }, {}, {});
  assert.deepEqual(result.control, { terminate: true });
  assert.deepEqual(result.details.edit, {
    summary: "Halve the note",
    code: `${JSON.stringify({ panels: [{ panel_id: "a", type: "markdown", title: "", layout: { x: 0, y: 0, w: 6, h: 2 }, config: { content: "y" } }] }, null, 2)}\n`,
    target: "dashboard",
    flowName: "Review",
    chipId: null,
    dashboardId: "dash-1",
    pagePath: "/dashboards/dash-1",
  });
  // An invalid draft fails the call, so the model can correct it; nothing reaches the user.
  await assert.rejects(tool.execute({ summary: "Share", code: JSON.stringify({ ...proposed, visibility: "project" }) }, {}, {}), /visibility is not part of a draft/);
  await assert.rejects(tool.execute({ summary: "Bad", code: "{not json" }, {}, {}), /not valid JSON/);
  await assert.rejects(
    tool.execute({ summary: "Wide", code: JSON.stringify({ panels: [{ ...proposed.panels[0], layout: { x: 8, y: 0, w: 6, h: 2 } }] }) }, {}, {}),
    /12-column grid/,
  );
});

test("a new dashboard's proposal carries its name, chip and template, and no ID", async () => {
  const page = parsePageContext({ path: "/dashboards/new", dashboard: { name: "", code: "{}" } });
  const tool = buildProposeCodeEditTool(editorOf(page), page.path);
  const result = await tool.execute(
    { summary: "Start from collisions", code: JSON.stringify({ template_id: "frequency-collision-map", name: "Collisions", panels: [] }) },
    {},
    {},
  );
  assert.equal(result.details.edit.dashboardId, null);
  assert.deepEqual(JSON.parse(result.details.edit.code), {
    name: "Collisions",
    description: "",
    chip_id: null,
    template_id: "frequency-collision-map",
    panels: [],
  });
  const parsed = parseDashboardDraft(JSON.stringify({ name: 1, panels: [] }), true);
  assert.equal(parsed.ok, false);
  assert.deepEqual(parsed.problems, ["name must be a string"]);
  // A saved dashboard's draft holds only panels.
  assert.equal(parseDashboardDraft(JSON.stringify({ name: "x", panels: [] }), false).ok, false);
  // A missing panels list is refused, not read as "remove every panel".
  for (const isNew of [false, true]) {
    const missing = parseDashboardDraft(JSON.stringify({}), isNew);
    assert.equal(missing.ok, false);
    assert.match(missing.problems.join("\n"), /panels is required/);
  }
});
