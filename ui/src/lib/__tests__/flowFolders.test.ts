import { describe, expect, it } from "vitest";
import {
  buildFlowTree,
  countFlows,
  folderPaths,
  folderSegments,
  groupFlowsByCreator,
  normalizeFolderPath,
} from "../flowFolders";
import type { FlowSummary } from "@/schemas";

function flow(name: string, created_by: string, folder = ""): FlowSummary {
  return {
    name,
    created_by,
    folder,
    description: "",
    chip_id: "chip1",
    flow_function_name: "main",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-02T00:00:00Z",
    tags: [],
  };
}

describe("groupFlowsByCreator", () => {
  it("puts the signed-in user's folder first, then the others by name", () => {
    const folders = groupFlowsByCreator(
      [flow("a", "zoe"), flow("b", "bob"), flow("c", "mia"), flow("d", "zoe")],
      "mia",
    );
    expect(folders.map((f) => f.creator)).toEqual(["mia", "bob", "zoe"]);
    expect(folders[0]!.mine).toBe(true);
    expect(folders[1]!.mine).toBe(false);
    // Flows keep the order the API gave within a folder.
    expect(folders[2]!.flows.map((f) => f.name)).toEqual(["a", "d"]);
  });

  it("sorts by name alone when the user owns nothing, and names a missing creator", () => {
    const folders = groupFlowsByCreator([flow("a", "zoe"), flow("b", "")], null);
    expect(folders.map((f) => f.creator)).toEqual(["unknown", "zoe"]);
    expect(folders.every((f) => !f.mine)).toBe(true);
    expect(groupFlowsByCreator([], "mia")).toEqual([]);
  });
});

describe("buildFlowTree", () => {
  it("nests flows by their folder path, subfolders in name order, root flows at the top", () => {
    const tree = buildFlowTree([
      flow("a", "mia", "weekly"),
      flow("b", "mia"),
      flow("c", "mia", "daily/t1"),
      flow("d", "mia", "daily"),
      flow("e", "mia", "/daily/t1/"),
    ]);
    expect(tree.flows.map((f) => f.name)).toEqual(["b"]);
    expect(tree.children.map((c) => c.path)).toEqual(["daily", "weekly"]);
    const daily = tree.children[0]!;
    expect(daily.flows.map((f) => f.name)).toEqual(["d"]);
    expect(daily.children.map((c) => c.path)).toEqual(["daily/t1"]);
    expect(daily.children[0]!.flows.map((f) => f.name)).toEqual(["c", "e"]);
    expect(groupFlowsByCreator([flow("a", "mia", "x")], "mia")[0]!.root.children).toHaveLength(1);
  });

  it("treats a blank or missing folder as the root", () => {
    expect(folderSegments(undefined)).toEqual([]);
    expect(folderSegments(" / ")).toEqual([]);
    expect(folderSegments("a//b")).toEqual(["a", "b"]);
  });
});

describe("empty folders and path helpers", () => {
  it("keeps a creator's empty folders in the tree and lists every path", () => {
    const empty = new Map([
      ["mia", ["weekly", "daily/t2"]],
      ["new_user", ["inbox"]],
    ]);
    const folders = groupFlowsByCreator([flow("c", "mia", "daily/t1")], "mia", empty);
    expect(folders.map((f) => f.creator)).toEqual(["mia", "new_user"]);
    expect(folderPaths(folders[0]!.root)).toEqual(["daily", "daily/t1", "daily/t2", "weekly"]);
    expect(countFlows(folders[0]!.root)).toBe(1);
    expect(folders[1]!.flows).toEqual([]);
    expect(folderPaths(folders[1]!.root)).toEqual(["inbox"]);
  });

  it("normalizes typed folder paths the way the API does", () => {
    expect(normalizeFolderPath("")).toBe("");
    expect(normalizeFolderPath(" / ")).toBe("");
    expect(normalizeFolderPath("/daily/t1/")).toBe("daily/t1");
    expect(normalizeFolderPath("daily//t1")).toBe("daily/t1");
    expect(normalizeFolderPath("bad name")).toBeNull();
    expect(normalizeFolderPath("../x")).toBeNull();
  });
});
