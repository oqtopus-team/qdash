import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { test } from "node:test";

import {
  EVALUATION_TOOL,
  EVIDENCE_TOOL,
  EvaluationError,
  evaluateTask,
  evidenceSummary,
  figureCount,
  figureRecord,
} from "../src/evaluate.ts";

const PNG = Buffer.from("\x89PNG\r\n\x1a\n" + "x".repeat(80), "latin1").toString("base64");

function evidenceResult(overrides = {}) {
  return {
    content: [
      { type: "text", text: "Task: CheckRabi\nTarget: Q05\nrabi_frequency = 12.3 MHz" },
      { type: "image", data: PNG, mimeType: "image/png" },
    ],
    details: {
      tool: EVIDENCE_TOOL,
      taskId: "task-1",
      evidence: {
        task: { name: "CheckRabi", status: "completed" },
        target: { kind: "qubit", id: "Q05", chipId: "64Qv1" },
        metrics: { rabi_frequency: 12.3 },
        runParameters: {
          time_range: { value: [0, 401, 8], unit: "ns", value_type: "range", description: "" },
          shots: { value: 2048, unit: "a.u.", value_type: "int", description: "" },
          interval: { value: 153600, unit: "ns", value_type: "int", description: "" },
        },
        sweeps: [{ name: "time_range", unit: "ns", description: "", spacing: "linear", start: 0, stop: 400, points: 51, step: 8 }],
        notes: "Task message: fit converged\n\nFigure JSON analysis #1:\n- 2 traces",
      },
    },
    ...overrides,
  };
}

function evaluationResult(overrides = {}) {
  return {
    content: [{ type: "text", text: '{"fit_quality":"good","success":true}' }],
    details: {
      model: { provider: "vllm", modelId: "nvidia/Ising-Calibration" },
      diagnosis: { fit_quality: "good", success: true },
      prompt: "Reference for this experiment ...\nExperiment context:\nTask: CheckRabi",
    },
    usage: { input: 1200, output: 80 },
    ...overrides,
  };
}

const REFERENCE = {
  knowledge: "This is a CheckRabi experiment: expect a damped cosine.",
  criteria: { statuses: { SUCCESS: "clear oscillation", LOW_CONTRAST: "small amplitude" }, parameters: { rabi_frequency: "float" } },
};
// The direct path completes the criteria with the sweep's range format before hashing.
const RANGE_FORMAT = "(<min time_range>, <max time_range>) [ns]";
// Key order follows compactCriteria (parameters, statuses, range_format), which the hash sees.
const PASSED_CRITERIA = { parameters: REFERENCE.criteria.parameters, statuses: REFERENCE.criteria.statuses, range_format: RANGE_FORMAT };
const REFERENCE_IDENTITY = `${REFERENCE.knowledge}\n${JSON.stringify(PASSED_CRITERIA)}`;

function deps(results, knowledge = REFERENCE) {
  const calls = [];
  return {
    calls,
    runTool: async (name, args) => {
      calls.push({ name, args });
      const result = results[name];
      return typeof result === "function" ? result(args) : result;
    },
    fetchKnowledge: async (taskName) => {
      calls.push({ name: "knowledge", args: { taskName } });
      return knowledge;
    },
    fetchExamples: async (taskName) => {
      calls.push({ name: "examples", args: { taskName } });
      return [
        { id: "e1", title: "Short T1", outcome: "suboptimal", status: "SHORT_T1", suggested_range: "", parameters: '{"t1": 14}', analysis: "Short.", images: [{ data: PNG, mimeType: "image/png" }], paths: ["examples/figures/t1.png"] },
      ];
    },
    evaluator: { name: "@orangekame3/pi-qcaleval", version: "0.0.2-beta.5", source: "checkout", commit: "042e454323b2" },
  };
}

