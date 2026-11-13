import { describe, expect, it } from "vitest";
import {
  dropMoves,
  flowExplorerNodes,
  flowSpace,
  flowTreePath,
  parseFlowTreePath,
  renameMoves,
} from "../flowExplorer";
import type { FlowSummary } from "@/schemas";

function flow(name: string, folder = ""): FlowSummary {
  return {
    name,
    created_by: "mia",
    description: "",
    chip_id: "chip1",
    flow_function_name: "main",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-02T00:00:00Z",
    tags: [],
    folder,
  };
}

const flows = [flow("root_flow"), flow("daily_a", "daily"), flow("daily_t1", "daily/t1")];

describe("tree paths", () => {
  it("round-trips a flow through its tree path", () => {
    expect(flowTreePath(flow("x", "daily/t1"))).toBe("daily/t1/x.py");
    expect(flowTreePath(flow("x"))).toBe("x.py");
    expect(parseFlowTreePath("daily/t1/x.py")).toEqual({ folder: "daily/t1", name: "x" });
    expect(parseFlowTreePath("daily")).toEqual({ folder: "daily", name: null });
    expect(parseFlowTreePath("")).toEqual({ folder: "", name: null });
    expect(parseFlowTreePath(null)).toEqual({ folder: "", name: null });
    expect(flowSpace({ created_by: "" })).toBe("unknown");
  });

  it("builds nested folders, directories first, with empty folders kept", () => {
    const nodes = flowExplorerNodes(flows, ["weekly"]);
    expect(nodes.map((c) => `${c.type}:${c.path}`)).toEqual([
      "directory:daily",
      "directory:weekly",
      "file:root_flow.py",
    ]);
    expect(nodes[0]!.children!.map((c) => c.path)).toEqual(["daily/t1", "daily/daily_a.py"]);
    expect(nodes[1]!.children).toEqual([]);
  });
});

describe("dropMoves", () => {
  it("moves a dropped file into the target folder, and nothing when it is already there", () => {
    expect(dropMoves(flows, ["root_flow.py"], "daily/t1")).toEqual([
      { name: "root_flow", folder: "daily/t1" },
    ]);
    expect(dropMoves(flows, ["daily/daily_a.py"], null)).toEqual([{ name: "daily_a", folder: "" }]);
    expect(dropMoves(flows, ["daily/daily_a.py"], "daily")).toEqual([]);
  });

  it("moves a dropped folder with everything under it", () => {
    expect(dropMoves(flows, ["daily"], "weekly")).toEqual([
      { name: "daily_a", folder: "weekly/daily" },
      { name: "daily_t1", folder: "weekly/daily/t1" },
    ]);
    expect(dropMoves(flows, ["daily/t1"], null)).toEqual([{ name: "daily_t1", folder: "t1" }]);
    expect(dropMoves(flows, ["daily"], null)).toEqual([]);
  });

  it("refuses a file as target, the top as a dragged item, or a folder into itself", () => {
    expect(dropMoves(flows, ["root_flow.py"], "daily/daily_a.py")).toBeNull();
    expect(dropMoves(flows, [""], "daily")).toBeNull();
    expect(dropMoves(flows, ["daily"], "daily/t1")).toBeNull();
  });
});

describe("renameMoves", () => {
  it("re-files every flow under the renamed folder", () => {
    expect(renameMoves(flows, "daily", "nightly")).toEqual([
      { name: "daily_a", folder: "nightly" },
      { name: "daily_t1", folder: "nightly/t1" },
    ]);
    expect(renameMoves(flows, "daily/t1", "daily/t2")).toEqual([
      { name: "daily_t1", folder: "daily/t2" },
    ]);
    expect(renameMoves(flows, "weekly", "monthly")).toEqual([]);
  });

  it("refuses the top of the space and file paths", () => {
    expect(renameMoves(flows, "", "x")).toBeNull();
    expect(renameMoves(flows, "daily", "")).toBeNull();
    expect(renameMoves(flows, "daily/daily_a.py", "daily/b.py")).toBeNull();
  });
});
