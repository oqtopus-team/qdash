import { z } from "zod";
import type { TaskInfo } from "@/schemas";
import {
  expandSweep,
  isSweepValueType,
  parseTaskParameter,
  type SweepFormType,
} from "@/lib/utils/task-parameters";
import { sweepFieldValue } from "./SweepParameterField";
import type { TaskPrefill } from "./task-prefill";

/** Builds initial form values in definition order. */
export function buildTaskRunDefaults(task: TaskInfo, prefill: TaskPrefill) {
  return {
    inputs: Object.keys(task.input_parameters ?? {}).map((name) => ({
      name,
      value: prefill.input[name] ?? "",
    })),
    runs: Object.keys(task.run_parameters ?? {}).map((name) => {
      const value = prefill.run[name] ?? "";
      const runType = prefill.runTypes[name];
      let parts = ["", "", ""];
      if (runType !== undefined && runType !== "list") {
        try {
          const parsed: unknown = JSON.parse(value);
          if (Array.isArray(parsed) && parsed.length === 3) parts = parsed.map(String);
        } catch {
          /* Empty or malformed values start blank. */
        }
      }
      return { name, value, type: prefill.runTypes[name] ?? ("list" as SweepFormType), parts };
    }),
    reconfigure: false,
    updateCalibrationParameters: false,
  };
}

/** Creates a task-specific validator and converts valid values into request overrides. */
export function buildTaskRunSchema(task: TaskInfo) {
  return z
    .object({
      inputs: z.array(z.object({ name: z.string(), value: z.string() })),
      runs: z.array(
        z.object({
          name: z.string(),
          value: z.string(),
          type: z.enum(["list", "range", "np.arange", "np.linspace", "np.logspace"]),
          parts: z.array(z.string()),
        }),
      ),
      reconfigure: z.boolean(),
      updateCalibrationParameters: z.boolean(),
    })
    .transform((values, ctx) => {
      const inputParameterOverrides: Record<string, unknown> = {};
      const runParameterOverrides: Record<string, unknown> = {};
      values.inputs.forEach((field, index) => {
        const definition = task.input_parameters?.[field.name];
        if (!definition || definition.user_override === "forbidden" || !field.value.trim()) return;
        try {
          inputParameterOverrides[field.name] = parseTaskParameter(
            field.value,
            definition.value_type ?? "float",
          );
        } catch (error) {
          ctx.addIssue({
            code: "custom",
            path: ["inputs", index, "value"],
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });
      values.runs.forEach((field, index) => {
        const definition = task.run_parameters?.[field.name];
        if (!definition) return;
        try {
          if (!isSweepValueType(definition.value_type)) {
            if (field.value.trim())
              runParameterOverrides[field.name] = parseTaskParameter(
                field.value,
                definition.value_type,
              );
            return;
          }
          if (
            field.type === "list" ? !field.value.trim() : field.parts.every((part) => !part.trim())
          )
            return;
          const value = sweepFieldValue(field.type, field.parts, field.value);
          if (value === null || expandSweep(field.type, value) === null)
            throw new Error(`Enter numbers that produce a ${field.type} sweep for ${field.name}`);
          runParameterOverrides[field.name] =
            field.type === definition.value_type ? value : { value, value_type: field.type };
        } catch (error) {
          ctx.addIssue({
            code: "custom",
            path: ["runs", index, "value"],
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });
      return { ...values, inputParameterOverrides, runParameterOverrides };
    });
}
export type TaskRunInput = z.input<ReturnType<typeof buildTaskRunSchema>>;
export type TaskRunOutput = z.output<ReturnType<typeof buildTaskRunSchema>>;