test("evidence feeds the evaluation: task and target as context, figure bytes, task name and reference", async () => {
  const d = deps({ [EVIDENCE_TOOL]: evidenceResult(), [EVALUATION_TOOL]: evaluationResult() });

  const result = await evaluateTask({ taskId: "task-1", question: "Is the fit trustworthy?" }, d);

  assert.deepEqual(
    d.calls.map((call) => call.name),
    [EVIDENCE_TOOL, "knowledge", EVALUATION_TOOL],
  );
  assert.deepEqual(d.calls[0].args, { taskId: "task-1", maxFigures: 1 });
  assert.deepEqual(d.calls[1].args, { taskName: "CheckRabi" });
  const evaluation = d.calls[2].args;
  // The fitted metrics of the evidence text stay out: the model reads the plot,
  // and is told the sweep it was taken over.
  assert.equal(
    evaluation.context,
    [
      "Task CheckRabi on qubit Q05 (chip 64Qv1), status completed.",
      "Sweep: time_range 0 to 400 ns in steps of 8 ns (51 points).",
      "Settings: shots 2048; interval 153600 ns.",
      "Task message: fit converged",
    ].join("\n"),
  );
  assert.equal(evaluation.question, "Is the fit trustworthy?");
  assert.equal(evaluation.task_name, "CheckRabi");
  assert.equal(evaluation.knowledge, REFERENCE.knowledge);
  assert.deepEqual(evaluation.criteria, PASSED_CRITERIA);
  assert.deepEqual(evaluation.images, [{ data: PNG, mimeType: "image/png" }]);

  assert.equal(result.task_id, "task-1");
  assert.equal(result.task_name, "CheckRabi");
  assert.deepEqual(result.target, { kind: "qubit", id: "Q05", chip_id: "64Qv1" });
  assert.equal(result.figures.length, 1);
  assert.equal(result.figures[0].mime_type, "image/png");
  assert.equal(result.figures[0].bytes, 88);
  assert.equal(result.context, evaluation.context);
  assert.equal(result.knowledge.chars, REFERENCE_IDENTITY.length);
  assert.equal(result.knowledge.sha256, createHash("sha256").update(REFERENCE_IDENTITY).digest("hex"));
  assert.equal(result.evaluation.model, "vllm/nvidia/Ising-Calibration");
  assert.equal(result.evaluation.fallback, false);
  assert.deepEqual(result.evaluation.diagnosis, { fit_quality: "good", success: true });
  assert.equal(result.evaluation.raw, null);
  assert.match(result.evaluation.prompt, /^Reference for this experiment/);
  assert.deepEqual(result.evaluation.usage, { input: 1200, output: 80 });
  assert.ok(result.evaluation.duration_ms >= 0);
  assert.equal(result.evaluator.commit, "042e454323b2");
});

test("with examples requested, the labeled examples are fetched, passed, and recorded by hash", async () => {
  const d = deps({ [EVIDENCE_TOOL]: evidenceResult(), [EVALUATION_TOOL]: evaluationResult() });

  const result = await evaluateTask({ taskId: "task-1", withExamples: true }, d);

  assert.deepEqual(d.calls.map((call) => call.name), [EVIDENCE_TOOL, "knowledge", "examples", EVALUATION_TOOL]);
  const evaluation = d.calls[3].args;
  assert.equal(evaluation.use_examples, true);
  assert.deepEqual(evaluation.examples, [
    { images: [{ data: PNG, mimeType: "image/png" }], scenario: "Short T1", analysis: "Short.", parameters: { t1: 14 }, status: "SHORT_T1" },
  ]);
  assert.deepEqual(
    result.examples.map((e) => [e.id, e.outcome, e.status, e.figures.length, e.figures[0].bytes, e.figures[0].path]),
    [["e1", "suboptimal", "SHORT_T1", 1, 88, "examples/figures/t1.png"]],
  );
  assert.equal("id" in evaluation.examples[0], false);

  // Not requested: no fetch, no flag, no record.
  const zero = deps({ [EVIDENCE_TOOL]: evidenceResult(), [EVALUATION_TOOL]: evaluationResult() });
  const plain = await evaluateTask({ taskId: "task-1" }, zero);
  assert.equal(zero.calls.some((call) => call.name === "examples"), false);
  assert.equal("use_examples" in zero.calls[2].args, false);
  assert.deepEqual(plain.examples, []);
});

