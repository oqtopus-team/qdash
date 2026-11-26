import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

import { describe, expect, it } from "vitest";

import * as calibration from "../src/calibration.js";
import {
  calibrationDefinitionsSource,
  calibrationSpec,
  calibrationStep,
  couplingTargets,
  customOneQubit,
  filterByMetric,
  generateCRSchedule,
  muxTargets,
  qubitTargets,
  STEP_TYPES,
  sweep,
  taskCall,
  type CalibrationDefinitions,
  type CalibrationStepType,
} from "../src/calibration.js";
import * as sdk from "../src/index.js";

type Json = Record<string, unknown>;
interface Case {
  name: string;
  kind: "task_call" | "targets" | "step" | "spec";
  type?: string;
  fields?: Json;
  targets?: { type: string; fields: Json };
  steps?: { type: string; fields: Json }[];
  options?: Json;
  expected?: unknown;
}
const shared = JSON.parse(
  readFileSync(new URL("../../testdata/calibration_definitions.json", import.meta.url), "utf8"),
) as {
  task_call_fields: string[];
  step_fields: Record<string, string[]>;
  valid: Case[];
  server_only: Case[];
  invalid: Case[];
};

/** The fixture's `$sweep` and `$task` markers, built by `defs`. */
function materialize(defs: CalibrationDefinitions, value: unknown): unknown {
  if (Array.isArray(value)) return value.map((entry) => materialize(defs, entry));
  if (typeof value === "object" && value !== null) {
    const keys = Object.keys(value);
    if (keys.length === 1 && keys[0] === "$sweep") {
      const [constructor, ...args] = (value as { $sweep: [keyof CalibrationDefinitions["sweep"], ...number[]] }).$sweep;
      return (defs.sweep[constructor] as (...values: number[]) => unknown)(...args);
    }
    if (keys.length === 1 && keys[0] === "$task") {
      return defs.taskCall(materialize(defs, (value as { $task: unknown }).$task) as never);
    }
    return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, materialize(defs, entry)]));
  }
  return value;
}

function targets(defs: CalibrationDefinitions, type: string, fields: Json): unknown {
  if (type === "QubitTargets") return defs.qubitTargets(fields.qids as string[]);
  if (type === "MuxTargets") return defs.muxTargets(fields.mux_ids as number[], { exclude_qids: fields.exclude_qids as string[] | undefined });
  if (type === "CouplingTargets") return defs.couplingTargets(fields.pairs as string[][]);
  throw new Error(`unknown targets ${type}`);
}

/** What `defs` writes for one case. */
function build(defs: CalibrationDefinitions, entry: Case): unknown {
  const fields = materialize(defs, entry.fields) as Json;
  switch (entry.kind) {
    case "task_call":
      return defs.taskCall(fields as never);
    case "targets":
      return targets(defs, entry.type!, fields);
    case "step":
      return defs.calibrationStep(entry.type as CalibrationStepType, fields as never);
    case "spec":
      return defs.calibrationSpec(
        targets(defs, entry.targets!.type, materialize(defs, entry.targets!.fields) as Json) as never,
        entry.steps!.map((step) => defs.calibrationStep(step.type as CalibrationStepType, materialize(defs, step.fields) as never)),
        materialize(defs, entry.options) as never,
      );
  }
}

// The module's own builders, and the same implementation evaluated from its source in a fresh
// global scope, as Code Mode evaluates it.
const sandboxed = runInNewContext(calibrationDefinitionsSource(), {}) as CalibrationDefinitions;
const implementations: [string, CalibrationDefinitions][] = [
  ["module", calibration as unknown as CalibrationDefinitions],
  ["source", sandboxed],
];

