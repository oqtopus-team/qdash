import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DEFAULT_GUIDANCE,
  DEFAULT_STATUSES,
  ICL_QUESTIONS,
  MAX_EXAMPLES,
  QUESTIONS,
  addUsage,
  answerText,
  askQuestions,
  assembleDiagnosis,
  buildQuestionContent,
  fitExamples,
  labeledLine,
  normalizeStatus,
  outputBudget,
  parseAnswer,
  parseFitAssessment,
  parseJsonObject,
  parseModelSpec,
  parseOutcome,
  promptRecord,
  questionTemplate,
  resolveEvaluationModel,
} from "../.test-dist/extensions/qcaleval.js";

// ---------------------------------------------------------------------------
// Model resolution
// ---------------------------------------------------------------------------

test("the override spec splits provider and model id at the first slash", () => {
  assert.equal(parseModelSpec(undefined), undefined);
  assert.equal(parseModelSpec("  "), undefined);
  assert.deepEqual(parseModelSpec("vllm/nvidia/Ising-Calibration-1.5-31B-NVFP4"), {
    provider: "vllm",
    modelId: "nvidia/Ising-Calibration-1.5-31B-NVFP4",
  });
  assert.throws(() => parseModelSpec("no-slash"), /provider\/modelId/);
  assert.throws(() => parseModelSpec("vllm/"), /provider\/modelId/);
});

const model = (provider, id, input = ["text", "image"], maxTokens = 2048) => ({
  provider,
  id,
  input,
  maxTokens,
});
const registry = (available) => ({
  getAvailable: () => available,
  find: (provider, id) => available.find((m) => m.provider === provider && m.id === id),
});

test("a configured calibration VLM is preferred over the conversation's model", () => {
  const ising = model("vllm", "nvidia/Ising-Calibration-1.5-31B-NVFP4");
  const qwen = model("openai-compatible", "qwen3.8-flash-next");
  assert.deepEqual(resolveEvaluationModel(registry([qwen, ising]), qwen, undefined), {
    model: ising,
    fallback: false,
  });
});

test("without a calibration VLM the conversation's vision model judges, as a fallback", () => {
  const qwen = model("openai-compatible", "qwen3.8-flash-next");
  assert.deepEqual(resolveEvaluationModel(registry([qwen]), qwen, undefined), {
    model: qwen,
    fallback: true,
  });
  // A text-only conversation model cannot see the plot.
  const textOnly = model("openai", "gpt-text", ["text"]);
  assert.match(resolveEvaluationModel(registry([textOnly]), textOnly, undefined).error, /no evaluation model/);
  assert.match(resolveEvaluationModel(registry([]), undefined, undefined).error, /no evaluation model/);
});

test("an explicit QCALEVAL_MODEL override wins, and must exist", () => {
  const ising = model("vllm", "nvidia/Ising-Calibration-1.5-31B-NVFP4");
  const other = model("vllm", "other-vlm");
  assert.deepEqual(resolveEvaluationModel(registry([ising, other]), ising, "vllm/other-vlm"), {
    model: other,
    fallback: false,
  });
  assert.match(resolveEvaluationModel(registry([ising]), ising, "vllm/missing").error, /not configured/);
});

test("the output budget follows the model's limit within bounds", () => {
  assert.equal(outputBudget({ maxTokens: 2048 }), 2048);
  assert.equal(outputBudget({ maxTokens: 16384 }), 4096);
  assert.equal(outputBudget({ maxTokens: 0 }), 2048);
});

// ---------------------------------------------------------------------------
// Question templates
// ---------------------------------------------------------------------------

const png = (data) => ({ data, mimeType: "image/png" });
const BACKGROUND =
  "This is a CheckRabi experiment: we sweep the drive duration to find the Rabi frequency. A successful result has a clear damped cosine with high contrast.";
const input = (overrides = {}) => ({
  background: BACKGROUND,
  context: "CheckRabi on Q05 (chip 64Qv3), completed.",
  images: [png("QUERY")],
  ...overrides,
});