test("the evaluator's system prompt is recorded when it reports one", () => {
  const record = recordFromDetails("task-1", { system_prompt: "You evaluate plots.", prompt: "p" }, { mode: "direct" });
  assert.equal(record.evaluation.system_prompt, "You evaluate plots.");
  assert.equal(recordFromDetails("task-1", {}, { mode: "direct" }).evaluation.system_prompt, null);
});

test("without a task name or reference, the evaluation runs on the evidence alone", async () => {
  const evidence = evidenceResult({ details: { tool: EVIDENCE_TOOL, taskId: "task-1" } });
  const d = deps({ [EVIDENCE_TOOL]: evidence, [EVALUATION_TOOL]: evaluationResult() }, undefined);

  const result = await evaluateTask({ taskId: " task-1 " }, d);

  assert.deepEqual(
    d.calls.map((call) => call.name),
    [EVIDENCE_TOOL, EVALUATION_TOOL],
  );
  assert.equal("task_name" in d.calls[1].args, false);
  assert.equal("knowledge" in d.calls[1].args, false);
  assert.equal("question" in d.calls[1].args, false);
  assert.equal(result.task_name, null);
  assert.equal(result.target, null);
  assert.equal(result.knowledge, null);
});

test("a prose answer is kept as raw, with no diagnosis", async () => {
  const prose = evaluationResult({
    content: [{ type: "text", text: "The Rabi oscillation decays as expected." }],
    details: {
      model: { provider: "vllm", modelId: "nvidia/Ising-Calibration" },
      fallback: true,
      diagnosis: null,
      raw: "The Rabi oscillation decays as expected.",
      prompt: "Experiment context: ...",
    },
  });
  const d = deps({ [EVIDENCE_TOOL]: evidenceResult(), [EVALUATION_TOOL]: prose });

  const result = await evaluateTask({ taskId: "task-1" }, d);

  assert.equal(result.evaluation.diagnosis, null);
  assert.equal(result.evaluation.raw, "The Rabi oscillation decays as expected.");
  assert.equal(result.evaluation.fallback, true);
});

test("an evidence failure stops before the model is called", async () => {
  const d = deps({
    [EVIDENCE_TOOL]: { content: [{ type: "text", text: "task result task-9 not found" }], isError: true },
    [EVALUATION_TOOL]: evaluationResult(),
  });

  await assert.rejects(evaluateTask({ taskId: "task-9" }, d), (error) => {
    assert.ok(error instanceof EvaluationError);
    assert.equal(error.stage, "evidence");
    assert.equal(error.status, 502);
    assert.match(error.message, /not found/);
    return true;
  });
  assert.deepEqual(
    d.calls.map((call) => call.name),
    [EVIDENCE_TOOL],
  );
});

test("a task result without a figure is rejected as unprocessable", async () => {
  const d = deps({
    [EVIDENCE_TOOL]: evidenceResult({ content: [{ type: "text", text: "Task: CheckRabi" }] }),
    [EVALUATION_TOOL]: evaluationResult(),
  });

  await assert.rejects(evaluateTask({ taskId: "task-1" }, d), (error) => {
    assert.equal(error.stage, "evidence");
    assert.equal(error.status, 422);
    return true;
  });
});

test("an evaluation tool error surfaces with its text", async () => {
  const d = deps({
    [EVIDENCE_TOOL]: evidenceResult(),
    [EVALUATION_TOOL]: {
      content: [{ type: "text", text: "qcal_evaluate: HTTP 400 Non-base64 digit found" }],
      details: { model: { provider: "vllm", modelId: "x" } },
      isError: true,
    },
  });

  await assert.rejects(evaluateTask({ taskId: "task-1" }, d), (error) => {
    assert.equal(error.stage, "evaluation");
    assert.match(error.message, /Non-base64/);
    return true;
  });
});

