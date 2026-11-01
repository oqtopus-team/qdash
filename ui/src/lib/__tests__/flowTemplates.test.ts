import { describe, expect, it } from "vitest";

import { pickDefaultTemplate } from "@/lib/flowTemplates";
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
});