test("the six questions are asked in the paper's order, and three take demonstrations", () => {
  assert.deepEqual(QUESTIONS, [
    "technical_description",
    "experimental_conclusion",
    "experimental_significance",
    "fit_reliability",
    "parameter_extraction",
    "calibration_diagnosis",
  ]);
  assert.deepEqual([...ICL_QUESTIONS].sort(), ["calibration_diagnosis", "experimental_significance", "parameter_extraction"]);
});

test("Q1 describes the figure in JSON without the background; every other question opens with it", () => {
  const q1 = questionTemplate("technical_description", input());
  assert.match(q1.text, /^Describe the figure <image> in JSON format\.\n\nRequired fields:\n\{\n  "plot_type"/);
  assert.doesNotMatch(q1.text, /CheckRabi/);
  assert.deepEqual(q1.images, [png("QUERY")]);
  for (const question of QUESTIONS.slice(1)) {
    const { text } = questionTemplate(question, input());
    assert.ok(text.startsWith(`${BACKGROUND}\n\nExperiment context: CheckRabi on Q05 (chip 64Qv3), completed.\n\n`), question);
    assert.equal((text.match(/<image>/g) ?? []).length, 1, question);
  }
  // Without a background or context the question stands alone.
  assert.match(questionTemplate("fit_reliability", input({ background: undefined, context: "  " })).text, /^Assess whether/);
});

test("Q2 lists the four outcomes and asks for a classification line", () => {
  const { text } = questionTemplate("experimental_conclusion", input());
  assert.match(text, /Based on what you observe in the data <image>, classify the experimental outcome\./);
  assert.match(text, /Options:\n- Expected behavior: Experiment produced usable calibration data\n- Suboptimal parameters: .*\n- Anomalous behavior: .*\n- Apparatus issue: No meaningful signal/);
  assert.match(text, /Provide your answer as:\nClassification: <your choice>\nReason: <brief explanation>$/);
});

test("Q3 explains the host's points, or the default ones, plus a specific question", () => {
  const plain = questionTemplate("experimental_significance", input()).text;
  assert.match(plain, /What does this result <image> imply\?\n\nExplain:\n- What the observed behavior indicates/);
  for (const line of DEFAULT_GUIDANCE) assert.ok(plain.includes(`- ${line}`));
  assert.match(plain, /\n\nProvide your assessment\.$/);
  const custom = questionTemplate(
    "experimental_significance",
    input({ criteria: { guidance: ["What the contrast says about readout", " "] }, question: "Is the decay too fast?" }),
  ).text;
  assert.match(custom, /Explain:\n- What the contrast says about readout\n- Is the decay too fast\?\n\nProvide your assessment\.$/);
  assert.doesNotMatch(custom, /observed behavior indicates/);
});

test("Q4 offers Reliable / Unreliable / No fit and asks for an assessment line", () => {
  const { text } = questionTemplate("fit_reliability", input());
  assert.match(text, /Assess whether the fit to the data in this plot <image> is reliable for parameter extraction\.\n\nOptions:\n- Reliable\n- Unreliable\n- No fit\n\nProvide your answer as:\nAssessment: <your choice>\nReason: <brief explanation>$/);
});

test("Q5 asks for the host's parameter schema as JSON, or for whatever the plot determines", () => {
  const schema = questionTemplate("parameter_extraction", input({ criteria: { parameters: { rabi_frequency: "float", contrast: "float" } } })).text;
  assert.match(schema, /Extract the following parameters from this plot <image>\.\n\nReport in JSON format:\n\{"rabi_frequency": float, "contrast": float\}\nUse "Unreliable" for a value the plot does not determine\.$/);
  const generic = questionTemplate("parameter_extraction", input()).text;
  assert.match(generic, /Extract the physical parameters this plot <image> determines\.\n\nReport in JSON format/);
});

test("Q6 lists the decision criteria, the range format, and the exact answer format", () => {
  const { text } = questionTemplate(
    "calibration_diagnosis",
    input({
      criteria: {
        statuses: { SUCCESS: "Clear damped cosine", LOW_CONTRAST: "Oscillation amplitude under 70%" },
        range_format: "(<min duration>, <max duration>) [ns]",
      },
    }),
  );
  assert.match(text, /Evaluate the image <image> and determine the experiment status\.\n\nDECISION CRITERIA\n- SUCCESS: Clear damped cosine\n- LOW_CONTRAST: Oscillation amplitude under 70%\n\nWhen the status is not SUCCESS, provide a SPECIFIC suggested \(<min duration>, <max duration>\) \[ns\]\./);
  assert.match(text, /The response MUST follow this exact format:\n\nStatus: <one of the listed statuses>\nSuggested range: \(<min duration>, <max duration>\) \[ns\] \(or "N\/A" if SUCCESS\)\nNotes: <1-3 sentences explaining your reasoning>$/);
  // Without criteria the default statuses stand in.
  const plain = questionTemplate("calibration_diagnosis", input()).text;
  for (const code of Object.keys(DEFAULT_STATUSES)) assert.ok(plain.includes(`- ${code}: `), code);
  assert.match(plain, /suggested \(<min>, <max>\) of the swept parameter\./);
});

const EXAMPLES = [
  { images: [png("E1")], scenario: "Low contrast", analysis: "The contrast is 40%.", status: "LOW_CONTRAST", suggested_range: "(0, 200) [ns]" },
  { images: [png("E2")], scenario: "Clean cosine", analysis: "Textbook Rabi.", status: "SUCCESS", parameters: { rabi_frequency: 12.5 } },
  { images: [png("E3")], scenario: "Only a status", status: "no_signal" },
];

test("in-context Q3 shows each analysed example as figure then scenario analysis, query last", () => {
  const { text, images } = questionTemplate("experimental_significance", input({ examples: EXAMPLES, question: "Is it centred?" }));
  assert.equal(
    text,
    [
      BACKGROUND,
      "",
      "Experiment context: CheckRabi on Q05 (chip 64Qv3), completed.",
      "",
      "Here are example analyses for each scenario type in this experiment family:",
      "",
      '<image> Scenario "Low contrast":\nThe contrast is 40%.',
      "",
      '<image> Scenario "Clean cosine":\nTextbook Rabi.',
      "",
      "Also address: Is it centred?",
      "",
      "Now analyze this chart:",
      "",
      "<image>",
    ].join("\n"),
  );
  // The example without an analysis is not shown for Q3, and the query figure is last.
  assert.deepEqual(images, [png("E1"), png("E2"), png("QUERY")]);
});

test("in-context Q5 shows the first example with parameters, one-shot", () => {
  const { text, images } = questionTemplate("parameter_extraction", input({ examples: EXAMPLES }));
  assert.match(text, /Here is an example of parameter extraction from a similar chart:\n\n<image> Extracted parameters: \{"rabi_frequency":12\.5\}\n\nNow extract parameters from this chart:\n\n<image>$/);
  assert.deepEqual(images, [png("E2"), png("QUERY")]);
  // JSON text is shown as given.
  const asText = questionTemplate("parameter_extraction", input({ examples: [{ images: [png("T")], parameters: '{"t1": 14}' }] })).text;
  assert.match(asText, /Extracted parameters: \{"t1": 14\}/);
});

test("in-context Q6 shows every example with a status, labelled as the answer format", () => {
  const { text, images } = questionTemplate("calibration_diagnosis", input({ examples: EXAMPLES, criteria: { statuses: { SUCCESS: "ok", LOW_CONTRAST: "low" } } }));
  assert.match(text, /Classify this chart given the following labeled examples\.\n\nDECISION CRITERIA\n- SUCCESS: ok\n- LOW_CONTRAST: low\n\n<image> Status: LOW_CONTRAST\nSuggested range: \(0, 200\) \[ns\]\n\n<image> Status: SUCCESS\nSuggested range: N\/A\n\n<image> Status: NO_SIGNAL\nSuggested range: N\/A\n\nNow classify this chart:\n\n<image>$/);
  assert.deepEqual(images, [png("E1"), png("E2"), png("E3"), png("QUERY")]);
});

test("questions outside the in-context set ignore the examples", () => {
  for (const question of ["technical_description", "experimental_conclusion", "fit_reliability"]) {
    const { text, images } = questionTemplate(question, input({ examples: EXAMPLES }));
    assert.equal((text.match(/<image>/g) ?? []).length, 1, question);
    assert.deepEqual(images, [png("QUERY")], question);
  }
});

test("reference figures ahead of the measured one are shown first and announced", () => {
  const { text, images } = questionTemplate("fit_reliability", input({ images: [png("EXPECTED"), png("MEASURED")] }));
  assert.match(text, /^Reference figure for comparison \(expected result\); the last figure is the measured result to judge:\n<image>\n\n/);
  assert.deepEqual(images, [png("EXPECTED"), png("MEASURED")]);
});

test("examples beyond the budgets are dropped in order, and unlabeled ones skipped", () => {
  const many = Array.from({ length: MAX_EXAMPLES + 2 }, (_, i) => ({ images: [png(`E${i}`)], status: `S${i}` }));
  assert.equal(fitExamples(many).length, MAX_EXAMPLES);
  assert.deepEqual(
    fitExamples([
      { images: [png("A")], analysis: "  " },
      { images: [], status: "SUCCESS" },
      { images: [png("B")], status: "SUCCESS" },
      { images: [png("C"), png("D"), png("E"), png("F"), png("G"), png("H")], analysis: "too many figures" },
      { images: [png("I")], parameters: { t1: 1 } },
    ]),
    [{ images: [png("B")], status: "SUCCESS" }],
  );
});

test("the user turn interleaves text and figures at the <image> positions, and the record marks them", () => {
  const { content, prompt } = buildQuestionContent("experimental_significance", input({ examples: EXAMPLES.slice(0, 1) }));
  assert.deepEqual(
    content.map((block) => (block.type === "text" ? block.text.slice(0, 24) : `[${block.data}]`)),
    [
      "This is a CheckRabi expe",
      "[E1]",
      'Scenario "Low contrast":',
      "[QUERY]",
    ],
  );
  assert.match(prompt, /\[figure\] Scenario "Low contrast":\nThe contrast is 40%\.\n\nNow analyze this chart:\n\n\[figure\]$/);
  assert.doesNotMatch(prompt, /<image>/);
  assert.equal(
    promptRecord([
      { question: "technical_description", prompt: "A" },
      { question: "fit_reliability", prompt: "B" },
    ]),
    "## technical_description\nA\n\n## fit_reliability\nB",
  );
});

// ---------------------------------------------------------------------------
// Answers
// ---------------------------------------------------------------------------

test("answer text keeps text blocks and drops thinking", () => {
  const message = {
    content: [
      { type: "thinking", thinking: "looking at the plot" },
      { type: "text", text: '{"success": ' },
      { type: "text", text: "true}" },
    ],
  };
  assert.equal(answerText(message), '{"success": true}');
});

test("a JSON object is parsed from bare, fenced, or surrounded text, LaTeX escapes included", () => {
  assert.deepEqual(parseJsonObject('{"a": 1}'), { a: 1 });
  assert.deepEqual(parseJsonObject('```json\n{"a": {"b": [1, 2]}}\n```'), { a: { b: [1, 2] } });
  assert.deepEqual(parseJsonObject('Here you go:\n{"a": "x}y"}\nDone.'), { a: "x}y" });
  assert.deepEqual(parseJsonObject('{"phase": "$\\pi/2$"}'), { phase: "$\\pi/2$" });
  assert.equal(parseJsonObject("no object"), undefined);
  assert.equal(parseJsonObject("[1, 2]"), undefined);
});

test("labelled lines are read with or without markdown emphasis", () => {
  assert.equal(labeledLine("Classification: Expected behavior\nReason: fine", "Classification"), "Expected behavior");
  assert.equal(labeledLine("**Status:** NO_SIGNAL\n**Suggested range:** N/A", "Status"), "NO_SIGNAL");
  assert.equal(labeledLine("**Suggested range**: (0.1, 0.3)", "Suggested range"), "(0.1, 0.3)");
  assert.equal(labeledLine("nothing here", "Status"), undefined);
});

test("the four outcomes are read from the classification line, by key or by option", () => {
  assert.equal(parseOutcome("Classification: Expected behavior\nReason: ok"), "expected");
  assert.equal(parseOutcome("Classification: Suboptimal parameters"), "suboptimal");
  assert.equal(parseOutcome("**Classification:** Anomalous behavior"), "anomalous");
  assert.equal(parseOutcome("Classification: apparatus"), "apparatus");
  // Without the line, the first outcome named anywhere counts.
  assert.equal(parseOutcome("This looks like an apparatus issue to me."), "apparatus");
  assert.equal(parseOutcome("Hard to say."), null);
});

test("fit reliability distinguishes unreliable from reliable and recognises no fit", () => {
  assert.equal(parseFitAssessment("Assessment: Reliable\nReason: clean"), "reliable");
  assert.equal(parseFitAssessment("Assessment: Unreliable"), "unreliable");
  assert.equal(parseFitAssessment("Assessment: No fit\nReason: no curve drawn"), "no_fit");
  assert.equal(parseFitAssessment("The fit is unreliable."), "unreliable");
  assert.equal(parseFitAssessment("Maybe."), null);
});

test("status codes are normalised as the benchmark does", () => {
  assert.equal(normalizeStatus("NO_SIGNAL"), "NO_SIGNAL");
  assert.equal(normalizeStatus(" success "), "SUCCESS");
  assert.equal(normalizeStatus("`Optimal not centered`"), "OPTIMAL_NOT_CENTERED");
  assert.equal(normalizeStatus("NO_SIGNAL (flat data)"), "NO_SIGNAL");
  assert.equal(normalizeStatus("NO_SIGNAL - flat data"), "NO_SIGNAL");
  assert.equal(normalizeStatus(""), null);
  assert.equal(normalizeStatus(undefined), null);
});

test("each question's answer is parsed into the diagnosis shape for that question", () => {
  assert.deepEqual(parseAnswer("technical_description", '{"plot_type": "line", "main_features": "decay"}'), {
    plot_type: "line",
    main_features: "decay",
  });
  assert.equal(parseAnswer("technical_description", "A line plot."), "A line plot.");
  assert.deepEqual(parseAnswer("experimental_conclusion", "Classification: Suboptimal parameters\nReason: the window is\ntoo narrow"), {
    classification: "suboptimal",
    reason: "the window is\ntoo narrow",
  });
  assert.equal(parseAnswer("experimental_significance", "It implies X."), "It implies X.");
  assert.deepEqual(parseAnswer("fit_reliability", "Assessment: Unreliable\nReason: noisy"), {
    assessment: "unreliable",
    reason: "noisy",
  });
  assert.deepEqual(parseAnswer("parameter_extraction", '{"t1": "Unreliable"}'), { t1: "Unreliable" });
  assert.equal(parseAnswer("parameter_extraction", "null"), null);
  assert.equal(parseAnswer("parameter_extraction", "cannot read"), "cannot read");
  assert.deepEqual(
    parseAnswer("calibration_diagnosis", "Status: OPTIMAL_NOT_CENTERED\nSuggested range: (-0.012, -0.004)\nNotes: The crossing sits\nat the edge."),
    { status: "OPTIMAL_NOT_CENTERED", suggested_range: "(-0.012, -0.004)", notes: "The crossing sits\nat the edge." },
  );
  assert.deepEqual(parseAnswer("calibration_diagnosis", "Status: SUCCESS\nSuggested range: N/A\nNotes: Clean."), {
    status: "SUCCESS",
    suggested_range: null,
    notes: "Clean.",
  });
});

test("success follows the status, then the outcome when no status was asked", () => {
  assert.equal(assembleDiagnosis({ calibration_diagnosis: { status: "SUCCESS" } }).success, true);
  assert.equal(assembleDiagnosis({ calibration_diagnosis: { status: "NO_SIGNAL" }, experimental_conclusion: { classification: "expected" } }).success, false);
  assert.equal(assembleDiagnosis({ calibration_diagnosis: { status: null } }).success, null);
  assert.equal(assembleDiagnosis({ experimental_conclusion: { classification: "expected" } }).success, true);
  assert.equal(assembleDiagnosis({ experimental_conclusion: { classification: "apparatus" } }).success, false);
  assert.equal(assembleDiagnosis({ experimental_significance: "x" }).success, null);
  // Keys come out in the paper's order, whatever order they were answered in.
  assert.deepEqual(Object.keys(assembleDiagnosis({ fit_reliability: {}, technical_description: "d" })), [
    "technical_description",
    "fit_reliability",
    "success",
  ]);
});

const usage = (input, output) => ({
  input,
  output,
  cacheRead: 0,
  cacheWrite: 0,
  totalTokens: input + output,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
});
const reply = (text, extra = {}) => ({
  role: "assistant",
  content: [{ type: "text", text }],
  stopReason: "stop",
  usage: usage(10, 5),
  ...extra,
});
const REPLIES = {
  technical_description: '{"plot_type": "scatter"}',
  experimental_conclusion: "Classification: Expected behavior\nReason: clean",
  experimental_significance: "All good.",
  fit_reliability: "Assessment: Reliable\nReason: tight",
  parameter_extraction: '{"rabi_frequency": 12.5}',
  calibration_diagnosis: "Status: SUCCESS\nSuggested range: N/A\nNotes: Fine.",
};

test("every question is asked once, in its own call, and the answers make the diagnosis", async () => {
  const asked = [];
  const answers = await askQuestions(QUESTIONS, async (question) => {
    asked.push(question);
    return reply(REPLIES[question]);
  });
  assert.deepEqual(asked, QUESTIONS);
  assert.deepEqual(answers.diagnosis, {
    technical_description: { plot_type: "scatter" },
    experimental_conclusion: { classification: "expected", reason: "clean" },
    experimental_significance: "All good.",
    fit_reliability: { assessment: "reliable", reason: "tight" },
    parameter_extraction: { rabi_frequency: 12.5 },
    calibration_diagnosis: { status: "SUCCESS", suggested_range: null, notes: "Fine." },
    success: true,
  });
  assert.deepEqual(answers.answers, REPLIES);
  assert.deepEqual(answers.questions, QUESTIONS);
  assert.deepEqual(answers.missing, []);
  assert.equal(answers.attempts, 6);
  assert.equal(answers.stopReason, "stop");
  assert.equal(answers.usage.input, 60);
  assert.equal(answers.usage.output, 30);
  assert.deepEqual(
    answers.calls.map((c) => [c.question, c.stop_reason, c.input_tokens, c.output_tokens]),
    QUESTIONS.map((q) => [q, "stop", 10, 5]),
  );
});

test("a subset of questions is asked, and success follows the outcome when Q6 is absent", async () => {
  const answers = await askQuestions(["experimental_conclusion", "fit_reliability"], async (question) => reply(REPLIES[question]));
  assert.deepEqual(Object.keys(answers.diagnosis), ["experimental_conclusion", "fit_reliability", "success"]);
  assert.equal(answers.diagnosis.success, true);
  assert.equal(answers.attempts, 2);
});

test("a failed call is retried once; a question that still fails is missing, with its error", async () => {
  let now = 1000;
  const clock = () => now;
  const attempts = { fit_reliability: 0, calibration_diagnosis: 0 };
  const answers = await askQuestions(
    ["fit_reliability", "calibration_diagnosis"],
    async (question) => {
      now += 500;
      attempts[question] += 1;
      if (question === "fit_reliability" && attempts[question] === 1) {
        return reply("", { stopReason: "error", errorMessage: "502 upstream" });
      }
      if (question === "calibration_diagnosis") return reply("", { stopReason: "error", errorMessage: "timeout" });
      return reply(REPLIES[question]);
    },
    clock,
  );
  assert.deepEqual(attempts, { fit_reliability: 2, calibration_diagnosis: 2 });
  assert.deepEqual(answers.missing, ["calibration_diagnosis"]);
  assert.deepEqual(answers.errors, { calibration_diagnosis: "timeout" });
  assert.deepEqual(answers.diagnosis, { fit_reliability: { assessment: "reliable", reason: "tight" }, success: null });
  assert.equal(answers.attempts, 4);
  assert.deepEqual(
    answers.calls.map((c) => [c.question, c.stop_reason]),
    [
      ["fit_reliability", "error"],
      ["fit_reliability", "stop"],
      ["calibration_diagnosis", "error"],
      ["calibration_diagnosis", "error"],
    ],
  );
  // Calls run concurrently, so a shared fake clock only shows that each was timed.
  assert.ok(answers.calls.every((c) => Number.isInteger(c.duration_ms) && c.duration_ms >= 500));
  assert.equal(answers.stopReason, "stop");
});

test("an answer cut at the output budget marks the evaluation as length-stopped, and an empty one as missing", async () => {
  const answers = await askQuestions(["experimental_significance", "parameter_extraction"], async (question) =>
    question === "experimental_significance" ? reply("It implies", { stopReason: "length" }) : reply("   "),
  );
  assert.equal(answers.stopReason, "length");
  assert.deepEqual(answers.missing, ["parameter_extraction"]);
  assert.deepEqual(answers.errors, {});
  assert.equal(answers.diagnosis.experimental_significance, "It implies");
  // When every call failed, the last stop reason is the evaluation's.
  const failed = await askQuestions(["fit_reliability"], async () => reply("", { stopReason: "error", errorMessage: "down" }));
  assert.equal(failed.stopReason, "error");
  assert.deepEqual(failed.missing, ["fit_reliability"]);
});

test("usage of several calls is added, and one side alone is kept", () => {
  assert.equal(addUsage(undefined, undefined), undefined);
  assert.deepEqual(addUsage(usage(1, 2), undefined), usage(1, 2));
  const sum = addUsage(usage(10, 5), usage(20, 7));
  assert.equal(sum.input, 30);
  assert.equal(sum.output, 12);
  assert.equal(sum.totalTokens, 42);
  assert.equal(sum.reasoning, undefined);
  assert.equal(addUsage({ ...usage(1, 1), reasoning: 3 }, usage(1, 1)).reasoning, 3);
});

// ---------------------------------------------------------------------------
// The tool
// ---------------------------------------------------------------------------

import qcalevalExtension from "../.test-dist/extensions/qcaleval.js";

function registerTool() {
  let tool;
  qcalevalExtension({ registerTool: (definition) => { tool = definition; } });
  return tool;
}

const ISING = model("vllm", "nvidia/Ising-Calibration-1.5-31B-NVFP4");
const ctx = (available, complete) => ({
  model: undefined,
  modelRegistry: {
    ...registry(available),
    complete: async (_model, context, _options) => complete(context),
  },
});

test("a dry run returns the prompts by question without asking the model, figure optional", async () => {
  const tool = registerTool();
  assert.equal(tool.name, "qcal_evaluate");
  let asked = 0;
  const result = await tool.execute("c1", { context: "CheckRabi on Q05", knowledge: BACKGROUND, dry_run: true, questions: ["fit_reliability", "calibration_diagnosis"] }, undefined, undefined, ctx([ISING], () => { asked += 1; }));
  assert.equal(asked, 0);
  assert.equal(result.isError, undefined);
  assert.equal(result.details.dry_run, true);
  assert.deepEqual(result.details.model, { provider: "vllm", modelId: "nvidia/Ising-Calibration-1.5-31B-NVFP4" });
  assert.deepEqual(result.details.questions, ["fit_reliability", "calibration_diagnosis"]);
  assert.deepEqual(Object.keys(result.details.prompts), ["fit_reliability", "calibration_diagnosis"]);
  assert.match(result.details.prompts.fit_reliability, /^This is a CheckRabi experiment.*\n\nExperiment context: CheckRabi on Q05\n\nAssess whether the fit to the data in this plot \[figure\]/s);
  assert.match(result.details.prompt, /^## fit_reliability\n/);
  assert.equal(result.details.diagnosis, undefined);
  // Without any model the prompts are still shown.
  const none = await tool.execute("c2", { context: "", dry_run: true }, undefined, undefined, ctx([], () => {}));
  assert.equal(none.details.dry_run, true);
  assert.equal(none.details.model, undefined);
  assert.deepEqual(none.details.questions, QUESTIONS);
});

test("a real run asks each question with its own user turn and records the answers and prompts", async () => {
  const tool = registerTool();
  const turns = [];
  const result = await tool.execute(
    "c3",
    { context: "CheckRabi on Q05", knowledge: BACKGROUND, images: [png("QUERY")] },
    undefined,
    undefined,
    ctx([ISING], (context) => {
      turns.push(context);
      const text = context.messages[0].content.filter((b) => b.type === "text").map((b) => b.text).join("\n");
      const marks = {
        technical_description: "Describe the figure",
        experimental_conclusion: "classify the experimental outcome",
        experimental_significance: "What does this result",
        fit_reliability: "Assess whether the fit",
        parameter_extraction: "Extract the physical parameters",
        calibration_diagnosis: "determine the experiment status",
      };
      const question = QUESTIONS.find((q) => text.includes(marks[q]));
      return reply(REPLIES[question]);
    }),
  );
  assert.equal(turns.length, 6);
  assert.ok(turns.every((t) => t.systemPrompt === undefined && t.messages.length === 1 && t.messages[0].role === "user"));
  assert.ok(turns.every((t) => t.messages[0].content.some((b) => b.type === "image" && b.data === "QUERY")));
  assert.equal(result.details.diagnosis.success, true);
  assert.deepEqual(result.details.answers, REPLIES);
  assert.deepEqual(result.details.questions, QUESTIONS);
  assert.equal(result.details.attempts, 6);
  assert.deepEqual(Object.keys(result.details.prompts), QUESTIONS);
  assert.equal(result.details.dry_run, undefined);
  assert.equal(result.usage.input, 60);
  // No figure, no run.
  const missing = await tool.execute("c4", { context: "x" }, undefined, undefined, ctx([ISING], () => {}));
  assert.equal(missing.isError, true);
  assert.match(missing.content[0].text, /no plot was given/);
});

test("a model named in the call is used when configured; an unknown one is an error", async () => {
  const tool = registerTool();
  const other = model("vllm", "other-vlm");
  const used = [];
  const complete = (context) => {
    used.push(context.messages.length);
    return reply(REPLIES.fit_reliability);
  };
  const registryCtx = { model: undefined, modelRegistry: { ...registry([ISING, other]), complete: async (m, context) => { used.push(m.id); return complete(context); } } };
  const result = await tool.execute("c5", { context: "x", images: [png("Q")], questions: ["fit_reliability"], model: "vllm/other-vlm" }, undefined, undefined, registryCtx);
  assert.deepEqual(result.details.model, { provider: "vllm", modelId: "other-vlm" });
  assert.ok(used.includes("other-vlm"));
  const missing = await tool.execute("c6", { context: "x", images: [png("Q")], model: "vllm/missing" }, undefined, undefined, registryCtx);
  assert.equal(missing.isError, true);
  assert.match(missing.content[0].text, /not configured/);
  const malformed = await tool.execute("c7", { context: "x", images: [png("Q")], model: "no-slash" }, undefined, undefined, registryCtx);
  assert.equal(malformed.isError, true);
  assert.match(malformed.content[0].text, /provider\/modelId/);
  // A dry run reports the named model too.
  const dry = await tool.execute("c8", { context: "x", dry_run: true, model: "vllm/other-vlm" }, undefined, undefined, registryCtx);
  assert.deepEqual(dry.details.model, { provider: "vllm", modelId: "other-vlm" });
});