test("an empty task id is a request error", async () => {
  const d = deps({});
  await assert.rejects(evaluateTask({ taskId: "  " }, d), (error) => {
    assert.equal(error.stage, "request");
    assert.equal(error.status, 400);
    return true;
  });
  assert.equal(d.calls.length, 0);
});

test("the requested figure count is passed through within pi-qcaleval's limit", async () => {
  const d = deps({ [EVIDENCE_TOOL]: evidenceResult(), [EVALUATION_TOOL]: evaluationResult() });
  await evaluateTask({ taskId: "task-1", maxFigures: 9 }, d);
  assert.equal(d.calls[0].args.maxFigures, 4);
  assert.equal(figureCount(undefined), 1);
  assert.equal(figureCount(2.7), 2);
  assert.equal(figureCount(-3), 1);
});

test("figure records hash the decoded bytes", () => {
  const record = figureRecord({ data: PNG, mimeType: "image/png" });
  assert.equal(record.sha256, createHash("sha256").update(Buffer.from(PNG, "base64")).digest("hex"));
  assert.equal(record.bytes, 88);
});

test("evidence summary tolerates missing or partial details", () => {
  assert.deepEqual(evidenceSummary(undefined), { taskName: null, target: null });
  assert.deepEqual(evidenceSummary({ evidence: { target: { kind: "coupling", id: "Q04-Q05" } } }), {
    taskName: null,
    target: { kind: "coupling", id: "Q04-Q05" },
  });
});

import { evidenceContext, evidenceSweeps, hostRecord, plannerInstruction, plannerOutcome, recordFromDetails, sweepRangeFormat } from "../src/evaluate.ts";

test("the context names the task, target and status, and the task's message, never the metrics", () => {
  assert.equal(
    evidenceContext(evidenceResult().details),
    [
      "Task CheckRabi on qubit Q05 (chip 64Qv1), status completed.",
      "Sweep: time_range 0 to 400 ns in steps of 8 ns (51 points).",
      "Settings: shots 2048; interval 153600 ns.",
      "Task message: fit converged",
    ].join("\n"),
  );
  assert.equal(evidenceContext({ evidence: { task: { name: "CheckRabi" } } }), "Task CheckRabi.");
  assert.equal(evidenceContext({ evidence: { task: { name: "Configure", status: "completed" }, target: { kind: "system", id: "all" } } }), "Task Configure on all, status completed.");
  assert.equal(evidenceContext({ evidence: { task: { name: "CheckBellState" }, target: { kind: "coupling", id: "Q00-Q01", chipId: "c1" }, notes: "Figure JSON analysis #1:\n- x" } }), "Task CheckBellState on coupling Q00-Q01 (chip c1).");
  // No details, or no task name: the caller falls back to the evidence text.
  assert.equal(evidenceContext(undefined), undefined);
  assert.equal(evidenceContext({ evidence: { target: { id: "Q05" } } }), undefined);
});

test("without evidence details the evidence text is the context", async () => {
  const evidence = evidenceResult({ details: { tool: EVIDENCE_TOOL, taskId: "task-1" } });
  const d = deps({ [EVIDENCE_TOOL]: evidence, [EVALUATION_TOOL]: evaluationResult() });
  const result = await evaluateTask({ taskId: "task-1" }, d);
  assert.equal(result.context, "Task: CheckRabi\nTarget: Q05\nrabi_frequency = 12.3 MHz");
});

test("the host record captures what the host put into the call", () => {
  const record = hostRecord(
    { context: "Task: CheckRabi", question: "Why?", task_name: "CheckRabi", images: [{ data: PNG, mimeType: "image/png" }, { data: 3 }] },
    { knowledge: "Expect a damped cosine." },
    1234,
  );
  assert.equal(record.context, "Task: CheckRabi");
  assert.equal(record.question, "Why?");
  assert.equal(record.task_name, "CheckRabi");
  assert.equal(record.figures.length, 1);
  assert.equal(record.figures[0].bytes, 88);
  assert.equal(record.knowledge.chars, "Expect a damped cosine.\n{}".length);
  assert.equal(record.duration_ms, 1234);

  const bare = hostRecord({ context: "x", question: "  " }, undefined);
  assert.deepEqual(bare, { context: "x", question: null, task_name: null, figures: [], knowledge: null });
  assert.equal(hostRecord({ context: "x" }, undefined, 5, "task-7").task_id, "task-7");
  assert.equal(recordFromDetails("", { host: { task_id: "task-7", context: "x" } }, { mode: "planner" }).task_id, "task-7");
});

