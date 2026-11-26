import assert from "node:assert/strict";
import test from "node:test";
import { runInNewContext } from "node:vm";

// The SDK's dedicated export, resolved through its package.json and built dist.
import * as calibration from "@oqtopus-team/qdash-sdk/calibration";

import { installQDashToolPolicy } from "../.test-dist/lib/script-policy.js";
import {
  directivePrologueEnd,
  prepareScriptSource,
  SCRIPT_HELPERS_GLOBAL,
  scriptPreludeLine,
  withScriptHelpers,
} from "../.test-dist/lib/script-prelude.js";
import { DEFAULT_SCRIPT_TIMEOUT_MS, QDASH_TOOL_NAMESPACE, withScriptDeadline } from "../.test-dist/lib/tool-policy.js";
import { QDASH_SCRIPT_GUIDELINE } from "../.test-dist/lib/qdash-guidance.js";

const OPTIONS = `// @options: {"timeout_ms":${DEFAULT_SCRIPT_TIMEOUT_MS}}`;

test("a script that does not name qdash runs exactly as before", () => {
  for (const code of [
    "text(1)",
    "const chips = await tools.qdash_list_chips({});\ntext(chips.length)",
    `${OPTIONS}\nawait tools["qdash_get_execution"]({})`,
    "// @options: {\"timeout_ms\": 1000}\nconst qdashboard = 1; text(qdashboard)",
  ]) {
    assert.equal(prepareScriptSource(code), withScriptDeadline(code), code);
  }
});

test("a script that names qdash gets the helpers on its first code line, keeping every line number", () => {
  const code = "const spec = qdash.calibration.qubitTargets([\"0\"]);\nthrow new Error(\"line 3\");";
  const prepared = prepareScriptSource(code);
  const lines = prepared.split("\n");
  assert.equal(lines.length, withScriptDeadline(code).split("\n").length);
  assert.equal(lines[0], OPTIONS);
  assert.equal(lines[1], `${scriptPreludeLine()}const spec = qdash.calibration.qubitTargets(["0"]);`);
  assert.equal(lines[2], 'throw new Error("line 3");');
  // An options line the model wrote stays its own, deadline bounded as before.
  const own = prepareScriptSource('// @options: {"max_output_tokens": 100}\nqdash.calibration.sweep.values(1)');
  assert.equal(own.split("\n")[0], `// @options: {"max_output_tokens":100,"timeout_ms":${DEFAULT_SCRIPT_TIMEOUT_MS}}`);
  // Without an options line, or with nothing after it, code mode reports the script as it is.
  assert.equal(withScriptHelpers("qdash.calibration"), "qdash.calibration");
  assert.equal(withScriptHelpers(`${OPTIONS}`), OPTIONS);
  assert.equal(SCRIPT_HELPERS_GLOBAL, "qdash");
});

/**
 * Whether `code` runs as strict code when it is the body of a function, as Code Mode runs a
 * script: an assignment to an undeclared name throws only in strict code. `globals` stands in for
 * the helpers when the script runs without the prelude.
 */
function runsStrict(code, globals = {}) {
  const context = { ...globals };
  try {
    runInNewContext(`(function () {${code}\nundeclaredProbe = 1;\n})()`, context);
  } catch (error) {
    if (error?.name === "ReferenceError" && /undeclaredProbe/.test(String(error.message))) return true;
    throw error;
  }
  assert.equal(context.undeclaredProbe, 1);
  return false;
}

