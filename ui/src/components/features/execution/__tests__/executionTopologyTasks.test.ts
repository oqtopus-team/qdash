import { describe, expect, it } from "vitest";

import type { Task } from "@/schemas";

import {
  filterTaskGroupsByName,
  groupTasksByEntity,
  resolveInitialTaskIndex,
} from "@/components/features/execution/executionTopologyTasks";

function task(name: string, qid: string): Task {
  return { name, qid, task_id: `${name}-${qid}` };
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
