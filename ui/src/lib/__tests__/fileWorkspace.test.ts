import { describe, expect, it } from "vitest";

import { resolveWorkspaceImagePath } from "../fileWorkspace";

describe("resolveWorkspaceImagePath", () => {
  const index = "one_qubit_coarse/CheckRabi/index.md";

  it("resolves an image next to the Markdown file", () => {
    expect(resolveWorkspaceImagePath(index, "./check_rabi_expected_1.png")).toBe(
      "one_qubit_coarse/CheckRabi/check_rabi_expected_1.png",
    );
    expect(resolveWorkspaceImagePath(index, "figures/q61.png")).toBe(
      "one_qubit_coarse/CheckRabi/figures/q61.png",
    );
  });

  it("follows parent directories inside the workspace", () => {
    expect(
      resolveWorkspaceImagePath(
        "one_qubit_coarse/CheckT1/examples/case.md",
        "../figures/a%20b.png",
      ),
    ).toBe("one_qubit_coarse/CheckT1/figures/a b.png");
  });

  it("leaves URLs, absolute paths, and escapes to the browser", () => {
    expect(resolveWorkspaceImagePath(index, "https://example.com/a.png")).toBeNull();
    expect(resolveWorkspaceImagePath(index, "data:image/png;base64,AAAA")).toBeNull();
    expect(resolveWorkspaceImagePath(index, "/api/executions/figure?path=x")).toBeNull();
    expect(resolveWorkspaceImagePath(index, "../../../outside.png")).toBeNull();
  });
});
