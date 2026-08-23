import { describe, expect, it } from "vitest";

import type { Task } from "@/schemas";

import {
  filterTaskGroupsByName,
  groupTasksByEntity,
  resolveInitialTaskIndex,
  selectTaskNeighborhood,
} from "@/components/features/execution/executionTopologyTasks";

function task(name: string, qid: string): Task {
  return { name, qid, task_id: `${name}-${qid}` };
}

function chain(names: string[], qid = "0"): Task[] {
  return names.map((name, index) => ({
    ...task(name, qid),
    upstream_id: index === 0 ? "" : `${names[index - 1]}-${qid}`,
  }));
}

const tasks: Task[] = [
  task("CheckStatus", "Q00"),
  task("CheckRabi", "Q00"),
  task("CreateHPIPulse", "Q00"),
  task("CheckRabi", "1"),
  task("CheckCrossResonance", "2-1"),
  task("CheckStatus", "1-2"),
];

describe("groupTasksByEntity", () => {
  it("keeps every task of a qubit in execution order", () => {
    const { oneQubit } = groupTasksByEntity(tasks);

    expect(oneQubit["0"].map((entry) => entry.name)).toEqual([
      "CheckStatus",
      "CheckRabi",
      "CreateHPIPulse",
    ]);
    expect(oneQubit["1"].map((entry) => entry.name)).toEqual(["CheckRabi"]);
  });

  it("normalizes coupling ids so both directions share one group", () => {
    const { coupling } = groupTasksByEntity(tasks);

    expect(Object.keys(coupling)).toEqual(["1-2"]);
    expect(coupling["1-2"].map((entry) => entry.name)).toEqual([
      "CheckCrossResonance",
      "CheckStatus",
    ]);
  });
});

describe("filterTaskGroupsByName", () => {
  it("keeps only the entities that ran the selected task", () => {
    const { oneQubit } = groupTasksByEntity(tasks);
    const filtered = filterTaskGroupsByName(oneQubit, "CreateHPIPulse");

    expect(Object.keys(filtered)).toEqual(["0"]);
    expect(filtered["0"]).toHaveLength(1);
  });

  it("returns nothing when no task is selected", () => {
    const { oneQubit } = groupTasksByEntity(tasks);

    expect(filterTaskGroupsByName(oneQubit, "")).toEqual({});
  });
});

describe("selectTaskNeighborhood", () => {
  const linked = chain(["CheckFineChevron", "CheckRabi", "CreateHPIPulse", "CheckT1"]);

  it("keeps the upstream and downstream tasks of the selected one", () => {
    expect(selectTaskNeighborhood(linked, "CheckRabi").map((entry) => entry.name)).toEqual([
      "CheckFineChevron",
      "CheckRabi",
      "CreateHPIPulse",
    ]);
  });

  it("drops tasks that are more than one dependency away", () => {
    expect(selectTaskNeighborhood(linked, "CheckFineChevron").map((entry) => entry.name)).toEqual([
      "CheckFineChevron",
      "CheckRabi",
    ]);
    expect(selectTaskNeighborhood(linked, "CheckT1").map((entry) => entry.name)).toEqual([
      "CreateHPIPulse",
      "CheckT1",
    ]);
  });

  it("keeps every branch that depends on the selected task", () => {
    const branched: Task[] = [
      { ...task("CheckRabi", "0"), upstream_id: "" },
      { ...task("CreateHPIPulse", "0"), upstream_id: "CheckRabi-0" },
      { ...task("CheckT1", "0"), upstream_id: "CheckRabi-0" },
    ];

    expect(selectTaskNeighborhood(branched, "CheckRabi")).toHaveLength(3);
    expect(selectTaskNeighborhood(branched, "CreateHPIPulse").map((entry) => entry.name)).toEqual([
      "CheckRabi",
      "CreateHPIPulse",
    ]);
  });

  it("falls back to the adjacent tasks when the execution has no upstream links", () => {
    const { oneQubit } = groupTasksByEntity(tasks);

    expect(selectTaskNeighborhood(oneQubit["0"], "CheckRabi").map((entry) => entry.name)).toEqual([
      "CheckStatus",
      "CheckRabi",
      "CreateHPIPulse",
    ]);
  });

  it("returns the whole group when the task is missing or unset", () => {
    expect(selectTaskNeighborhood(linked, "CheckT2Echo")).toHaveLength(linked.length);
    expect(selectTaskNeighborhood(linked, "")).toHaveLength(linked.length);
  });
});

describe("resolveInitialTaskIndex", () => {
  it("points at the task selected in the filter", () => {
    const { oneQubit } = groupTasksByEntity(tasks);

    expect(resolveInitialTaskIndex(oneQubit["0"], "CheckRabi")).toBe(1);
  });

  it("falls back to the first task when the name is absent", () => {
    const { oneQubit } = groupTasksByEntity(tasks);

    expect(resolveInitialTaskIndex(oneQubit["0"], "CheckT1")).toBe(0);
    expect(resolveInitialTaskIndex(oneQubit["0"], "")).toBe(0);
  });
});
