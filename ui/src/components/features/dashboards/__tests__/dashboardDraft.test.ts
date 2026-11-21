import { describe, expect, it } from "vitest";

import type { DashboardPanelResponse } from "@/schemas";

import {
  EMPTY_NEW_DASHBOARD,
  parseDashboardDraft,
  serializeDashboardDraft,
} from "../dashboardDraft";

const scriptPanel: DashboardPanelResponse = {
  config: { script_id: "ms_1", script_revision: 2, metric_id: "zx90" },
  layout: { h: 4, w: 6, y: 0, x: 0 },
  title: "ZX90",
  type: "metric_script",
  panel_id: "p1",
  script_name: "ZX90 median",
  latest_revision: 3,
};

describe("dashboard drafts", () => {
  it("writes panels in a fixed key order without the response's script annotations", () => {
    const code = serializeDashboardDraft([scriptPanel], null);
    expect(code.endsWith("\n")).toBe(true);
    const parsed = JSON.parse(code);
    expect(Object.keys(parsed)).toEqual(["panels"]);
    expect(Object.keys(parsed.panels[0])).toEqual([
      "panel_id",
      "type",
      "title",
      "layout",
      "config",
    ]);
    expect(parsed.panels[0]).not.toHaveProperty("script_name");
    expect(Object.keys(JSON.parse(serializeDashboardDraft([], EMPTY_NEW_DASHBOARD)))).toEqual([
      "name",
      "description",
      "chip_id",
      "template_id",
      "panels",
    ]);
  });

  it("round-trips and keeps the newer-revision hint of an unchanged script panel", () => {
    const parsed = parseDashboardDraft(serializeDashboardDraft([scriptPanel], null), false, [
      scriptPanel,
    ]);
    expect(parsed.ok && parsed.panels[0]).toMatchObject({
      script_name: "ZX90 median",
      latest_revision: 3,
    });
    // A panel pointed at another script loses the hint of the old one.
    const moved = parseDashboardDraft(
      JSON.stringify({ panels: [{ ...scriptPanel, config: { script_id: "ms_2" } }] }),
      false,
      [scriptPanel],
    );
    expect(moved.ok && moved.panels[0].latest_revision).toBeUndefined();
  });

  it("refuses sharing, unknown fields, duplicate IDs and panels off the grid", () => {
    const panel = { panel_id: "a", type: "markdown", layout: { x: 0, y: 0, w: 12, h: 2 } };
    const problem = (draft: unknown, isNew = false) => {
      const parsed = parseDashboardDraft(JSON.stringify(draft), isNew, []);
      return parsed.ok ? null : parsed.problem;
    };
    expect(problem({ panels: [panel], visibility: "project" }, true)).toMatch(/changes sharing/);
    expect(problem({ name: "x", panels: [panel] })).toMatch(/unknown field "name"/);
    expect(problem({ panels: [panel, panel] })).toMatch(/unique ID/);
    expect(problem({ panels: [{ ...panel, layout: { x: 6, y: 0, w: 7, h: 2 } }] })).toMatch(
      /12-column grid/,
    );
    expect(problem({ panels: [{ ...panel, type: "chart" }] })).toMatch(/unknown type/);
    // A missing list would otherwise read as "remove every panel".
    expect(problem({})).toMatch(/no panels list/);
    expect(problem({ name: "x" }, true)).toMatch(/no panels list/);
    expect(problem({ panels: [panel] })).toBeNull();
  });

  it("reads a new dashboard's name, chip and template", () => {
    const parsed = parseDashboardDraft(
      JSON.stringify({
        name: "Collisions",
        chip_id: " ",
        template_id: "frequency-collision-map",
        panels: [],
      }),
      true,
      [],
    );
    expect(parsed).toEqual({
      ok: true,
      panels: [],
      meta: {
        name: "Collisions",
        description: "",
        chip_id: null,
        template_id: "frequency-collision-map",
      },
    });
  });
});
