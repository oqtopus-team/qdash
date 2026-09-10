import { describe, expect, it } from "vitest";
import type { TaskInfo, TaskResultResponse } from "@/schemas";
import { buildTaskPrefill } from "../task-prefill";

const task: TaskInfo = {
  name: "CheckRabi",
  class_name: "CheckRabi",
  file_path: "rabi.py",
  input_parameters: {
    frequency: { value_type: "float", unit: "GHz" },
    internal: { value_type: "float", user_override: "forbidden" },
  },
  run_parameters: {
    shots: { value: 100, value_type: "int" },
    sweep: { value: [0, 1, 10], value_type: "np.linspace" },
  },
};
function source(
  input_parameters: Record<string, unknown>,
  run_parameters: Record<string, unknown> = {},
) {
  return { input_parameters, run_parameters } as TaskResultResponse;
}

describe("current task form prefill", () => {
  it("preserves current defaults and fills compatible historical values", () => {
    expect(
      buildTaskPrefill(
        task,
        source({ frequency: { value: 5, value_type: "float", unit: "GHz" } }, { shots: 200 }),
      ),
    ).toEqual({
      input: { frequency: "5", internal: "" },
      run: { shots: "200", sweep: "[0,1,10]" },
      skipped: [],
    });
  });
  it("does not add deleted fields or apply forbidden overrides", () => {
    const result = buildTaskPrefill(task, source({ deleted: 1, internal: 2 }));
    expect(result.input).toEqual({ frequency: "", internal: "" });
    expect(result.skipped).toEqual(["input.deleted", "input.internal"]);
  });
  it.each([
    { value: 5000, value_type: "float", unit: "MHz" },
    { value: 5, value_type: "int", unit: "GHz" },
    { value: "5", value_type: "float", unit: "GHz" },
    { value: null },
  ])("does not fill incompatible input %j", (historical) => {
    const result = buildTaskPrefill(task, source({ frequency: historical }));
    expect(result.input.frequency).toBe("");
    expect(result.skipped).toEqual(["input.frequency"]);
  });
  it("keeps current run defaults for incompatible range shapes", () => {
    const result = buildTaskPrefill(
      task,
      source({}, { sweep: { value: [0, 1], value_type: "np.linspace" } }),
    );
    expect(result.run.sweep).toBe("[0,1,10]");
    expect(result.skipped).toEqual(["run.sweep"]);
  });
});
