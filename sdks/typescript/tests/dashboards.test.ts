import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { QDashClient, QDashConfig } from "@oqtopus-team/qdash-client";
import {
  Dashboard,
  MetricScriptError,
  QDash,
  QDashApiError,
  Script,
  ScriptMetric,
  type MetricInfo,
} from "../src/index.js";

type Reply = { status?: number; body?: unknown };

/** A fetch that answers from a queue per "METHOD /path" and records every request. */
function server(routes: Record<string, Reply[]>) {
  const requests: { key: string; body: unknown }[] = [];
  const fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const request = new Request(input, init);
    const key = `${request.method} ${new URL(request.url).pathname.replace(/^\/api/, "")}`;
    const text = await request.text();
    requests.push({ key, body: text ? JSON.parse(text) : undefined });
    const reply = routes[key]?.shift();
    if (!reply) throw new Error(`unexpected request ${key}`);
    return new Response(JSON.stringify(reply.body ?? {}), {
      status: reply.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  const qdash = new QDash(
    new QDashClient(new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "token", projectId: "p" }), { fetch }),
  );
  return { qdash, requests };
}

const NOW = "2026-11-20T00:00:00Z";
const ZX90: MetricInfo = {
  id: "zx90_median",
  title: "Median ZX90 gate fidelity",
  unit: "%",
  target: "pair",
  hops: [1],
  parameters: {},
  has_legend: true,
};
const FREQ: MetricInfo = { id: "qubit_freq", title: "Frequency", unit: "GHz", target: "qubit" };

function scriptBody({ revision = 1, active = 1 as number | null, invalid = false } = {}) {
  return {
    script_id: "ms_1",
    project_id: "p",
    name: "ZX90",
    description: "",
    visibility: "project",
    status: invalid ? "invalid" : "valid",
    revision,
    active_revision: active,
    metrics: active ? [ZX90, FREQ] : [],
    template_id: null,
    owner_username: "alice",
    owner_user_id: "u1",
    can_edit: true,
    created_at: NOW,
    updated_at: NOW,
    source: `# ${revision}`,
    active_source: null,
    diagnostics: invalid ? [{ message: "invalid syntax", line: 1 }] : [],
    revisions: Array.from({ length: revision }, (_, index) => {
      const bad = invalid && index + 1 === revision;
      return { revision: index + 1, source: "", created_at: NOW, status: bad ? "invalid" : "valid", metrics: bad ? [] : [ZX90, FREQ] };
    }),
  };
}

function dashboardBody(version: number, panels: unknown[] = []) {
  return {
    dashboard_id: "dash_1",
    project_id: "p",
    name: "Ops",
    description: "",
    visibility: "project",
    chip_id: "64Qv3",
    panels: (panels as object[]).map((panel) => ({ ...panel, script_name: "ZX90", latest_revision: 2 })),
    owner_username: "alice",
    owner_user_id: "u1",
    can_edit: true,
    version,
    created_at: NOW,
    updated_at: NOW,
  };
}

describe("Script and Dashboard definitions", () => {
  it("read files as text and send nothing", async () => {
    const dir = await mkdtemp(join(tmpdir(), "qdash-sdk-"));
    const path = join(dir, "zx90_median.py");
    await writeFile(path, "raise SystemExit('never run')\n");
    const { requests } = server({});

    const script = await Script.fromFile(path, { visibility: "project" });
    const board = new Dashboard({ name: "Ops" });
    board.addMetric(new ScriptMetric("ms_1", 1, ZX90));

    expect([script.name, script.source, script.visibility]).toEqual(["zx90_median", "raise SystemExit('never run')\n", "project"]);
    expect(script.createRequest()).toEqual({ name: "zx90_median", source: "raise SystemExit('never run')\n", visibility: "project" });
    expect(requests).toEqual([]);
  });

  it("give panels readable IDs, declared hops and the editor's default layout", () => {
    const board = new Dashboard({ name: "Ops", visibility: "project" });
    board.addMarkdown("# Notes");
    const first = board.addMetric(new ScriptMetric("ms_1", 1, ZX90), { params: { min_samples: 3 } });
    board.addMetric(new ScriptMetric("ms_1", 1, ZX90), { period: 30, view: "table" });
    const qubit = board.addMetric(new ScriptMetric("ms_1", 1, FREQ));

    expect(board.panels.map((panel) => panel.panel_id)).toEqual(["markdown", "zx90_median", "zx90_median-2", "qubit_freq"]);
    expect(board.panels.map((panel) => panel.layout)).toEqual([
      { x: 0, y: 0, w: 12, h: 2 },
      { x: 0, y: 2, w: 6, h: 4 },
      { x: 0, y: 6, w: 6, h: 4 },
      { x: 0, y: 10, w: 6, h: 4 },
    ]);
    expect(first).toMatchObject({ type: "metric_script", title: "Median ZX90 gate fidelity" });
    expect(first.config).toEqual({
      script_id: "ms_1",
      script_revision: 1,
      metric_id: "zx90_median",
      period: { kind: "relative", days: 14 },
      params: { min_samples: 3 },
      view: "map",
      direction: "both",
      hops: [1],
    });
    // Wire compatible with servers before series metrics, whose config forbids extra keys.
    expect(board.panels.some((panel) => "targets" in (panel.config ?? {}))).toBe(false);
    expect(qubit.config?.hops).toEqual([1, 2]);
    expect(() => board.addMarkdown("x", { panelId: "markdown" })).toThrow(/already on the dashboard/);
  });

  it("give series metrics a timeseries panel of the selected targets only", () => {
    const trend = new ScriptMetric("ms_1", 1, {
      id: "zx90_daily_trend",
      title: "ZX90 gate fidelity trend",
      unit: "%",
      target: "pair",
      result: "series",
      hops: [1],
    });
    expect([trend.result, new ScriptMetric("ms_1", 1, ZX90).result]).toEqual(["series", "scalar"]);
    const board = new Dashboard({ name: "Trend" });
    const panel = board.addMetric(trend, { targets: ["0>1", "1>0"], params: { interval: "week" } });
    expect(panel.config).toMatchObject({ view: "timeseries", targets: ["0>1", "1>0"], params: { interval: "week" } });
    expect(() => board.addMetric(trend)).toThrow(/1 to 16 targets/);
    expect(() => board.addMetric(trend, { targets: Array.from({ length: 17 }, (_, i) => `${i}>${i + 1}`) })).toThrow(/1 to 16/);
    expect(() => board.addMetric(trend, { targets: ["0>1"], view: "map" })).toThrow(/view "timeseries"/);
    expect(() => board.addMetric(new ScriptMetric("ms_1", 1, ZX90), { view: "timeseries" })).toThrow(/"map" or "table"/);
    expect(() => board.addMetric(new ScriptMetric("ms_1", 1, ZX90), { targets: ["0>1"] })).toThrow(/only to series/);
  });
});

