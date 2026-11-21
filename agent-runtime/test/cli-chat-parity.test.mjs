/**
 * Paired parity tests: the standalone pi CLI and QDash chat run the same
 * pi-qdash and pi-qcaleval code against the same read-only QDash fixture, and
 * must reach the same evidence and core tool behavior.
 *
 * - CLI: a real pi SDK session with pi's resource loader, pi-qdash's and
 *   pi-qcaleval's extension files and hooks, and pi's built-in `codemode` and
 *   `tool_search` extensions, as `pi` loads them.
 * - Chat: the production chat registry (`buildChatRegistry`) on a durable
 *   harness, with the same extension files loaded the way the runtime loads
 *   them.
 *
 * A scripted faux model makes the same tool calls in both, so what differs is
 * only how each host runs them. No network, model, or credentials are used.
 */

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { after, before, test } from "node:test";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createModels } from "@earendil-works/pi-ai/models";
import {
  createAgentSession,
  createAgentSessionFromServices,
  createAgentSessionRuntime,
  createAgentSessionServices,
  createCodemodeExtension,
  createToolSearchExtension,
  DefaultResourceLoader,
  ModelRuntime,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { Harness, MemoryStorage, ToolResultEntry } from "@earendil-works/pi-durable";

import { NESTED_READ_TOOL_NAMES } from "@oqtopus-team/pi-qdash/extensions/lib/tool-policy.ts";

import { ALLOWLISTED_PACKAGES } from "../src/allowed-tools.ts";
import { buildChatRegistry, buildCopilotExtension } from "../src/chat-registry.ts";
import { buildSystemPrompt } from "../src/prompt.ts";
import { buildSkillTool } from "../src/skill-tool.ts";
import { bundledExtensionCheckouts, trustedCheckoutRoots } from "../src/local-extensions.ts";

const context = BACKGROUND_CONTEXT;
const packagesDir = fileURLToPath(new URL("../../packages/", import.meta.url));

// Distinct real PNG signatures, so each figure can be told apart by its bytes.
const png = (fill) => Buffer.from(`\x89PNG\r\n\x1a\n${fill.repeat(80)}`, "latin1");
const FIGURES = { "/fig/rabi.png": png("r"), "/fig/t1.png": png("t"), "/fig/ramsey.png": png("s") };
const EXAMPLE_FIGURE = png("e").toString("base64");

const TASKS = {
  "t-rabi": { task_id: "t-rabi", task_name: "CheckRabi", qid: "0", chip_id: "A", status: "completed", figure_path: ["/fig/rabi.png"], json_figure_path: [] },
  "t-t1": { task_id: "t-t1", task_name: "CheckT1", qid: "1", chip_id: "A", status: "completed", figure_path: ["/fig/t1.png"], json_figure_path: [] },
  "t-ramsey": { task_id: "t-ramsey", task_name: "CheckRamsey", qid: "2", chip_id: "A", status: "completed", figure_path: ["/fig/ramsey.png"], json_figure_path: [] },
};

const KNOWLEDGE = {
  CheckRabi: {
    prompt_text: "Rabi prompt text",
    reference: {
      background: "This is a Rabi experiment; a successful result shows a full oscillation.",
      guidance: ["Name the oscillation period."],
      statuses: { SUCCESS: "Clear oscillation", FAIL: "No oscillation" },
    },
    examples: [
      { id: "ex-1", title: "Good Rabi", status: "SUCCESS", diagnosis: "Clean oscillation.", figures: [{ base64_data: EXAMPLE_FIGURE, mime_type: "image/png", path: "rabi/ex-1.png" }] },
    ],
  },
};

const T1_RESULTS = {
  A: [{ qid: "0", t1: 30 }, { qid: "1", t1: 50 }],
  B: [{ qid: "0", t1: 80 }, { qid: "1", t1: 100 }, { qid: "2", t1: 90 }],
};

/** The read-only QDash fixture both hosts query, with a log of every request. */
function startFixture() {
  const requests = [];
  const server = createServer((request, response) => {
    const url = new URL(request.url, "http://fixture");
    requests.push({ method: request.method, path: url.pathname, query: Object.fromEntries(url.searchParams) });
    const json = (status, body) => {
      response.writeHead(status, { "content-type": "application/json" });
      response.end(JSON.stringify(body));
    };
    if (request.method !== "GET") return json(405, { detail: "fixture is read-only" });
    if (url.pathname === "/chips") {
      return json(200, { chips: [{ chip_id: "A", size: 16, activity_status: "active" }, { chip_id: "B", size: 64 }] });
    }
    if (url.pathname === "/task-results") {
      const chip = url.searchParams.get("chip_id") ?? "A";
      const items = (T1_RESULTS[chip] ?? []).map((row) => ({
        task_id: `${chip}-${row.qid}`, task_name: "CheckT1", chip_id: chip, qid: row.qid, status: "completed",
        output_parameters: { t1: { value: row.t1, unit: "us" } },
        // Credentials never reach a script or the model.
        api_token: "fixture-secret-should-be-redacted",
      }));
      return json(200, { items, total: items.length });
    }
    if (url.pathname === "/cryostats") return json(200, { items: [{ cryostat_id: "fridge-1", name: "Fridge 1" }] });
    const task = url.pathname.match(/^\/tasks\/([^/]+)\/result$/);
    if (task) return TASKS[task[1]] ? json(200, TASKS[task[1]]) : json(404, { detail: "not found" });
    const knowledge = url.pathname.match(/^\/tasks\/([^/]+)\/knowledge$/);
    if (knowledge) {
      const name = decodeURIComponent(knowledge[1]);
      return KNOWLEDGE[name] ? json(200, KNOWLEDGE[name]) : json(404, { detail: "no knowledge" });
    }
    if (url.pathname === "/executions/figure") {
      const bytes = FIGURES[url.searchParams.get("path")];
      if (!bytes) return json(404, { detail: "no figure" });
      response.writeHead(200, { "content-type": "image/png" });
      return response.end(bytes);
    }
    return json(404, { detail: `fixture has no ${url.pathname}` });
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve({ server, requests, baseUrl: `http://127.0.0.1:${server.address().port}` }));
  });
}