// Script bodies (after the options line) and whether the engine runs them as strict code.
const DIRECTIVE_CASES = [
  ['"use strict"; void qdash', true],
  ['"use strict"\nvoid qdash', true],
  ["'use strict'\nvoid qdash", true],
  ['"use strict"\r\nvoid qdash', true],
  ['// leading comment\n/* block\n comment */ "use strict"\nvoid qdash', true],
  ['"use asm"; "use strict";\nvoid qdash', true],
  ['"first"\n\'use strict\'\nvoid qdash', true],
  ['"use strict" // trailing comment\nvoid qdash', true],
  ['"use strict" /* before the semicolon */ ;void qdash', true],
  ['"use strict" /* a block comment\n with a line break */ void qdash', true],
  ['"use strict"\n++globalThis.counter; void qdash', true],
  ['"use strict"\n!qdash', true],
  ['"use strict"\ninx: void qdash', true],
  ['"use\\x20strict";\n"use strict";\nvoid qdash', true],
  ['"escaped \\" quote"; "use strict"; void qdash', true],
  ['void qdash', false],
  ['"use\\x20strict"; void qdash', false],
  ['"use \\\nstrict"; void qdash', false],
  ['("use strict"); void qdash', false],
  ['"x" + "y";\n"use strict";\nvoid qdash', false],
  ['"use strict"\n+ 1; void qdash', false],
  ['"use strict"\n- 1; void qdash', false],
  ['"use strict"\n.length; void qdash', false],
  ['"use strict"\n["length"]; void qdash', false],
  ['"use strict"\n!= 0; void qdash', false],
  ['"use strict"\n=== "x"; void qdash', false],
  ['"use strict"\ninstanceof Object; void qdash', false],
  ['"use strict"\nin { "use strict": 1 }; void qdash', false],
  ['"use strict"\n? 1 : 0; void qdash', false],
  ['"use strict"\n, 0; void qdash', false],
  ['"use strict"\n/ 1; void qdash', false],
  ['"use strict" || 0; void qdash', false],
  ['qdash; "use strict"', false],
];

test("the helpers keep a script's directive prologue in effect, strict or not", () => {
  for (const [body, strict] of DIRECTIVE_CASES) {
    // The expectation is the engine's own reading of the script as written.
    const script = `${OPTIONS}\n${body}`;
    assert.equal(runsStrict(script, { qdash: {} }), strict, `original: ${JSON.stringify(body)}`);
    const prepared = prepareScriptSource(script);
    assert.ok(prepared.includes(scriptPreludeLine()), body);
    assert.equal(prepared.split(/\r\n|\n/).length, script.split(/\r\n|\n/).length, body);
    assert.equal(runsStrict(prepared), strict, `prepared: ${JSON.stringify(body)}`);
  }
});

test("the issue's script keeps use strict: an undeclared assignment still throws", () => {
  const script = '// @options: {}\n"use strict"; undeclaredProbe=1; void qdash';
  const run = (code) => runInNewContext(`(function () {${code}\n})()`, { qdash: {} });
  assert.throws(() => run(script), { name: "ReferenceError" });
  assert.throws(() => run(prepareScriptSource(script)), { name: "ReferenceError" });
  // The helpers follow the directive on its own line.
  assert.equal(prepareScriptSource(script).split("\n")[1], `"use strict";${scriptPreludeLine()} undeclaredProbe=1; void qdash`);
  assert.equal(prepareScriptSource('// @options: {}\n"use strict"\nqdash').split("\n")[1], `"use strict";${scriptPreludeLine()}`);
});

test("the directive prologue ends where its last directive does", () => {
  const at = (source) => directivePrologueEnd(source);
  assert.deepEqual(at(""), { index: 0, semicolon: false });
  assert.deepEqual(at("text(1)"), { index: 0, semicolon: false });
  assert.deepEqual(at('"use strict"'), { index: 12, semicolon: true });
  assert.deepEqual(at('"use strict";x'), { index: 13, semicolon: false });
  assert.deepEqual(at('"a"; "b"\nx'), { index: 8, semicolon: true });
  // A tagged template or call continues the string: it is not a directive.
  assert.deepEqual(at('"use strict"\n`t`'), { index: 0, semicolon: false });
  assert.deepEqual(at('"use strict"\n(0)'), { index: 0, semicolon: false });
  // An unterminated string or comment ends the prologue before it; Code Mode reports the error.
  assert.deepEqual(at('"a";\n"unterminated\n'), { index: 4, semicolon: false });
  assert.deepEqual(at('"a"; /* open'), { index: 4, semicolon: false });
  assert.deepEqual(at('"a"\n/* open'), { index: 0, semicolon: false });
  // A string may span lines only with a line continuation; U+2028 does not end it.
  assert.deepEqual(at('"a\\\r\nb"\nx'), { index: 7, semicolon: true });
  assert.deepEqual(at('"a b"\nx'), { index: 5, semicolon: true });
});