describe("qdash.scripts", () => {
  it("binds a save to the revision it produced and refuses an invalid one", async () => {
    const { qdash, requests } = server({
      "POST /metric-scripts": [{ status: 201, body: scriptBody() }],
      "PATCH /metric-scripts/ms_1": [{ body: scriptBody({ revision: 2, active: 1, invalid: true }) }],
    });

    const created = await qdash.scripts.create(new Script({ name: "ZX90", source: "# 1", visibility: "project" }));
    expect(created.metric("zx90_median")).toEqual(new ScriptMetric("ms_1", 1, ZX90));
    expect(() => created.metric("missing")).toThrow(/declares: zx90_median, qubit_freq/);

    const broken = await qdash.scripts.update(created, new Script({ name: "ZX90", source: "def broken(:" }));
    expect(requests[1]?.body).toEqual({ name: "ZX90", source: "def broken(:", expected_revision: 1 });
    expect([broken.revision, broken.valid, broken.diagnostics]).toEqual([2, false, ["line 1: invalid syntax"]]);
    let error: unknown;
    try {
      broken.metric("zx90_median");
    } catch (caught) {
      error = caught;
    }
    expect(error).toBeInstanceOf(MetricScriptError);
    expect(error).toMatchObject({ scriptId: "ms_1", revision: 2 });
  });
});

describe("qdash.dashboards", () => {
  const panel = {
    panel_id: "zx90_median",
    type: "metric_script",
    title: "ZX90",
    layout: { x: 0, y: 0, w: 6, h: 4 },
    config: { script_id: "ms_1", script_revision: 1, metric_id: "zx90_median" },
  };

  it("sends the version an update is based on and surfaces a stale save", async () => {
    const { qdash, requests } = server({
      "GET /dashboards/dash_1": [{ body: dashboardBody(4, [panel]) }, { body: dashboardBody(4, [panel]) }],
      "PATCH /dashboards/dash_1": [
        { body: dashboardBody(5, [panel]) },
        { status: 409, body: { detail: "Dashboard was changed by another save" } },
      ],
    });

    const current = await qdash.dashboards.get("dash_1");
    const edited = current.edit();
    const saved = await qdash.dashboards.update(current, edited);

    expect(requests[1]?.body).toEqual({
      name: "Ops",
      description: "",
      visibility: "project",
      chip_id: "64Qv3",
      panels: [panel],
      expected_version: 4,
    });
    expect(saved.version).toBe(5);
    const stale = qdash.dashboards.update("dash_1", edited);
    await expect(stale).rejects.toBeInstanceOf(QDashApiError);
    await expect(stale).rejects.toMatchObject({ statusCode: 409 });
    expect(requests.slice(-2).map((request) => request.key)).toEqual(["GET /dashboards/dash_1", "PATCH /dashboards/dash_1"]);
    expect((requests.at(-1)?.body as { expected_version: number }).expected_version).toBe(4);
  });

  it("creates with only the settings given", async () => {
    const { qdash, requests } = server({ "POST /dashboards": [{ status: 201, body: dashboardBody(0) }] });
    const saved = await qdash.dashboards.create(new Dashboard({ name: "Ops" }));
    expect(requests[0]?.body).toEqual({ name: "Ops", panels: [] });
    expect(saved.dashboardId).toBe("dash_1");
  });
});