test("a planner turn's qcal_evaluate result yields the same record as a direct evaluation", () => {
  const details = {
    model: { provider: "vllm", modelId: "nvidia/Ising-Calibration" },
    diagnosis: { fit_quality: "good", success: true },
    prompt: "Reference ...",
    host: hostRecord({ context: "Task: CheckRabi", task_name: "CheckRabi", images: [{ data: PNG, mimeType: "image/png" }] }, { knowledge: "ref" }, 900),
  };
  const record = recordFromDetails("task-1", details, {
    mode: "planner",
    evaluator: { name: "@orangekame3/pi-qcaleval", version: "0.0.1", source: "checkout" },
    planner: { model: "openai-compatible/qwen", answer: "Looks good.", tool_calls: [EVIDENCE_TOOL, EVALUATION_TOOL], duration_ms: 40000 },
  });
  assert.equal(record.mode, "planner");
  assert.equal(record.task_name, "CheckRabi");
  assert.equal(record.context, "Task: CheckRabi");
  assert.equal(record.figures[0].bytes, 88);
  assert.equal(record.knowledge.chars, "ref\n{}".length);
  assert.equal(record.evaluation.model, "vllm/nvidia/Ising-Calibration");
  assert.deepEqual(record.evaluation.diagnosis, { fit_quality: "good", success: true });
  assert.equal(record.evaluation.duration_ms, 900);
  assert.equal(record.planner.answer, "Looks good.");
  assert.deepEqual(record.planner.tool_calls, [EVIDENCE_TOOL, EVALUATION_TOOL]);

  const prose = recordFromDetails("task-1", { ...details, diagnosis: null, raw: "It decays." }, { mode: "direct" });
  assert.equal(prose.evaluation.diagnosis, null);
  assert.equal(prose.evaluation.raw, "It decays.");
  assert.equal(prose.planner, null);
});

test("the planner instruction asks for examples only when the request does", () => {
  assert.doesNotMatch(plannerInstruction("task-1"), /use_examples/);
  assert.match(plannerInstruction("task-1", undefined, true), /use_examples: true/);
});

test("the planner instruction names both tools and passes the question on", () => {
  const text = plannerInstruction("task-1", "Is the fit trustworthy?");
  assert.match(text, /task result task-1/);
  assert.match(text, new RegExp(`First call ${EVIDENCE_TOOL}`));
  assert.match(text, new RegExp(`then ${EVALUATION_TOOL}`));
  assert.match(text, /Is the fit trustworthy\?/);
  assert.doesNotMatch(plannerInstruction("task-1"), /Pass this question/);
  assert.match(text, /not the fitted metrics/);
  assert.match(text, /calibration_diagnosis/);
});

