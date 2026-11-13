import { describe, expect, it } from "vitest";

import { resolveWorkspaceImagePath } from "../fileWorkspace";

describe("resolveWorkspaceImagePath", () => {
  const taskDocument = "one_qubit_coarse/CheckRabi/task.md";

  it("resolves an image next to the Markdown file", () => {
    expect(resolveWorkspaceImagePath(taskDocument, "./check_rabi_expected_1.png")).toBe(
      "one_qubit_coarse/CheckRabi/check_rabi_expected_1.png",
    );
    expect(resolveWorkspaceImagePath(taskDocument, "figures/q61.png")).toBe(
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
    expect(resolveWorkspaceImagePath(taskDocument, "https://example.com/a.png")).toBeNull();
    expect(resolveWorkspaceImagePath(taskDocument, "data:image/png;base64,AAAA")).toBeNull();
    expect(resolveWorkspaceImagePath(taskDocument, "/api/executions/figure?path=x")).toBeNull();
    expect(resolveWorkspaceImagePath(taskDocument, "../../../outside.png")).toBeNull();
  });
});