test("the prelude is one line that defines a frozen qdash.calibration from the SDK's implementation", () => {
  const line = scriptPreludeLine();
  assert.doesNotMatch(line, /[\n\r\u2028\u2029]/);
  const context = {};
  runInNewContext(line, context);
  const helpers = runInNewContext("qdash", context);
  assert.ok(Object.isFrozen(helpers));
  assert.ok(Object.isFrozen(helpers.calibration));
  assert.deepEqual(Object.keys(helpers), ["calibration"]);
  assert.deepEqual(Object.keys(helpers.calibration).sort(), Object.keys(calibration).filter((name) => name !== "calibrationDefinitionsSource").sort());
  // The global cannot be replaced or redefined by the script.
  assert.throws(() => runInNewContext('"use strict"; qdash = 1', context), { name: "TypeError" });
  assert.throws(() => runInNewContext("Object.defineProperty(globalThis, 'qdash', { value: 1 })", context), { name: "TypeError" });
  const spec = runInNewContext(
    'const c = qdash.calibration; c.calibrationSpec(c.couplingTargets([["0", "1"]]), [c.customTwoQubit({ tasks: [c.taskCall("CheckCrossResonance")] })])',
    context,
  );
  const expected = calibration.calibrationSpec(calibration.couplingTargets([["0", "1"]]), [
    calibration.customTwoQubit({ tasks: [calibration.taskCall("CheckCrossResonance")] }),
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(spec)), expected);
});

test("both hosts' script paths add the helpers: the pi CLI's tool_call hook rewrites only the codemode call it runs", async () => {
  const handlers = new Map();
  const pi = {
    registerTool() {},
    registerCommand() {},
    appendEntry() {},
    on: (event, handler) => handlers.set(event, [...(handlers.get(event) ?? []), handler]),
    getAllTools: () => [],
    getActiveTools: () => [],
    setActiveTools() {},
    getSettings: () => ({}),
  };
  installQDashToolPolicy(pi, { env: {} });
  const emit = async (payload) => {
    for (const handler of handlers.get("tool_call") ?? []) await handler(payload, {});
  };
  const script = { type: "tool_call", toolName: "codemode", toolCallId: "c1", input: { code: "text(qdash.calibration.SPEC_VERSION)" } };
  await emit(script);
  assert.equal(script.input.code, prepareScriptSource("text(qdash.calibration.SPEC_VERSION)"));
  assert.ok(script.input.code.includes(scriptPreludeLine()));
  // A strict script keeps its directive through the hook.
  const strict = { type: "tool_call", toolName: "codemode", toolCallId: "c2", input: { code: '"use strict"\nvoid qdash' } };
  await emit(strict);
  assert.equal(runsStrict(strict.input.code), true);
  // A nested call's arguments are never rewritten.
  const nested = { type: "tool_call", toolName: "codemode", toolCallId: "c1/1", parentToolCallId: "c1", input: { code: "qdash" } };
  await emit(nested);
  assert.equal(nested.input.code, "qdash");
});

test("the guidance tells scripts about qdash.calibration and keeps runs and agent sessions out of scripts", () => {
  assert.match(QDASH_SCRIPT_GUIDELINE, /`qdash\.calibration`/);
  assert.match(QDASH_SCRIPT_GUIDELINE, /await tools\.qdash_plan_pipeline\(\{ spec \}\)/);
  assert.match(QDASH_SCRIPT_GUIDELINE, /direct, approved `qdash_run_pipeline` call outside the script/);
  assert.match(QDASH_SCRIPT_GUIDELINE, /`qdash_run_agent_session_step`\); a spec never replaces them/);
  assert.match(QDASH_TOOL_NAMESPACE.instructions, /qdash\.calibration holds pure builders/);
  // Every builder the namespace instructions name exists.
  const named = QDASH_TOOL_NAMESPACE.instructions.split("\n").find((line) => line.startsWith("qdash.calibration"));
  for (const name of ["taskCall", "qubitTargets", "muxTargets", "couplingTargets", "configureAll", "bringUp", "oneQubitCheck", "oneQubitFineTune", "customOneQubit", "filterByStatus", "filterByMetric", "generateCRSchedule", "twoQubitCalibration", "customTwoQubit", "calibrationStep", "calibrationSpec"]) {
    assert.match(named, new RegExp(`\\b${name}\\b`));
    assert.equal(typeof calibration[name], "function", name);
  }
});