describe.each(implementations)("shared calibration definition cases (%s)", (_label, defs) => {
  it.each([...shared.valid, ...shared.server_only].map((entry) => [entry.name, entry] as const))(
    "builds %s",
    (_name, entry) => {
      // Through JSON, as it is sent.
      expect(JSON.parse(JSON.stringify(build(defs, entry)))).toEqual(entry.expected);
    },
  );

  it.each(shared.invalid.map((entry) => [entry.name, entry] as const))("refuses %s", (_name, entry) => {
    let error: unknown;
    try {
      build(defs, entry);
    } catch (caught) {
      error = caught;
    }
    expect(error).toBeDefined();
    // The sandboxed copy throws its own realm's errors.
    expect(["TypeError", "RangeError"]).toContain((error as Error).constructor.name);
  });

  it("accepts exactly the Python definitions' fields", () => {
    const fieldsOf = (run: () => unknown): string[] => {
      try {
        run();
      } catch (error) {
        const match = /its fields are (.*)$/.exec((error as Error).message);
        if (match) return match[1]!.split(", ");
        throw error;
      }
      throw new Error("an unknown field was accepted");
    };
    expect(fieldsOf(() => defs.taskCall({ name: "CheckT1", unknown_field: 1 } as never))).toEqual(shared.task_call_fields);
    expect([...defs.STEP_TYPES]).toEqual(Object.keys(shared.step_fields));
    for (const [type, fields] of Object.entries(shared.step_fields)) {
      expect(fieldsOf(() => defs.calibrationStep(type as CalibrationStepType, { unknown_field: 1 } as never))).toEqual(fields);
    }
  });
});

describe("calibration builders", () => {
  it("treat undefined as unset and write null and defaults as given", () => {
    expect(taskCall("CheckT1", { call_id: undefined, run: undefined, on_failure: null })).toEqual({ name: "CheckT1", on_failure: null });
    expect(JSON.stringify(customOneQubit({ tasks: [taskCall("CheckT1")], rounds: undefined }))).toBe(
      '{"type":"CustomOneQubit","tasks":[{"name":"CheckT1"}]}',
    );
    expect(generateCRSchedule({ max_parallel_ops: 10 })).toEqual({ type: "GenerateCRSchedule", max_parallel_ops: 10 });
    expect(generateCRSchedule()).toEqual({ type: "GenerateCRSchedule" });
  });

  it("take a task name with its fields, or one object, but not both names", () => {
    expect(taskCall("CheckT1", { call_id: "t1" })).toEqual(taskCall({ name: "CheckT1", call_id: "t1" }));
    expect(() => taskCall("CheckT1", { name: "CheckT2" } as never)).toThrow(TypeError);
    expect(() => (taskCall as (...args: unknown[]) => unknown)({ name: "CheckT1" }, {})).toThrow(TypeError);
  });

  it("copy what they were given, so later edits to the input do not change a step", () => {
    const run = { shots: 1 };
    const tasks = [{ name: "CheckT1", run }];
    const step = customOneQubit({ tasks });
    run.shots = 2;
    tasks.push({ name: "CheckT2", run });
    expect(step).toEqual({ type: "CustomOneQubit", tasks: [{ name: "CheckT1", run: { shots: 1 } }] });
  });

  it("refuse a sweep under input but keep a hand-written wire value", () => {
    expect(() => taskCall("CheckT1", { input: { qubit_frequency: sweep.values(1, 2) } })).toThrow(/put generated experiment ranges under run/);
    expect(taskCall("CheckT1", { input: { qubit_frequency: { value: 7.9, value_type: "float" } } }).input).toEqual({
      qubit_frequency: { value: 7.9, value_type: "float" },
    });
  });

  it("name the builder and field in their errors, and refuse a type in the fields", () => {
    expect(() => filterByMetric({ metric: "t1" } as never)).toThrow("filterByMetric: needs threshold");
    expect(() => customOneQubit({ tasks: ["CheckT1"] } as never)).toThrow(/write it as taskCall\("CheckT1"\)/);
    expect(() => calibrationStep("FilterByStatus", { type: "FilterByStatus" } as never)).toThrow(/leave out type/);
    expect(() => calibrationStep("Nope" as never)).toThrow(/unknown step type "Nope"/);
    expect(() => filterByMetric({ metric: "t1", threshold: Number.NaN })).toThrow(TypeError);
  });

  it("keep the earlier target and spec options", () => {
    expect(muxTargets([3], { excludeQids: ["5"] })).toEqual({ mux_ids: [3], exclude_qids: ["5"] });
    expect(() => muxTargets([3], { excludeQids: ["5"], exclude_qids: ["6"] })).toThrow(TypeError);
    const spec = calibrationSpec(qubitTargets(["0"]), [customOneQubit({ tasks: [{ name: "CheckT1" }] })], {
      defaultRunParameters: { shots: 1 },
      backendName: "qubex",
    });
    expect(spec).toEqual({
      spec_version: 2,
      targets: { qids: ["0"] },
      steps: [{ type: "CustomOneQubit", tasks: [{ name: "CheckT1" }] }],
      default_run_parameters: { shots: 1 },
    });
    expect(() => calibrationSpec(qubitTargets(["0"]), "x" as never)).toThrow(TypeError);
    expect(() => calibrationSpec(qubitTargets(["0"]), [], { label: "x" } as never)).toThrow(/has no option "label"/);
    expect(couplingTargets([["0", "1"]])).toEqual({ pairs: [["0", "1"]] });
  });

  it("are frozen", () => {
    expect(Object.isFrozen(sweep)).toBe(true);
    expect(Object.isFrozen(STEP_TYPES)).toBe(true);
    expect(Object.isFrozen(sandboxed)).toBe(true);
  });

  it("are the same functions from the package root and the earlier definitions module", async () => {
    const definitions = await import("../src/definitions.js");
    for (const name of ["calibrationSpec", "customOneQubit", "muxTargets", "qubitTargets", "sweep"] as const) {
      expect(definitions[name]).toBe(calibration[name]);
      expect(sdk[name]).toBe(calibration[name]);
    }
    for (const name of Object.keys(sandboxed)) {
      expect(sdk).toHaveProperty(name);
      expect(calibration).toHaveProperty(name);
    }
  });
});