test("the planner outcome is the last qcal_evaluate result and the tools called", () => {
  const entries = [
    { model: [{ role: "user", content: "evaluate" }] },
    { model: [{ role: "assistant", content: [{ type: "toolCall", name: EVIDENCE_TOOL }] }] },
    { model: [{ role: "toolResult", toolName: EVIDENCE_TOOL, content: [{ type: "text", text: "..." }], isError: false }] },
    { model: [{ role: "assistant", content: [{ type: "toolCall", name: EVALUATION_TOOL }] }] },
    { model: [{ role: "toolResult", toolName: EVALUATION_TOOL, content: [{ type: "text", text: "no plot" }], isError: true }] },
    { model: [{ role: "assistant", content: [{ type: "toolCall", name: EVALUATION_TOOL }] }] },
    { model: [{ role: "toolResult", toolName: EVALUATION_TOOL, content: [{ type: "text", text: "{}" }], isError: false, details: { prompt: "p" }, usage: { input: 10 } }] },
    { model: [{ role: "assistant", content: [{ type: "text", text: "Done." }] }] },
  ];
  const outcome = plannerOutcome(entries);
  assert.deepEqual(outcome.details, { prompt: "p" });
  assert.deepEqual(outcome.usage, { input: 10 });
  assert.equal(outcome.error, undefined);
  assert.deepEqual(outcome.toolCalls, [EVIDENCE_TOOL, EVALUATION_TOOL, EVALUATION_TOOL]);

  const failed = plannerOutcome(entries.slice(0, 5));
  assert.equal(failed.details, undefined);
  assert.equal(failed.error, "no plot");

  assert.deepEqual(plannerOutcome([]), { details: undefined, usage: undefined, error: undefined, toolCalls: [] });
});

test("an incomplete answer keeps its text, the keys it lacks, and how it was asked", () => {
  const details = {
    model: { provider: "vllm", modelId: "nvidia/Ising-Calibration" },
    diagnosis: { technical_description: "only" },
    raw: '{"technical_description": "only"}',
    missing_keys: ["experimental_conclusion", "experimental_significance", "fit_quality", "parameter_extraction", "success"],
    attempts: 2,
    structured: true,
    stop_reason: "stop",
    calls: [
      { question: "technical_description", duration_ms: 195000, stop_reason: "length", structured: true, output_tokens: 2000, missing_keys: ["success"] },
      { duration_ms: 30000, stop_reason: "stop", structured: true, output_tokens: 300, missing_keys: [] },
      { bogus: true },
    ],
    answers: { technical_description: "only", bogus: 3 },
    questions: ["technical_description", "experimental_conclusion", 7],
    prompt: "p",
  };
  const record = recordFromDetails("task-1", details, { mode: "direct", text: "ignored" });
  assert.equal(record.evaluation.calls.length, 2);
  assert.deepEqual(record.evaluation.answers, { technical_description: "only" });
  assert.deepEqual(record.evaluation.questions, ["technical_description", "experimental_conclusion"]);
  assert.equal(record.evaluation.calls[1].question, undefined);
  assert.deepEqual(record.evaluation.calls[0], {
    question: "technical_description",
    duration_ms: 195000,
    stop_reason: "length",
    structured: true,
    output_tokens: 2000,
    missing_keys: ["success"],
  });
  assert.deepEqual(record.evaluation.diagnosis, { technical_description: "only" });
  assert.equal(record.evaluation.raw, '{"technical_description": "only"}');
  assert.equal(record.evaluation.missing_keys.length, 5);
  assert.equal(record.evaluation.attempts, 2);
  assert.equal(record.evaluation.structured, true);
  assert.equal(record.evaluation.stop_reason, "stop");

  // An older evaluator reports none of this; a complete answer has no text to keep.
  const old = recordFromDetails("task-1", { diagnosis: { fit_quality: "good", success: true } }, { mode: "direct", text: "{}" });
  assert.equal(old.evaluation.raw, null);
  assert.equal(old.evaluation.answers, null);
  assert.deepEqual(old.evaluation.questions, []);
  assert.deepEqual(old.evaluation.missing_keys, []);
  assert.equal(old.evaluation.attempts, null);
  assert.equal(old.evaluation.structured, null);
  assert.equal(old.evaluation.stop_reason, null);
  assert.deepEqual(old.evaluation.calls, []);
});

