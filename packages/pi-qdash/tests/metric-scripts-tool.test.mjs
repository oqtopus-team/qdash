import assert from "node:assert/strict";
import test from "node:test";

import {
  apiError,
  dashboardSaveProblems,
  formatEvaluation,
  formatErrorDetail,
  metricScriptQuery,
  registerMetricScriptTools,
  scriptSaveProblems,
} from "../.test-dist/tools/metric-scripts.js";

const SOURCE = [
  "from qdash_metrics import metric",
  "",
  "@metric(title='T1', unit='us')",
  "def t1(target, ctx):",
  "    return ctx.data['t1'][target].latest()",
  "",
].join("\n");

const METRIC = {
  id: "zx90_median",
  title: "Median ZX90 gate fidelity",
  unit: "%",
  target: "pair",
  hops: [1],
  parameters: { min_samples: { default: 3, label: "Minimum observations", kind: "integer", min: 1, max: null, unit: "", choices: null } },
  has_legend: true,
};

function evaluation(cells, extra = {}) {
  return {
    script_id: null,
    revision: null,
    metric: METRIC,
    chip_id: "64Qv3",
    start: "2026-11-06T00:00:00Z",
    end: "2026-11-20T00:00:00Z",
    params: { min_samples: 3 },
    legend: { kind: "continuous", items: [], stops: [{ value: 90, color: "#dc2626" }, { value: 99, color: "#2563eb" }] },
    cells,
    log: "",
    evaluated_at: "2026-11-20T00:00:01Z",
    truncated: false,
    ...extra,
  };
}

function apiFailure(statusCode, detail) {
  const error = new Error(`HTTP ${statusCode}`);
  error.statusCode = statusCode;
  error.payload = { detail };
  return error;
}

/** The registered tools over a stub client that records every call. */
function setup(overrides = {}) {
  const tools = new Map();
  const calls = [];
  const record = (name, result) => async (...args) => {
    calls.push([name, ...args]);
    if (typeof result === "function") return result(...args);
    if (result === undefined) throw new Error(`${name} must not be called`);
    return result;
  };
  const client = {
    validateMetricScript: record("validate", overrides.validate ?? { ok: true, metrics: [METRIC], diagnostics: [] }),
    evaluateMetricScriptDraft: record("evaluateDraft", overrides.evaluateDraft),
    evaluateMetricScript: record("evaluate", overrides.evaluate),
    createMetricScript: record("create", overrides.create),
    updateMetricScript: record("update", overrides.update),
    createDashboard: record("createDashboard", overrides.createDashboard),
    updateDashboard: record("updateDashboard", overrides.updateDashboard),
    listMetricScriptTemplates: record("templates", overrides.templates),
    previewDashboardTemplate: record("previewTemplate", overrides.previewTemplate),
  };
  registerMetricScriptTools({ registerTool(tool) { tools.set(tool.name, tool); } }, {
    async makeClient() { return client; },
    async resolveChipId(_client, explicit) { return explicit ?? "64Qv3"; },
    pageUrl: (_client, path) => `https://qdash.example${path}`,
  });
  return { tools, calls };
}

const uiContext = (answer, asked = { count: 0 }) => ({
  hasUI: true,
  ui: { async confirm() { asked.count += 1; return answer; } },
});

const savedScript = (overrides = {}) => ({
  script_id: "ms_0123456789ab",
  name: "ZX90",
  visibility: "private",
  status: "valid",
  revision: 2,
  active_revision: 2,
  metrics: [METRIC],
  diagnostics: [],
  ...overrides,
});

