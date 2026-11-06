import { describe, expect, it } from "vitest";

import { newFlowTemplateHref, pickDefaultTemplate } from "@/lib/flowTemplates";
import type { FlowTemplate } from "@/schemas";

function template(id: string, backend = "qubex"): FlowTemplate {
  return {
    id,
    name: id,
    description: "",
    category: "basic",
    backend,
    filename: `${id}.py`,
    function_name: id,
  };
}

describe("pickDefaultTemplate", () => {
  it("prefers the simple template", () => {
    expect(pickDefaultTemplate([template("bringup"), template("simple")])?.id).toBe("simple");
  });

  it("falls back to the first template of the backend", () => {
    expect(pickDefaultTemplate([template("fake_calibration", "fake")])?.id).toBe(
      "fake_calibration",
    );
  });

  it("returns null when the backend has no templates", () => {
    expect(pickDefaultTemplate([])).toBeNull();
  });

  it("opens the requested template when the backend lists it", () => {
    const templates = [template("simple"), template("bringup")];
    expect(pickDefaultTemplate(templates, "bringup")?.id).toBe("bringup");
    expect(pickDefaultTemplate(templates, "fake_calibration")?.id).toBe("simple");
  });
});

describe("newFlowTemplateHref", () => {
  it("preserves the created chip in the editor URL", () => {
    const url = new URL(
      newFlowTemplateHref("fake", "fake_calibration", "fake-4q"),
      "http://localhost",
    );
    expect(url.searchParams.get("chip_id")).toBe("fake-4q");
  });
  it("names the backend and the template", () => {
    expect(newFlowTemplateHref("fake", "fake_calibration")).toBe(
      "/workflow/new?backend=fake&template=fake_calibration",
    );
  });
});