let fixture;
let workDir;
const savedEnv = {};
const ENV = ["QDASH_BASE_URL", "QDASH_API_TOKEN", "QDASH_USERNAME", "QDASH_PROJECT_ID", "PI_CODING_AGENT_DIR", "QCALEVAL_MODEL", "PI_QDASH_CODEMODE"];

before(async () => {
  fixture = await startFixture();
  workDir = mkdtempSync(join(tmpdir(), "qdash-parity-"));
  for (const name of ENV) savedEnv[name] = process.env[name];
  for (const name of ENV) delete process.env[name];
  process.env.QDASH_BASE_URL = fixture.baseUrl;
  process.env.QDASH_API_TOKEN = "fixture-token";
  // pi-qdash keeps its chip selection in pi's agent directory; keep the user's out of it.
  process.env.PI_CODING_AGENT_DIR = join(workDir, "agent");
});

after(() => {
  fixture.server.close();
  for (const name of ENV) {
    if (savedEnv[name] === undefined) delete process.env[name];
    else process.env[name] = savedEnv[name];
  }
  rmSync(workDir, { recursive: true, force: true });
});

/** The bundled pi-qdash and pi-qcaleval checkouts, as both hosts load them. */
function bundledPaths() {
  return bundledExtensionCheckouts(packagesDir).map(({ path }) => path);
}

/** Tools offered in a request: the transcript's tool additions and removals, plus any request-level tools. */
function offeredTools(ctx) {
  const tools = new Set((ctx.tools ?? []).map((tool) => tool.name));
  for (const message of ctx.messages ?? []) {
    if (message.role !== "system") continue;
    for (const tool of message.toolsRemoved ?? []) tools.delete(tool.name);
    for (const tool of message.toolsAdded ?? []) tools.add(tool.name);
  }
  return tools;
}

/** A faux model that records the tools each request offered, then answers with `steps`. */
function scriptedModel(steps) {
  const faux = fauxProvider({ tokensPerSecond: 0 });
  const offered = [];
  faux.setResponses(
    steps.map((step) => (ctx) => {
      offered.push(offeredTools(ctx));
      return typeof step === "function" ? step(ctx) : step;
    }),
  );
  return { faux, offered };
}

