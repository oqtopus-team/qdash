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
        task: { name: "CheckRabi" },
        target: { kind: "qubit", id: "Q05", chipId: "64Qv1" },
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

function deps(results, knowledge = "Expect a damped cosine.") {
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
    evaluator: { name: "@orangekame3/pi-qcaleval", version: "0.0.2-beta.5", source: "checkout", commit: "042e454323b2" },
  };
}

test("evidence feeds the evaluation: context text, figure bytes, task name and reference", async () => {
  const d = deps({ [EVIDENCE_TOOL]: evidenceResult(), [EVALUATION_TOOL]: evaluationResult() });

  const result = await evaluateTask({ taskId: "task-1", question: "Is the fit trustworthy?" }, d);

  assert.deepEqual(
    d.calls.map((call) => call.name),
    [EVIDENCE_TOOL, "knowledge", EVALUATION_TOOL],
  );
  assert.deepEqual(d.calls[0].args, { taskId: "task-1", maxFigures: 1 });
  assert.deepEqual(d.calls[1].args, { taskName: "CheckRabi" });
  const evaluation = d.calls[2].args;
  assert.equal(evaluation.context, "Task: CheckRabi\nTarget: Q05\nrabi_frequency = 12.3 MHz");
  assert.equal(evaluation.question, "Is the fit trustworthy?");
  assert.equal(evaluation.task_name, "CheckRabi");
  assert.equal(evaluation.knowledge, "Expect a damped cosine.");
  assert.deepEqual(evaluation.images, [{ data: PNG, mimeType: "image/png" }]);

  assert.equal(result.task_id, "task-1");
  assert.equal(result.task_name, "CheckRabi");
  assert.deepEqual(result.target, { kind: "qubit", id: "Q05", chip_id: "64Qv1" });
  assert.equal(result.figures.length, 1);
  assert.equal(result.figures[0].mime_type, "image/png");
  assert.equal(result.figures[0].bytes, 88);
  assert.equal(result.knowledge.chars, "Expect a damped cosine.".length);
  assert.equal(result.evaluation.model, "vllm/nvidia/Ising-Calibration");
  assert.equal(result.evaluation.fallback, false);
  assert.deepEqual(result.evaluation.diagnosis, { fit_quality: "good", success: true });
  assert.equal(result.evaluation.raw, null);
  assert.match(result.evaluation.prompt, /^Reference for this experiment/);
  assert.deepEqual(result.evaluation.usage, { input: 1200, output: 80 });
  assert.ok(result.evaluation.duration_ms >= 0);
  assert.equal(result.evaluator.commit, "042e454323b2");
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

import { hostRecord, plannerInstruction, plannerOutcome, recordFromDetails } from "../src/evaluate.ts";

test("the host record captures what the host put into the call", () => {
  const record = hostRecord(
    { context: "Task: CheckRabi", question: "Why?", task_name: "CheckRabi", images: [{ data: PNG, mimeType: "image/png" }, { data: 3 }] },
    "Expect a damped cosine.",
    1234,
  );
  assert.equal(record.context, "Task: CheckRabi");
  assert.equal(record.question, "Why?");
  assert.equal(record.task_name, "CheckRabi");
  assert.equal(record.figures.length, 1);
  assert.equal(record.figures[0].bytes, 88);
  assert.equal(record.knowledge.chars, "Expect a damped cosine.".length);
  assert.equal(record.duration_ms, 1234);

  const bare = hostRecord({ context: "x", question: "  " }, undefined);
  assert.deepEqual(bare, { context: "x", question: null, task_name: null, figures: [], knowledge: null });
});

test("a planner turn's qcal_evaluate result yields the same record as a direct evaluation", () => {
  const details = {
    model: { provider: "vllm", modelId: "nvidia/Ising-Calibration" },
    diagnosis: { fit_quality: "good", success: true },
    prompt: "Reference ...",
    host: hostRecord({ context: "Task: CheckRabi", task_name: "CheckRabi", images: [{ data: PNG, mimeType: "image/png" }] }, "ref", 900),
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
  assert.equal(record.knowledge.chars, 3);
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

test("the planner instruction names both tools and passes the question on", () => {
  const text = plannerInstruction("task-1", "Is the fit trustworthy?");
  assert.match(text, /task result task-1/);
  assert.match(text, new RegExp(`First call ${EVIDENCE_TOOL}`));
  assert.match(text, new RegExp(`then ${EVALUATION_TOOL}`));
  assert.match(text, /Is the fit trustworthy\?/);
  assert.doesNotMatch(plannerInstruction("task-1"), /Pass this question/);
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