test("the sweep gives the status question its range format, unless the knowledge states one", async () => {
  assert.equal(sweepRangeFormat(evidenceResult().details), "(<min time_range>, <max time_range>) [ns]");
  assert.equal(sweepRangeFormat({ evidence: { sweeps: [{ name: "amp", unit: "a.u.", spacing: "list", start: 0, stop: 1, points: 3 }] } }), "(<min amp>, <max amp>)");
  assert.equal(sweepRangeFormat({ evidence: {} }), undefined);
  assert.deepEqual(evidenceSweeps({ evidence: { sweeps: [{ name: "x" }, 3] } }), []);
  const d = deps({ [EVIDENCE_TOOL]: evidenceResult(), [EVALUATION_TOOL]: evaluationResult() });
  const result = await evaluateTask({ taskId: "task-1" }, d);
  const call = d.calls.find((c) => c.name === EVALUATION_TOOL);
  assert.deepEqual(call.args.criteria, PASSED_CRITERIA);
  // The record hashes the reference as passed, range format included.
  assert.equal(result.knowledge.chars, REFERENCE_IDENTITY.length);
  // A stated format wins; without any knowledge the sweep alone makes the criteria.
  const stated = deps({ [EVIDENCE_TOOL]: evidenceResult(), [EVALUATION_TOOL]: evaluationResult() }, { knowledge: "bg", criteria: { statuses: { SUCCESS: "ok" }, range_format: "(<min t>, <max t>) [us]" } });
  await evaluateTask({ taskId: "task-1" }, stated);
  assert.deepEqual(stated.calls.find((c) => c.name === EVALUATION_TOOL).args.criteria, { statuses: { SUCCESS: "ok" }, range_format: "(<min t>, <max t>) [us]" });
  const bare = deps({ [EVIDENCE_TOOL]: evidenceResult(), [EVALUATION_TOOL]: evaluationResult() }, null);
  await evaluateTask({ taskId: "task-1" }, bare);
  const bareCall = bare.calls.find((c) => c.name === EVALUATION_TOOL);
  assert.equal(bareCall.args.knowledge, undefined);
  assert.deepEqual(bareCall.args.criteria, { range_format: "(<min time_range>, <max time_range>) [ns]" });
});

import { previewEvaluationPrompts } from "../src/evaluate.ts";

const PREVIEW_IDENTITY = `${REFERENCE.knowledge}\n${JSON.stringify({ parameters: REFERENCE.criteria.parameters, statuses: REFERENCE.criteria.statuses })}`;

test("a prompt preview runs the evaluator dry with the task's reference and examples, no figure", async () => {
  const d = deps({
    [EVALUATION_TOOL]: (args) => ({
      content: [{ type: "text", text: "## fit_reliability\n..." }],
      details: {
        model: { provider: "vllm", modelId: "nvidia/Ising-Calibration" },
        dry_run: true,
        questions: ["fit_reliability", "calibration_diagnosis"],
        prompts: { fit_reliability: `F: ${args.context}`, calibration_diagnosis: "C" },
        examples_used: args.examples ? args.examples.length : 0,
      },
    }),
  });
  const preview = await previewEvaluationPrompts({ taskName: " CheckRabi ", withExamples: true, question: "Centred?" }, d);
  assert.deepEqual(d.calls.map((c) => c.name), ["knowledge", "examples", EVALUATION_TOOL]);
  const args = d.calls[2].args;
  assert.equal(args.dry_run, true);
  assert.equal(args.images, undefined);
  assert.equal(args.context, "Task CheckRabi.");
  assert.equal(args.question, "Centred?");
  assert.equal(args.task_name, "CheckRabi");
  assert.equal(args.knowledge, REFERENCE.knowledge);
  assert.deepEqual(args.criteria, REFERENCE.criteria);
  assert.equal(args.use_examples, true);
  assert.equal(args.examples.length, 1);
  assert.deepEqual(preview, {
    task_name: "CheckRabi",
    with_examples: true,
    model: "vllm/nvidia/Ising-Calibration",
    questions: [
      { key: "fit_reliability", prompt: "F: Task CheckRabi." },
      { key: "calibration_diagnosis", prompt: "C" },
    ],
    // Hashed as passed: compactCriteria orders parameters before statuses.
    knowledge: {
      chars: PREVIEW_IDENTITY.length,
      sha256: createHash("sha256").update(PREVIEW_IDENTITY).digest("hex"),
    },
    examples: [{ id: "e1", title: "Short T1", outcome: "suboptimal", status: "SHORT_T1", figures: [{ ...figureRecord({ data: PNG, mimeType: "image/png" }), path: "examples/figures/t1.png" }] }],
    examples_used: 1,
  });
  // Zero-shot, a given context, and no knowledge.
  const bare = deps({ [EVALUATION_TOOL]: () => ({ content: [], details: { dry_run: true, questions: ["fit_reliability"], prompts: { fit_reliability: "F" } } }) }, null);
  const zero = await previewEvaluationPrompts({ taskName: "CheckRabi", context: "CheckRabi on Q05" }, bare);
  assert.deepEqual(bare.calls.map((c) => c.name), ["knowledge", EVALUATION_TOOL]);
  assert.equal(bare.calls[1].args.context, "CheckRabi on Q05");
  assert.equal(bare.calls[1].args.knowledge, undefined);
  assert.equal(zero.model, null);
  assert.equal(zero.knowledge, null);
  assert.deepEqual(zero.examples, []);
  // Errors surface as evaluation-stage errors; a blank task name is a request error.
  const failing = deps({ [EVALUATION_TOOL]: () => ({ content: [{ type: "text", text: "qcal_evaluate: boom" }], isError: true }) });
  await assert.rejects(previewEvaluationPrompts({ taskName: "CheckRabi" }, failing), (error) => error instanceof EvaluationError && error.stage === "evaluation" && /boom/.test(error.message));
  await assert.rejects(previewEvaluationPrompts({ taskName: "  " }, d), (error) => error instanceof EvaluationError && error.status === 400);
});

