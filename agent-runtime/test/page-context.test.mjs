import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildPageContextSection,
  buildProposeCodeEditTool,
  codeFence,
  editorOf,
  MAX_PAGE_CODE_CHARS,
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
  const path = "/custom-dashboards/scripts/ms_0123456789ab";
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
    path: "/custom-dashboards/scripts/ms_1",
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
    path: "/custom-dashboards/scripts/ms_1",
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
      pagePath: "/custom-dashboards/scripts/ms_1",
    },
  });
  assert.deepEqual(result.control, { terminate: true });
  assert.equal(editorOf({ path: "/chip" }), undefined);
});