test("the preview summary names the metric, period, counts, legend, samples and errors", () => {
  const cells = [
    { key: "0>1", status: "ok", value: 99.1234, label: "median of 14", assessment: { count: 14 } },
    { key: "1>0", status: "ok", value: 95, label: "median of 3", assessment: { count: 3 } },
    { key: "2>3", status: "missing", value: null, label: "fewer than min_samples observations", assessment: { count: 1 } },
    { key: "3>2", status: "empty", value: null, message: "Function returned None" },
    { key: "4>5", status: "error", message: "KeyError", diagnostic: { message: "KeyError: 'zx90'", line: 30, function: "zx90_median" } },
  ];
  const text = formatEvaluation(evaluation(cells, { truncated: true, log: "checked 5 pairs\n" }));
  assert.match(text, /^Median ZX90 gate fidelity \(`zx90_median`\) \[%\], pair, hops 1; draft source \(not saved\)\./);
  assert.match(text, /Chip 64Qv3, period 2026-11-06T00:00:00Z → 2026-11-20T00:00:00Z/);
  assert.match(text, /Parameters: min_samples=3/);
  assert.match(text, /Cells: 5 \(ok 2, missing 1, empty 1, error 1\)/);
  assert.match(text, /Legend: continuous: 90 % #dc2626 → 99 % #2563eb/);
  assert.match(text, /- 0>1: 99\.123 % — median of 14; n=14/);
  assert.match(text, /- 2>3: missing — fewer than min_samples observations; n=1/);
  assert.match(text, /- 3>2: empty — Function returned None/);
  assert.match(text, /Errors \(1 cell\):\n- 4>5: line 30 in zx90_median: KeyError: 'zx90'/);
  assert.match(text, /Truncated: .*400-day cap/);
  assert.match(text, /Script output:\nchecked 5 pairs/);
});

test("the summary shows at most 12 sample cells and 5 errors", () => {
  const cells = [
    ...Array.from({ length: 20 }, (_, index) => ({ key: String(index), status: "ok", value: index })),
    ...Array.from({ length: 8 }, (_, index) => ({ key: `e${index}`, status: "error", message: `boom ${index}` })),
  ];
  const text = formatEvaluation({ ...evaluation(cells), script_id: "ms_1", revision: 4, metric: { ...METRIC, target: "qubit", unit: "us" } });
  assert.match(text, /script ms_1 revision 4/);
  assert.match(text, /Sample cells \(12 of 28\)/);
  assert.equal(text.match(/^- \d+: /gm).length, 12);
  assert.match(text, /Errors \(8 cells, first 5\)/);
  assert.doesNotMatch(text, /boom 5/);
});

test("API error details are spelled out: worker failures, field errors and plain strings", () => {
  assert.equal(
    formatErrorDetail({ message: "The script failed", diagnostics: [{ message: "SyntaxError: invalid syntax", line: 3, column: 7 }], log: "partial\n" }),
    "The script failed\n- line 3:7: SyntaxError: invalid syntax\nScript output:\npartial",
  );
  assert.equal(formatErrorDetail([{ loc: ["body", "period", "start"], msg: "start and end must include a timezone" }]), "period.start: start and end must include a timezone");
  assert.equal(formatErrorDetail("Chip 'x' not found"), "Chip 'x' not found");
  assert.deepEqual(apiError(apiFailure(429, "Metric script evaluation queue is full")), { status: 429, text: "Metric script evaluation queue is full" });
  assert.equal(apiError(new TypeError("fetch failed")), undefined);
});

test("a preview takes a draft or a saved script, on the default chip unless one is given", async () => {
  const { tools, calls } = setup({ evaluateDraft: evaluation([]), evaluate: { ...evaluation([]), script_id: "ms_1", revision: 2 } });
  const preview = tools.get("qdash_preview_metric_script");
  const period = { kind: "absolute", start: "2026-11-01T00:00:00+09:00", end: "2026-11-15T00:00:00+09:00" };
  const draft = await preview.execute("t", { source: SOURCE, metricId: "zx90_median", period, params: { min_samples: 5 } });
  assert.deepEqual(calls[0], ["evaluateDraft", { source: SOURCE, metric_id: "zx90_median", chip_id: "64Qv3", period, params: { min_samples: 5 } }]);
  assert.equal(draft.details.ok, true);
  assert.equal(draft.details.data.metric.id, "zx90_median");

  await preview.execute("t", { scriptId: "ms_1", revision: 2, metricId: "zx90_median", chipId: "chipB" });
  assert.deepEqual(calls[1], ["evaluate", "ms_1", { metric_id: "zx90_median", chip_id: "chipB", revision: 2 }]);

  const neither = await preview.execute("t", { metricId: "x" });
  assert.equal(neither.details.ok, false);
  assert.equal(calls.length, 2);
});

test("a failed evaluation is reported with QDash's detail, and a full queue says to wait", async () => {
  const { tools } = setup({
    evaluateDraft: () => { throw apiFailure(422, { message: "Metric 'nope' is not defined; expected one of: t1", diagnostics: [], log: "" }); },
  });
  const result = await tools.get("qdash_preview_metric_script").execute("t", { source: SOURCE, metricId: "nope" });
  assert.equal(result.details.ok, false);
  assert.match(result.content[0].text, /QDash rejected the evaluation \(HTTP 422\): Metric 'nope' is not defined/);

  const busy = setup({ evaluateDraft: () => { throw apiFailure(429, "Metric script evaluation queue is full"); } });
  const queued = await busy.tools.get("qdash_preview_metric_script").execute("t", { source: SOURCE, metricId: "t1" });
  assert.match(queued.content[0].text, /HTTP 429.*\nThe evaluation queue is full; wait a moment/);
});

test("validation reports metrics or diagnostics and saves nothing", async () => {
  const { tools, calls } = setup({ validate: { ok: false, metrics: [], diagnostics: [{ message: "Import 'os' is not allowed.", line: 1, column: 1 }] } });
  const result = await tools.get("qdash_validate_metric_script").execute("t", { source: "import os\n" });
  assert.equal(result.details.ok, false);
  assert.match(result.content[0].text, /Invalid \(1 problem\)\. Nothing was saved\.\n- line 1:1: Import 'os' is not allowed\./);
  assert.deepEqual(calls.map(([name]) => name), ["validate"]);

  const valid = setup();
  const ok = await valid.tools.get("qdash_validate_metric_script").execute("t", { source: SOURCE });
  assert.match(ok.content[0].text, /Valid: 1 metric\. Nothing was saved\.\n- `zx90_median` — Median ZX90 gate fidelity \[%\], pair, hops 1; parameters: min_samples=3 \(integer, min 1\); has a legend/);
});

test("a script that would not validate is refused before anyone is asked to approve it", async () => {
  const asked = { count: 0 };
  const { tools, calls } = setup({ validate: { ok: false, metrics: [], diagnostics: [{ message: "NameError: x", line: 4, function: "t1" }] } });
  const result = await tools.get("qdash_save_metric_script").execute("t", { name: "T1", source: SOURCE }, undefined, undefined, uiContext(true, asked));
  assert.equal(asked.count, 0);
  assert.deepEqual(calls.map(([name]) => name), ["validate"]);
  assert.equal(result.details.saved, false);
  assert.match(result.content[0].text, /not saved and no confirmation was asked[\s\S]*- line 4 in t1: NameError: x/);

  assert.deepEqual(scriptSaveProblems({ name: " ", source: "" }), ["name must not be empty", "source is empty"]);
  const local = await tools.get("qdash_save_metric_script").execute("t", { name: "", source: SOURCE }, undefined, undefined, uiContext(true, asked));
  assert.equal(local.details.problemCount, 1);
  assert.equal(calls.length, 1);
});

test("the script save is confirmation-gated and never writes on refusal or without a UI", async () => {
  const { tools, calls } = setup();
  const save = tools.get("qdash_save_metric_script");
  await assert.rejects(save.execute("t", { name: "T1", source: SOURCE }, undefined, undefined, uiContext(false)), /requires explicit confirmation/);
  await assert.rejects(save.execute("t", { name: "T1", source: SOURCE }, undefined, undefined, { hasUI: false }), /requires explicit confirmation/);
  assert.deepEqual(calls.map(([name]) => name), ["validate", "validate"]);
});

test("without scriptId the save creates a script; with one it saves a revision guarded by expectedRevision", async () => {
  const { tools, calls } = setup({
    create: savedScript({ revision: 1, active_revision: 1 }),
    update: savedScript({ status: "invalid", revision: 3, active_revision: 2, diagnostics: [{ message: "ZeroDivisionError", line: 9 }] }),
  });
  const save = tools.get("qdash_save_metric_script");
  const created = await save.execute("t", { name: "ZX90", source: SOURCE, visibility: "project" }, undefined, undefined, uiContext(true));
  assert.deepEqual(calls[1], ["create", { name: "ZX90", source: SOURCE, visibility: "project" }]);
  assert.equal(created.details.created, true);
  assert.equal(created.details.activeRevision, 1);
  assert.match(created.content[0].text, /Created metric script 'ZX90' \(ms_0123456789ab\) as revision 1, private\.\nIt validated: revision 1 is now the active revision\./);
  assert.match(created.content[0].text, /Page: https:\/\/qdash\.example\/dashboards\/scripts\/ms_0123456789ab/);
  assert.match(created.content[0].text, /panels keep the revision they pin/);

  const updated = await save.execute(
    "t",
    { scriptId: "ms_0123456789ab", name: "ZX90", description: "median", source: SOURCE, expectedRevision: 2, confirmWrite: true },
    undefined,
    undefined,
    { hasUI: false },
  );
  assert.deepEqual(calls[3], ["update", "ms_0123456789ab", { name: "ZX90", source: SOURCE, description: "median", expected_revision: 2 }]);
  assert.equal(updated.details.created, false);
  assert.match(updated.content[0].text, /did not validate \(status invalid\): the active revision stays 2, the last one that validated\.\nDiagnostics:\n- line 9: ZeroDivisionError/);
});

test("a concurrent save (409) is reported, not thrown", async () => {
  const { tools } = setup({ update: () => { throw apiFailure(409, "The script is at revision 5, not 4; reload it"); } });
  const result = await tools.get("qdash_save_metric_script").execute(
    "t",
    { scriptId: "ms_1", name: "x", source: SOURCE, expectedRevision: 4, confirmWrite: true },
    undefined,
    undefined,
    { hasUI: false },
  );
  assert.equal(result.details.saved, false);
  assert.equal(result.details.status, 409);
  assert.match(result.content[0].text, /QDash rejected the metric script \(HTTP 409\): The script is at revision 5, not 4; reload it\nNothing was saved\. Read the current state again/);
});

const PANEL = {
  panel_id: "p1",
  type: "metric_script",
  title: "ZX90 median",
  layout: { x: 0, y: 0, w: 12, h: 6 },
  config: { script_id: "ms_1", metric_id: "zx90_median", script_revision: 2, period: { kind: "relative", days: 14 }, params: {}, view: "map", direction: "both", hops: [1] },
};

test("dashboard saves send the API's shape: create with a template, update with only what changed", async () => {
  const response = (overrides = {}) => ({
    dashboard_id: "cd_1",
    name: "Couplings",
    visibility: "project",
    chip_id: "64Qv3",
    panels: [{ ...PANEL, script_name: "ZX90", latest_revision: 3 }],
    ...overrides,
  });
  const { tools, calls } = setup({
    createDashboard: response(),
    updateDashboard: response({ panels: [{ ...PANEL, script_name: "ZX90", latest_revision: 2 }] }),
    previewTemplate: { template_id: "frequency-collision-map", name: "Frequency Collision Map", panels: [], scripts_to_create: [] },
  });
  const save = tools.get("qdash_save_dashboard");

  const created = await save.execute(
    "t",
    { name: "Couplings", visibility: "project", chipId: "64Qv3", panels: [PANEL], confirmWrite: true },
    undefined,
    undefined,
    { hasUI: false },
  );
  assert.deepEqual(calls[0], ["createDashboard", { name: "Couplings", visibility: "project", chip_id: "64Qv3", panels: [PANEL] }]);
  assert.match(created.content[0].text, /Created dashboard 'Couplings' \(cd_1\), project, chip 64Qv3, 1 panel\./);
  assert.match(created.content[0].text, /- ZX90 median: ZX90 \/ zx90_median, pinned to revision 2 \(revision 3 is active\)/);
  assert.match(created.content[0].text, /Page: https:\/\/qdash\.example\/dashboards\/cd_1/);

  // Response-only annotations are not sent back.
  await save.execute(
    "t",
    { dashboardId: "cd_1", panels: [{ ...PANEL, script_name: "ZX90", latest_revision: 3 }] },
    undefined,
    undefined,
    uiContext(true),
  );
  assert.deepEqual(calls[1], ["updateDashboard", "cd_1", { panels: [PANEL] }]);

  await save.execute("t", { name: "Starter", templateId: "frequency-collision-map", confirmWrite: true }, undefined, undefined, { hasUI: false });
  assert.deepEqual(calls[2], ["previewTemplate", "frequency-collision-map"]);
  assert.deepEqual(calls[3], ["createDashboard", { name: "Starter", template_id: "frequency-collision-map" }]);

  await save.execute("t", { dashboardId: "cd_1", name: "Renamed", expectedVersion: 3, confirmWrite: true }, undefined, undefined, { hasUI: false });
  assert.deepEqual(calls[4], ["updateDashboard", "cd_1", { name: "Renamed", expected_version: 3 }]);
});

test("a template-based dashboard save names the shared scripts it adds before asking", async () => {
  const messages = [];
  const ask = (answer) => ({ hasUI: true, ui: { async confirm(_title, message) { messages.push(message); return answer; } } });
  const preview = {
    template_id: "frequency-collision-map",
    name: "Frequency Collision Map",
    panels: [],
    scripts_to_create: [{ template_id: "collision", name: "Frequency collision checks", source: "x = 1" }],
  };
  const { tools, calls } = setup({
    previewTemplate: preview,
    createDashboard: { dashboard_id: "cd_2", name: "Collisions", visibility: "private", chip_id: null, panels: [] },
  });
  const save = tools.get("qdash_save_dashboard");

  await assert.rejects(save.execute("t", { name: "Collisions", templateId: "frequency-collision-map" }, undefined, undefined, ask(false)), /requires explicit confirmation/);
  assert.match(messages[0], /a new dashboard 'Collisions'.*It also adds a project-visible metric script from the starter template: 'Frequency collision checks' \(collision\)\./);
  assert.deepEqual(calls.map(([name]) => name), ["previewTemplate"]);

  const saved = await save.execute("t", { name: "Collisions", templateId: "frequency-collision-map" }, undefined, undefined, ask(true));
  assert.deepEqual(calls.map(([name]) => name), ["previewTemplate", "previewTemplate", "createDashboard"]);
  assert.match(saved.content[0].text, /Creation also added a project-visible metric script from the starter template: 'Frequency collision checks'/);
  assert.deepEqual(saved.details.data.scripts_created, preview.scripts_to_create);

  // Explicit panels never copy the template, so nothing is previewed or disclosed.
  calls.length = 0;
  await save.execute("t", { name: "Own", panels: [PANEL], confirmWrite: true }, undefined, undefined, { hasUI: false });
  assert.deepEqual(calls.map(([name]) => name), ["createDashboard"]);
});

test("dashboard problems are reported before confirmation, and the save is gated", async () => {
  const asked = { count: 0 };
  const { tools, calls } = setup({ createDashboard: {} });
  const save = tools.get("qdash_save_dashboard");
  const unpinned = { ...PANEL, layout: { x: 6, y: 0, w: 12, h: 4 }, config: { script_id: "ms_1", metric_id: "m" } };
  const result = await save.execute("t", { panels: [unpinned] }, undefined, undefined, uiContext(true, asked));
  assert.equal(asked.count, 0);
  assert.equal(calls.length, 0);
  assert.deepEqual(result.details.data.problems, [
    "a new dashboard needs a name",
    "panels[0].layout exceeds the 12-column grid (x + w > 12)",
    "panels[0].config.script_revision must pin a saved revision (an integer)",
  ]);
  assert.deepEqual(dashboardSaveProblems({ dashboardId: "cd_1", templateId: "t" }), ["templateId applies only when creating a dashboard"]);
  assert.deepEqual(dashboardSaveProblems({ name: "x", expectedVersion: 1 }), ["expectedVersion applies only when updating a dashboard"]);
  await assert.rejects(save.execute("t", { name: "x" }, undefined, undefined, uiContext(false)), /requires explicit confirmation/);
  assert.equal(calls.length, 0);
});

test("query actions list templates without source and return one template with it", async () => {
  const templates = { templates: [{ template_id: "zx90_median", name: "Median ZX90", description: "d", source: "x = 1" }] };
  const client = { listMetricScriptTemplates: async () => templates };
  assert.deepEqual(await metricScriptQuery(client, "metric_script_templates", {}), { templates: [{ template_id: "zx90_median", name: "Median ZX90", description: "d" }] });
  assert.equal((await metricScriptQuery(client, "metric_script_template", { templateId: "zx90_median" })).source, "x = 1");
  await assert.rejects(metricScriptQuery(client, "metric_script_template", { templateId: "nope" }), /Unknown metric script template 'nope'; available: zx90_median/);
  await assert.rejects(metricScriptQuery(client, "metric_script", {}), /scriptId is required/);
});

test("the dashboard_template query previews a starter template without writing", async () => {
  const seen = [];
  const client = { previewDashboardTemplate: async (id) => { seen.push(id); return { template_id: id, panels: [], scripts_to_create: [] }; } };
  assert.equal((await metricScriptQuery(client, "dashboard_template", { templateId: "frequency-collision-map" })).template_id, "frequency-collision-map");
  assert.deepEqual(seen, ["frequency-collision-map"]);
  await assert.rejects(metricScriptQuery(client, "dashboard_template", {}), /templateId is required/);
});