import { draftKnowledge } from "../src/evaluate.ts";

const DRAFT = {
  name: "CheckRabi",
  prompt_text: "## Experiment: CheckRabi",
  reference: { background: "This is a CheckRabi experiment: the draft's wording.", statuses: { SUCCESS: "clear oscillation" } },
  examples: [
    { id: "d1", title: "Draft example", outcome: "suboptimal", status: "SHORT_T1", diagnosis: "Short.", figures: [{ base64_data: PNG, mime_type: "image/png", path: "examples/d1.png" }] },
  ],
};

test("an evaluation against a draft reads its reference and examples from one load of it", async () => {
  let loads = 0;
  const knowledge = draftKnowledge(async () => {
    loads += 1;
    return DRAFT;
  });
  const d = { ...deps({ [EVIDENCE_TOOL]: evidenceResult(), [EVALUATION_TOOL]: evaluationResult() }), ...knowledge };

  const result = await evaluateTask({ taskId: "task-1", withExamples: true }, d);

  assert.equal(loads, 1);
  const evaluation = d.calls.find((call) => call.name === EVALUATION_TOOL).args;
  assert.equal(evaluation.knowledge, "This is a CheckRabi experiment: the draft's wording.");
  assert.deepEqual(evaluation.criteria.statuses, { SUCCESS: "clear oscillation" });
  assert.deepEqual(evaluation.examples.map((e) => e.scenario), ["Draft example"]);
  assert.deepEqual(result.examples.map((e) => [e.id, e.figures[0].path]), [["d1", "examples/d1.png"]]);
});

test("a draft that cannot be read fails the evaluation at the knowledge stage", async () => {
  const knowledge = draftKnowledge(async () => {
    throw new Error("HTTP 404: knowledge draft abc not found");
  });
  const d = { ...deps({ [EVIDENCE_TOOL]: evidenceResult(), [EVALUATION_TOOL]: evaluationResult() }), ...knowledge };

  await assert.rejects(evaluateTask({ taskId: "task-1" }, d), (error) => {
    assert.ok(error instanceof EvaluationError);
    assert.equal(error.stage, "knowledge");
    assert.equal(error.message, "knowledge draft: HTTP 404: knowledge draft abc not found");
    return true;
  });
  assert.equal(d.calls.some((call) => call.name === EVALUATION_TOOL), false);
});