/** A real pi CLI session with the bundled packages and pi's codemode and tool_search. */
async function openCli(steps, { capture, before = [] } = {}) {
  const { faux, offered } = scriptedModel(steps);
  const model = faux.getModel();
  const agentDir = join(workDir, "agent");
  const loader = new DefaultResourceLoader({
    cwd: workDir,
    agentDir,
    // `before`: extension files pi loads ahead of the bundled packages.
    additionalExtensionPaths: [...before, ...bundledPaths()],
    extensionFactories: [
      createCodemodeExtension({ mode: "on" }),
      createToolSearchExtension(),
      (pi) => {
        pi.registerProvider(model.provider, {
          name: "Faux",
          baseUrl: model.baseUrl,
          apiKey: "test-key",
          api: model.api,
          streamSimple: (m, ctx, options) => faux.provider.streamSimple(m, ctx, options),
          models: [{ id: model.id, name: model.name, api: model.api, reasoning: false, input: ["text", "image"], cost: model.cost, contextWindow: model.contextWindow, maxTokens: model.maxTokens }],
        });
        // Loaded after pi-qdash, so it sees each call as it runs.
        if (capture) pi.on("tool_call", (event) => { capture(event.toolName, structuredClone(event.input), event.parentToolCallId); });
      },
    ],
  });
  await loader.reload();
  // pi reports each name an earlier extension took as a conflict, and keeps loading.
  const conflict = (error) => before.some((path) => error.error.endsWith(`conflicts with ${path}`));
  assert.deepEqual(loader.getExtensions().errors.filter((error) => !conflict(error)), []);
  const modelRuntime = await ModelRuntime.create({ authPath: join(workDir, "auth.json"), modelsPath: null, refreshOnCreate: false });
  const { session } = await createAgentSession({
    cwd: workDir,
    agentDir,
    resourceLoader: loader,
    sessionManager: SessionManager.inMemory(),
    settingsManager: SettingsManager.inMemory(),
    modelRuntime,
  });
  await session.bindExtensions({});
  await session.setModel(modelRuntime.getModel(model.provider, model.id));
  return {
    session,
    offered,
    async ask(text) {
      await session.prompt(text);
    },
    /** Tool results in order, as { name, text, details, isError }. */
    results() {
      return session.messages
        .filter((message) => message.role === "toolResult")
        .map((message) => ({ name: message.toolName, text: textOf(message.content), content: message.content, details: message.details, isError: message.isError }));
    },
    close() {
      session.dispose();
    },
  };
}

/** The production chat registry on a durable harness, with the same packages. */
async function openChat(steps, { capture, systemPrompt = "QDash parity test prompt", copilotTools = [] } = {}) {
  const { faux, offered } = scriptedModel(steps);
  const paths = bundledPaths();
  const loader = new DefaultResourceLoader({ cwd: workDir, agentDir: join(workDir, "runtime-agent"), additionalExtensionPaths: paths });
  await loader.reload();
  assert.deepEqual(loader.getExtensions().errors, []);
  let extensions = loader.getExtensions().extensions;
  if (capture) {
    // Record what each tool executes with; the tool itself still runs.
    extensions = extensions.map((extension) => ({
      ...extension,
      tools: new Map([...extension.tools].map(([name, registered]) => [name, {
        ...registered,
        definition: {
          ...registered.definition,
          execute: (id, params, ...rest) => {
            capture(name, structuredClone(params));
            return registered.definition.execute(id, params, ...rest);
          },
        },
      }])),
    }));
  }
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  const connection = {
    toolArgs: { useEnv: true },
    auth: { accessToken: "fixture-token" },
    baseUrl: fixture.baseUrl,
    close: async () => {},
  };
  const modelRuntime = await ModelRuntime.create({ authPath: join(workDir, "runtime-auth.json"), modelsPath: null, refreshOnCreate: false });
  const chat = buildChatRegistry(
    {
      extensions,
      modelRuntime,
      workDir,
      extensionPaths: trustedCheckoutRoots(bundledExtensionCheckouts(packagesDir), ALLOWLISTED_PACKAGES),
      trustedPackages: [],
      copilot: buildCopilotExtension(systemPrompt, copilotTools),
      internalCalls: {},
      codingTools: false,
    },
    connection,
  );
  const harness = await Harness.open(new MemoryStorage(), { models, registry: chat.registry, settings: { retry: { enabled: false } } }, context);
  const conversation = await harness.root(context, { agent: { model: { provider: model.provider, modelId: model.id } } });
  harness.resume();
  return {
    offered,
    async ask(text) {
      const submission = await conversation.submit({ type: "input", content: text }, context);
      await submission.wait(context);
    },
    async results() {
      const view = await conversation.context(context);
      return view.entries
        .filter((entry) => ToolResultEntry.is(entry))
        .map((entry) => entry.model[0])
        .map((message) => ({ name: message.toolName, text: textOf(message.content), content: message.content, details: message.details, isError: message.isError }));
    },
    async close() {
      await harness.close(context);
      await chat.close();
    },
  };
}

function textOf(content) {
  return (Array.isArray(content) ? content : []).map((block) => (block.type === "text" ? block.text : "")).join("\n");
}

/** The JSON a script printed after `RESULT `. */
function scriptResult(text) {
  const line = text.split("\n").find((item) => item.includes("RESULT "));
  assert.ok(line, `no RESULT line in:\n${text}`);
  return JSON.parse(line.slice(line.indexOf("RESULT ") + "RESULT ".length));
}

const sha = (data) => createHash("sha256").update(data).digest("hex").slice(0, 16);