describe("the calibration source for sandboxes", () => {
  it("references nothing outside itself but the language's own globals", () => {
    const builtins = new Set(["Object", "Array", "JSON", "Number", "String", "TypeError", "RangeError", "WeakSet", "Set", "RegExp", "Error", "undefined"]);
    const free = new Set<string>();
    // A sloppy-mode \`with\` scope sees every free identifier the builders look up as they run.
    const scope = new Proxy({} as Record<PropertyKey, unknown>, {
      has: (_target, key) => {
        if (typeof key === "string" && !builtins.has(key)) free.add(key);
        return false;
      },
    });
    const traced = new Function("scope", `with (scope) { return ${calibrationDefinitionsSource()}; }`)(scope) as CalibrationDefinitions;
    for (const entry of [...shared.valid, ...shared.server_only]) build(traced, entry);
    for (const entry of shared.invalid) expect(() => build(traced, entry)).toThrow();
    expect([...free]).toEqual([]);
  });

  it("is an expression that evaluates to the builders", () => {
    const source = calibrationDefinitionsSource();
    expect(source.startsWith("(")).toBe(true);
    expect(source).not.toMatch(/\b(fetch|process|require|import|globalThis)\b/);
    expect(Object.keys(sandboxed).sort()).toEqual(Object.keys(runInNewContext(source, {}) as object).sort());
  });
});

describe("the calibration package export", () => {
  const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8")) as {
    exports: Record<string, { types: string; import: string }>;
    scripts: { build: string };
  };

  it("is published as @oqtopus-team/qdash-sdk/calibration and built as its own entry", () => {
    expect(manifest.exports["./calibration"]).toEqual({ types: "./dist/calibration.d.ts", import: "./dist/calibration.js" });
    expect(manifest.scripts.build).toMatch(/tsup [^&]*src\/calibration\.ts/);
  });

  it("imports nothing at runtime: only types from the generated API", () => {
    const source = readFileSync(new URL("../src/calibration.ts", import.meta.url), "utf8");
    const imports = [...source.matchAll(/^import\s+(type\s+)?[^;]*?from\s+"([^"]+)";/gms)].map((match) => [Boolean(match[1]), match[2]]);
    expect(imports.length).toBeGreaterThan(0);
    for (const [typeOnly, from] of imports) expect({ from, typeOnly }).toEqual({ from, typeOnly: true });
    expect(source).not.toMatch(/^\s*export\s+\*\s+from/m);
    expect(source).not.toMatch(/\bimport\(/);
  });
});
