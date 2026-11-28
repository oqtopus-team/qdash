import { describe, expect, it } from "vitest";
import type { TaskInfo } from "@/schemas";
import { buildTaskPrefill } from "../task-prefill";
import { buildTaskRunDefaults, buildTaskRunSchema } from "../taskRunSchema";

const task = {
  name: "test",
  class_name: "test",
  file_path: "test",
  input_parameters: {
    "a.b": { value_type: "int" },
    floating: { value_type: "float" },
    flag: { value_type: "bool" },
    items: { value_type: "list" },
    locked: { value_type: "int", user_override: "forbidden" },
  },
  run_parameters: { sweep: { value_type: "range", value: [0, 3, 1] } },
} as TaskInfo;
/** Builds a fresh form for each case. */
function form() {
  return buildTaskRunDefaults(task, buildTaskPrefill(task));
}

describe("task run schema", () => {
  it.each([
    [0, "1.5"],
    [1, "abc"],
    [2, "maybe"],
    [3, "["],
  ] as const)("reports invalid input %s", (index, value) => {
    const values = form();
    values.inputs[index].value = value;
    const result = buildTaskRunSchema(task).safeParse(values);
    expect(result.success).toBe(false);
    if (!result.success) expect(result.error.issues[0].path).toEqual(["inputs", index, "value"]);
  });
  it("rejects invalid sweeps and omits blank and forbidden inputs", () => {
    const values = form();
    values.inputs[4].value = "invalid";
    values.runs[0].parts = ["0", "4", "0"];
    expect(buildTaskRunSchema(task).safeParse(values).success).toBe(false);
    values.runs[0].parts = ["", "", ""];
    const result = buildTaskRunSchema(task).parse(values);
    expect(result.inputParameterOverrides).toEqual({});
    expect(result.runParameterOverrides).toEqual({});
  });
  it("wraps only sweeps whose type differs from the declaration", () => {
    const values = form();
    expect(buildTaskRunSchema(task).parse(values).runParameterOverrides).toEqual({
      sweep: [0, 3, 1],
    });
    values.runs[0].type = "list";
    values.runs[0].value = "[0,1,2]";
    expect(buildTaskRunSchema(task).parse(values).runParameterOverrides).toEqual({
      sweep: { value: [0, 1, 2], value_type: "list" },
    });
  });
});