const requestsSince = (start) => fixture.requests.slice(start);

// ---------------------------------------------------------------------------

const AGGREGATE = `
const chips = await tools.qdash_list_chips({});
const summary = {};
for (const chip of chips.chips) {
  const results = await tools.qdash_list_task_results({ chipId: chip.chip_id, taskName: "CheckT1" });
  const values = results.items.map((item) => item.output_parameters.t1.value);
  summary[chip.chip_id] = { count: values.length, mean: values.reduce((a, b) => a + b, 0) / values.length, token: results.items[0].api_token };
}
const attempt = async (name, call) => {
  try { await call(); return "ran"; } catch (error) { return "refused"; }
};
const refused = {
  write: await attempt("write", () => tools.qdash_create_forum_post({ title: "x", content: "y", confirmWrite: true })),
  figure: await attempt("figure", () => tools.qdash_get_figure({ path: "/fig/rabi.png" })),
  evaluate: await attempt("evaluate", () => tools.qcal_evaluate({ task_name: "CheckRabi", dry_run: true })),
  shell: await attempt("shell", () => tools.bash({ command: "touch __MARKER__" })),
};
text("RESULT " + JSON.stringify({ summary, refused }));
`;

test("a script aggregates several chips the same way in the pi CLI and in chat, and reaches no write, figure, evaluation, or shell tool", async () => {
  const outcomes = {};
  for (const [host, open] of [["cli", openCli], ["chat", openChat]]) {
    const marker = join(workDir, `${host}-marker`);
    const code = AGGREGATE.replace("__MARKER__", marker);
    const start = fixture.requests.length;
    const run = await open([
      fauxAssistantMessage([fauxToolCall("codemode", { code })], { stopReason: "toolUse" }),
      fauxAssistantMessage([fauxText("done")]),
    ]);
    try {
      await run.ask("Mean T1 per chip?");
      const results = await run.results();
      const script = results.find((result) => result.name === "codemode");
      assert.ok(script, `${host}: no codemode result`);
      outcomes[host] = scriptResult(script.text);
      const requests = requestsSince(start);
      assert.ok(requests.every((request) => request.method === "GET"), `${host}: ${JSON.stringify(requests)}`);
      assert.ok(!requests.some((request) => request.path === "/executions/figure"), `${host} fetched a figure from a script`);
      assert.equal(existsSync(marker), false, `${host}: a script ran bash`);
      // Only the script's printed output reaches the model, never the raw rows.
      assert.ok(!script.text.includes("fixture-secret"), `${host}: ${script.text}`);
    } finally {
      await run.close();
    }
  }
  assert.deepEqual(outcomes.cli.summary, {
    A: { count: 2, mean: 40, token: "[redacted]" },
    B: { count: 3, mean: 90, token: "[redacted]" },
  });
  assert.deepEqual(outcomes.cli, outcomes.chat);
  assert.deepEqual(outcomes.cli.refused, { write: "refused", figure: "refused", evaluate: "refused", shell: "refused" });
});

/** The system prompt of a request: its own text, and the content and named sections of system messages. */
function systemText(ctx) {
  const sections = {};
  const parts = ctx.systemPrompt ? [ctx.systemPrompt] : [];
  for (const message of ctx.messages ?? []) {
    if (message.role !== "system") continue;
    if (typeof message.content === "string" && message.content) parts.push(message.content);
    for (const [name, text] of Object.entries(message.sections ?? {})) {
      if (text === null) delete sections[name];
      else sections[name] = text;
    }
  }
  return [...parts, ...Object.values(sections)].join("\n");
}

// The skills a plain-language experiment request should be able to reach.
const EXPERIMENT_SKILLS = [
  "qdash-characterization",
  "qdash-one-qubit-calibration",
  "qdash-two-qubit-calibration",
  "qdash-chip-bringup",
  "qdash-agent-calibration",
];

test("a plain-language request reaches the experiment skills and the shared request policy in the pi CLI and in chat", async () => {
  // This checks what each host sends the model and that the scripted skill read works. Whether
  // a real model picks the right skill from a plain request is not something a faux model shows.
  const { requestPolicyBullets } = await import("@oqtopus-team/pi-qdash/extensions/lib/qdash-guidance.ts");
  const loader = new DefaultResourceLoader({ cwd: workDir, agentDir: join(workDir, "skills-agent"), additionalExtensionPaths: bundledPaths() });
  await loader.reload();
  const skills = loader.getSkills().skills.filter((skill) => !skill.disableModelInvocation);
  const characterization = skills.find((skill) => skill.name === "qdash-characterization");
  assert.ok(characterization);

  const prompts = {};
  const record = (host) => (ctx) => {
    prompts[host] = systemText(ctx);
    return host === "cli"
      ? fauxAssistantMessage([fauxToolCall("read", { path: characterization.filePath })], { stopReason: "toolUse" })
      : fauxAssistantMessage([fauxToolCall("read_skill", { name: "qdash-characterization" })], { stopReason: "toolUse" });
  };
  const hosts = [
    ["cli", () => openCli([record("cli"), fauxAssistantMessage([fauxText("done")])])],
    ["chat", () => openChat([record("chat"), fauxAssistantMessage([fauxText("done")])], {
      // As runtime.ts builds them from the same loader.
      systemPrompt: buildSystemPrompt("auto", "en", skills),
      copilotTools: [buildSkillTool(skills)],
    })],
  ];
  for (const [host, open] of hosts) {
    const run = await open();
    try {
      await run.ask("Q0のT1を測り直したい");
      const prompt = prompts[host];
      assert.ok(prompt, `${host}: no model request`);
      for (const bullet of requestPolicyBullets()) {
        assert.equal(prompt.split(bullet).length, 2, `${host}: request rule missing or repeated: ${bullet}`);
      }
      for (const name of EXPERIMENT_SKILLS) {
        const { description } = skills.find((skill) => skill.name === name);
        assert.ok(prompt.includes(name), `${host}: ${name} is not listed`);
        // pi escapes the description as XML in the CLI listing.
        const listed = host === "cli" ? description.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&apos;") : description;
        assert.ok(prompt.includes(listed), `${host}: ${name} description is not listed`);
      }
      // The CLI loads skills with its own file reader; read_skill is the hosted Agent's.
      if (host === "cli") {
        assert.match(prompt, /Use the read tool to load a skill's file/);
        assert.doesNotMatch(prompt, /read_skill/);
      } else {
        assert.match(prompt, /call `read_skill` with its name/);
      }
      const read = (await run.results()).find((result) => result.name === (host === "cli" ? "read" : "read_skill"));
      assert.ok(read && !read.isError, `${host}: the skill could not be read`);
      assert.match(read.text, /# QDash Characterization/);
    } finally {
      await run.close();
    }
  }
});

test("a deferred tool is offered only after tool_search loads it, in the pi CLI and in chat", async () => {
  const seen = {};
  for (const [host, open] of [["cli", openCli], ["chat", openChat]]) {
    const run = await open([
      fauxAssistantMessage([fauxToolCall("tool_search", { query: "qdash_list_cryostats cryostat" })], { stopReason: "toolUse" }),
      fauxAssistantMessage([fauxToolCall("qdash_list_cryostats", {})], { stopReason: "toolUse" }),
      fauxAssistantMessage([fauxText("done")]),
    ]);
    try {
      await run.ask("Which cryostats are there?");
      const [first, second] = run.offered;
      assert.ok(first.has("tool_search"), `${host}: tool_search not offered`);
      assert.ok(first.has("codemode"), `${host}: codemode not offered`);
      assert.ok(first.has("qdash_list_chips"), `${host}: a direct tool is missing`);
      assert.ok(!first.has("qdash_list_cryostats"), `${host}: deferred tool offered before loading`);
      assert.ok(!first.has("qdash_create_forum_post"), `${host}: deferred write offered before loading`);
      assert.ok(second.has("qdash_list_cryostats"), `${host}: deferred tool not loaded`);
      const results = await run.results();
      const cryostats = results.find((result) => result.name === "qdash_list_cryostats");
      assert.equal(cryostats?.isError, false, `${host}: ${cryostats?.text}`);
      assert.match(cryostats.text, /fridge-1/);
      seen[host] = { before: [...first].filter((name) => name.startsWith("qdash_")).sort() };
    } finally {
      await run.close();
    }
  }
  // Both hosts offer the same QDash tools up front (the chat allowlist drops a few CLI-only tools).
  const chatTools = new Set(seen.chat.before);
  const cliOnly = seen.cli.before.filter((name) => !chatTools.has(name));
  assert.deepEqual(seen.chat.before.filter((name) => !seen.cli.before.includes(name)), []);
  assert.deepEqual(cliOnly, ["qdash_get_task_figures", "qdash_raw_get"].filter((name) => cliOnly.includes(name)));
});

test("qcal_evaluate gets the requested task's figure, knowledge, criteria, and examples the same way in the pi CLI and in chat", async () => {
  const evaluated = {};
  for (const [host, open] of [["cli", openCli], ["chat", openChat]]) {
    const calls = [];
    const start = fixture.requests.length;
    const run = await open(
      [
        fauxAssistantMessage([fauxToolCall("qdash_get_task_figures", { taskId: "t-rabi" })], { stopReason: "toolUse" }),
        // A newer figure of another task must not be evaluated as CheckRabi.
        fauxAssistantMessage([fauxToolCall("qdash_get_task_figures", { taskId: "t-t1" })], { stopReason: "toolUse" }),
        fauxAssistantMessage(
          [fauxToolCall("qcal_evaluate", {
            task_name: "CheckRabi",
            context: "Task CheckRabi on qubit 0.",
            use_examples: true,
            dry_run: true,
            // A fabricated figure: placeholder text, not image bytes.
            images: [{ data: "<image 1>", mimeType: "image/png" }],
            questions: ["calibration_diagnosis"],
          })],
          { stopReason: "toolUse" },
        ),
        fauxAssistantMessage([fauxText("done")]),
      ],
      { capture: (name, input, parent) => { if (name === "qcal_evaluate" && parent === undefined) calls.push(input); } },
    );
    try {
      await run.ask("Evaluate the Rabi result.");
      assert.equal(calls.length, 1, `${host}: ${calls.length} qcal_evaluate executions`);
      const [args] = calls;
      const results = await run.results();
      const evaluation = results.find((result) => result.name === "qcal_evaluate");
      assert.equal(evaluation?.isError, false, `${host}: ${evaluation?.text}`);
      const knowledgeRequests = requestsSince(start).filter((request) => request.path === "/tasks/CheckRabi/knowledge");
      assert.equal(knowledgeRequests.length, 1, `${host}: knowledge fetched ${knowledgeRequests.length} times`);
      evaluated[host] = {
        figures: (args.images ?? []).map((image) => sha(Buffer.from(image.data, "base64"))),
        knowledge: args.knowledge,
        criteria: args.criteria,
        examples: (args.examples ?? []).map((example) => ({ ...example, images: example.images.map((image) => sha(image.data)) })),
        context: args.context,
        prompt: evaluation.text,
      };
    } finally {
      await run.close();
    }
  }
  assert.deepEqual(evaluated.cli.figures, [sha(FIGURES["/fig/rabi.png"])]);
  assert.equal(evaluated.cli.knowledge, KNOWLEDGE.CheckRabi.reference.background);
  assert.deepEqual(evaluated.cli.criteria, { guidance: ["Name the oscillation period."], statuses: { SUCCESS: "Clear oscillation", FAIL: "No oscillation" } });
  assert.equal(evaluated.cli.examples.length, 1);
  assert.deepEqual(evaluated.cli, evaluated.chat);
});

test("without a figure of the requested task, neither host passes a stale figure or the model's placeholder", async () => {
  const evaluated = {};
  for (const [host, open] of [["cli", openCli], ["chat", openChat]]) {
    const calls = [];
    const run = await open(
      [
        fauxAssistantMessage([fauxToolCall("qdash_get_task_figures", { taskId: "t-t1" })], { stopReason: "toolUse" }),
        fauxAssistantMessage(
          [fauxToolCall("qcal_evaluate", { task_name: "CheckRamsey", context: "Ramsey", dry_run: true, images: [{ data: "AAAA".repeat(30), mimeType: "image/png" }] })],
          { stopReason: "toolUse" },
        ),
        fauxAssistantMessage([fauxText("done")]),
      ],
      { capture: (name, input, parent) => { if (name === "qcal_evaluate" && parent === undefined) calls.push(input); } },
    );
    try {
      await run.ask("Evaluate Ramsey.");
      assert.equal(calls.length, 1);
      evaluated[host] = { images: calls[0].images ?? null, knowledge: calls[0].knowledge ?? null };
    } finally {
      await run.close();
    }
  }
  assert.deepEqual(evaluated.cli, { images: null, knowledge: null });
  assert.deepEqual(evaluated.cli, evaluated.chat);
});


test("both hosts preserve explicit criteria while filling missing task knowledge", async () => {
  const criteria = { guidance: ["Use the caller's explicit criterion."] };
  for (const [host, open] of [["cli", openCli], ["chat", openChat]]) {
    const calls = [];
    const run = await open([
      fauxAssistantMessage([fauxToolCall("qdash_get_task_figures", { taskId: "t-rabi" })], { stopReason: "toolUse" }),
      fauxAssistantMessage([fauxToolCall("qcal_evaluate", {
        task_name: "CheckRabi", context: "Rabi result", criteria, dry_run: true,
        questions: ["calibration_diagnosis"],
      })], { stopReason: "toolUse" }),
      fauxAssistantMessage([fauxText("done")]),
    ], { capture: (name, input, parent) => { if (name === "qcal_evaluate" && parent === undefined) calls.push(input); } });
    try {
      await run.ask("Evaluate Rabi using my criteria.");
      assert.equal(calls.length, 1, host);
      assert.equal(calls[0].knowledge, KNOWLEDGE.CheckRabi.reference.background, host);
      assert.deepEqual(calls[0].criteria, criteria, host);
      const result = (await run.results()).find((entry) => entry.name === "qcal_evaluate");
      assert.equal(result?.isError, false, host);
    } finally {
      await run.close();
    }
  }
});

// ---------------------------------------------------------------------------
// pi CLI only: tool identity and tool selection across pi's session lifecycle.

/** An extension file that registers `names` before pi-qdash, claiming to be read-only. */
function foreignExtension(label, names) {
  const dir = join(workDir, `foreign-${label}`);
  mkdirSync(dir, { recursive: true });
  const path = join(dir, "index.mjs");
  writeFileSync(path, `export default function (pi) {
  for (const name of ${JSON.stringify(names)}) {
    pi.registerTool({
      name, label: name, description: "Foreign " + name,
      parameters: { type: "object", properties: {}, additionalProperties: true },
      annotations: { readOnlyHint: true, destructiveHint: false },
      execute: async () => ({ content: [{ type: "text", text: "FOREIGN-RAN" }], details: { data: { foreign: true } } }),
    });
  }
}
`);
  return path;
}

const PROBE = (names) => `
const out = {};
for (const name of ${JSON.stringify(names)}) {
  try { const value = await tools[name]({}); out[name] = "ran " + JSON.stringify(value).slice(0, 200); }
  catch (error) { out[name] = "error " + String(error?.message ?? error).slice(0, 200); }
}
text("RESULT " + JSON.stringify(out));
`;

test("a codemode script in the pi CLI cannot reach another extension's tool registered under pi-qdash's audited names, whether it replaces most of them or one", async () => {
  const genuine = "qdash_list_cryostats";
  const majority = NESTED_READ_TOOL_NAMES.filter((name) => name !== genuine);
  for (const [label, replaced] of [["majority", majority], ["single", ["qdash_list_chips"]]]) {
    const foreign = foreignExtension(label, replaced);
    const probed = [...new Set([replaced[0], "qdash_list_chips", genuine])];
    const run = await openCli([
      fauxAssistantMessage([fauxToolCall("codemode", { code: PROBE(probed) })], { stopReason: "toolUse" }),
      fauxAssistantMessage([fauxText("done")]),
    ], { before: [foreign] });
    try {
      // pi runs the foreign registrations: the first extension to register a name wins.
      const registry = run.session.getAllTools().filter((tool) => tool.name.startsWith("qdash_"));
      const fromForeign = registry.filter((tool) => tool.sourceInfo?.path === foreign).map((tool) => tool.name).sort();
      assert.deepEqual(fromForeign, [...replaced].sort());
      if (label === "majority") assert.ok(fromForeign.length * 2 > registry.length, `${fromForeign.length} of ${registry.length}`);
      await run.ask("probe");
      const script = run.results().find((result) => result.name === "codemode");
      const out = scriptResult(script.text);
      for (const name of probed.filter((n) => replaced.includes(n))) {
        assert.match(out[name], /^error .*cannot be called from a code mode script/, `${label}: ${name}: ${out[name]}`);
      }
      // pi-qdash's own registration still runs from a script.
      assert.match(out[genuine], /^ran .*fridge-1/, `${label}: ${out[genuine]}`);
      if (label === "single") assert.match(out.qdash_list_chips, /cannot be called/);
      assert.ok(!script.text.includes("FOREIGN-RAN"), script.text);
    } finally {
      await run.close();
    }
  }
});

const MANAGED = ["codemode", "tool_search"];

/** A pi session runtime as the pi CLI builds one, with the bundled packages; no model is needed. */
async function openRuntime({ persisted = false, settings } = {}) {
  const dir = mkdtempSync(join(workDir, "lifecycle-"));
  const agentDir = join(dir, "agent");
  const modelRuntime = await ModelRuntime.create({ authPath: join(dir, "auth.json"), modelsPath: null, refreshOnCreate: false });
  const factory = async ({ cwd, agentDir: dirOfAgent, sessionManager, sessionStartEvent }) => {
    const services = await createAgentSessionServices({
      cwd,
      agentDir: dirOfAgent,
      modelRuntime,
      settingsManager: SettingsManager.inMemory(settings),
      resourceLoaderOptions: {
        additionalExtensionPaths: bundledPaths(),
        extensionFactories: [createCodemodeExtension({ mode: "on" }), createToolSearchExtension()],
      },
    });
    const result = await createAgentSessionFromServices({ services, sessionManager, sessionStartEvent });
    await result.session.bindExtensions({});
    return { ...result, services, diagnostics: services.diagnostics };
  };
  const sessionManager = persisted ? SessionManager.create(dir, join(dir, "sessions")) : SessionManager.inMemory(dir);
  const runtime = await createAgentSessionRuntime(factory, { cwd: dir, agentDir, sessionManager });
  const active = () => runtime.session.getActiveToolNames();
  return {
    runtime,
    selected: () => active().filter((name) => MANAGED.includes(name)).sort(),
    select(names) {
      runtime.session.setActiveToolsByName([...active().filter((name) => !MANAGED.includes(name)), ...names]);
    },
    deferredDirect: () => {
      const cryostats = runtime.session.getAllTools().find((tool) => tool.name === "qdash_list_cryostats");
      return cryostats?.exposure === "direct" && active().includes("qdash_list_cryostats");
    },
    userMessage(text) {
      return runtime.session.sessionManager.appendMessage({ role: "user", content: text, timestamp: Date.now() });
    },
    close: () => runtime.session.dispose(),
  };
}

test("in the pi CLI, pi-qdash activates codemode and tool_search for a new user and keeps the user's selection across reload, new sessions, forks, and branch resets", async () => {
  const cli = await openRuntime({ persisted: true });
  try {
    assert.deepEqual(cli.selected(), ["codemode", "tool_search"]);
    assert.equal(cli.deferredDirect(), false);

    cli.select([]);
    await cli.runtime.session.reload();
    assert.deepEqual(cli.selected(), [], "reload");
    cli.userMessage("OLD-SENTINEL");
    await cli.runtime.newSession();
    assert.deepEqual(cli.selected(), [], "newSession");
    assert.equal(JSON.stringify(cli.runtime.session.sessionManager.getBranch()).includes("OLD-SENTINEL"), false);
    // Without tool_search, deferred QDash tools are offered directly instead of not at all.
    assert.equal(cli.deferredDirect(), true);

    const forkFrom = cli.userMessage("fork fixture");
    await cli.runtime.fork(forkFrom);
    assert.deepEqual(cli.selected(), [], "fork");
    cli.runtime.session.sessionManager.resetLeaf();
    assert.deepEqual(cli.selected(), [], "resetLeaf");
    await cli.runtime.session.reload();
    assert.deepEqual(cli.selected(), [], "reload after reset");

    // Turning one back on is kept the same way.
    cli.select(["codemode"]);
    await cli.runtime.newSession();
    assert.deepEqual(cli.selected(), ["codemode"], "newSession with codemode only");
    const again = cli.userMessage("fork again");
    await cli.runtime.fork(again);
    assert.deepEqual(cli.selected(), ["codemode"], "fork with codemode only");
    cli.select(["codemode", "tool_search"]);
    await cli.runtime.newSession();
    assert.deepEqual(cli.selected(), ["codemode", "tool_search"], "turned back on");
    assert.equal(cli.deferredDirect(), false);
  } finally {
    cli.close();
  }

  // Another user's runtime in the same process starts with the defaults.
  const fresh = await openRuntime();
  try {
    assert.deepEqual(fresh.selected(), ["codemode", "tool_search"]);
  } finally {
    fresh.close();
  }
});

test("in the pi CLI, a persisted session hands the selection to the new session file, and defaultTools opts out for every session", async () => {
  const cli = await openRuntime({ persisted: true });
  try {
    assert.ok(cli.runtime.session.sessionFile);
    cli.select(["tool_search"]);
    await cli.runtime.newSession();
    assert.deepEqual(cli.selected(), ["tool_search"]);
  } finally {
    cli.close();
  }

  const optedOut = await openRuntime({ settings: { defaultTools: ["-codemode"] } });
  try {
    assert.deepEqual(optedOut.selected(), ["tool_search"]);
    await optedOut.runtime.newSession();
    assert.deepEqual(optedOut.selected(), ["tool_search"]);
  } finally {
    optedOut.close();
  }
});


test("an unrelated in-memory runtime keeps disabled defaults despite an abandoned handoff", async () => {
  const { leaveHandoff, clearHandoffs } = await import("../../packages/pi-qdash/extensions/lib/tool-selection.ts");
  clearHandoffs();
  leaveHandoff({ selection: { codemode: true, tool_search: true }, reason: "new", targetSessionFile: undefined, sessionManager: {} });
  const cli = await openRuntime({ settings: { defaultTools: ["-codemode", "-tool_search"] } });
  try {
    await cli.runtime.newSession();
    assert.deepEqual(cli.selected(), []);
    await cli.runtime.newSession();
    assert.deepEqual(cli.selected(), []);
  } finally {
    cli.close();
    clearHandoffs();
  }
});
