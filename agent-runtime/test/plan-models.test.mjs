import assert from "node:assert/strict";
import { test } from "node:test";

import { createModels } from "@earendil-works/pi-ai";

import {
  CHATGPT_PROVIDER,
  createPlanCatalog,
  planModel,
  planModelIds,
  requestChatGPTToken,
  withPlanToken,
} from "../src/plan-models.ts";

const SUPPORTED = "gpt-6.1-sol";

/** A Responses SSE body that completes with one text answer. */
function completedStream(text) {
  const response = {
    id: "resp_1",
    object: "response",
    status: "completed",
    model: SUPPORTED,
    output: [
      {
        type: "message",
        id: "msg_1",
        role: "assistant",
        status: "completed",
        content: [{ type: "output_text", text, annotations: [] }],
      },
    ],
    usage: { input_tokens: 1, output_tokens: 1, total_tokens: 2 },
  };
  const events = [
    { type: "response.created", response: { ...response, status: "in_progress", output: [] } },
    {
      type: "response.output_item.added",
      output_index: 0,
      item: { ...response.output[0], status: "in_progress", content: [] },
    },
    {
      type: "response.content_part.added",
      output_index: 0,
      content_index: 0,
      item_id: "msg_1",
      part: { type: "output_text", text: "", annotations: [] },
    },
    { type: "response.output_text.delta", output_index: 0, content_index: 0, item_id: "msg_1", delta: text },
    { type: "response.output_item.done", output_index: 0, item: response.output[0] },
    { type: "response.completed", response },
  ];
  return events.map((event) => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`).join("");
}

/** A fetch that records each request and answers with a completed stream. */
function recordingFetch(calls, { status = 200, body } = {}) {
  return async (url, init) => {
    const headers = new Headers(init?.headers);
    calls.push({
      url: String(url),
      authorization: headers.get("authorization"),
      body: JSON.parse(String(init?.body ?? "{}")),
    });
    return new Response(body ?? completedStream("ok"), {
      status,
      headers: { "content-type": status === 200 ? "text/event-stream" : "application/json" },
    });
  };
}

const context = {
  systemPrompt: "You are QDash Copilot.",
  messages: [{ role: "user", content: "Hello", timestamp: Date.now() }],
  tools: [
    {
      name: "qdash_list_chips",
      description: "List chips",
      parameters: { type: "object", properties: {}, additionalProperties: false },
    },
  ],
};

/** A shared runtime stand-in whose own credential must never be used for plan models. */
function sharedRuntime() {
  const shared = createModels({
    authContext: {
      env: async (name) => (name === "OPENAI_API_KEY" ? "sk-operator" : undefined),
      fileExists: async () => false,
    },
  });
  return shared;
}

test("only catalog models whose tools go in additional_tools are offered on the plan route", () => {
  const catalog = createPlanCatalog();
  const ids = planModelIds(catalog);
  assert.ok(ids.includes(SUPPORTED));
  assert.ok(!ids.includes("gpt-4o"), "top-level function tools are not accepted on the plan route");
  const model = planModel(catalog, SUPPORTED);
  assert.equal(model?.provider, CHATGPT_PROVIDER);
  assert.equal(model?.samplingParams, undefined);
  assert.equal(planModel(catalog, "not-a-model"), undefined);
});

test("a plan turn sends the user's token and the documented Responses shape", async () => {
  const catalog = createPlanCatalog();
  const models = withPlanToken(sharedRuntime(), catalog, "user-a-access");
  const model = models.getModel(CHATGPT_PROVIDER, SUPPORTED);
  const calls = [];
  const answer = await models.completeSimple(model, context, {
    fetch: recordingFetch(calls),
    maxTokens: 4096,
    temperature: 0.2,
    sessionId: "session-1",
  });

  assert.equal(answer.stopReason, "stop", answer.errorMessage);
  assert.equal(calls.length, 1);
  const [call] = calls;
  assert.equal(call.url, "https://api.openai.com/v1/responses");
  assert.equal(call.authorization, "Bearer user-a-access");
  assert.equal(call.body.store, false);
  assert.equal(call.body.stream, true);
  assert.ok(Array.isArray(call.body.input));
  for (const field of [
    "max_output_tokens",
    "temperature",
    "top_p",
    "previous_response_id",
    "prompt_cache_retention",
    "metadata",
    "user",
    "truncation",
  ]) {
    assert.equal(call.body[field], undefined, `${field} must be omitted`);
  }
  assert.equal(call.body.tools, undefined, "tools are declared in additional_tools items");
  assert.ok(call.body.input.some((item) => item.type === "additional_tools"));
  assert.ok(
    !call.body.input.some((item) => item.type === "message" && item.role === "system"),
    "system messages are rejected; instructions go as developer messages",
  );
});

test("concurrent turns of different users each carry only their own token", async () => {
  const catalog = createPlanCatalog();
  const shared = sharedRuntime();
  const alice = withPlanToken(shared, catalog, "alice-access");
  const bob = withPlanToken(shared, catalog, "bob-access");
  const calls = [];
  const fetch = recordingFetch(calls);
  await Promise.all([
    alice.completeSimple(alice.getModel(CHATGPT_PROVIDER, SUPPORTED), context, { fetch }),
    bob.completeSimple(bob.getModel(CHATGPT_PROVIDER, SUPPORTED), context, { fetch }),
    alice.completeSimple(alice.getModel(CHATGPT_PROVIDER, SUPPORTED), context, { fetch }),
  ]);
  assert.deepEqual(
    calls.map((call) => call.authorization).sort(),
    ["Bearer alice-access", "Bearer alice-access", "Bearer bob-access"],
  );
});

test("the shared runtime never serves a plan model, so no operator key can pay for it", async () => {
  const shared = sharedRuntime();
  const catalog = createPlanCatalog();
  const model = planModel(catalog, SUPPORTED);
  const calls = [];
  const answer = await shared.completeSimple(model, context, { fetch: recordingFetch(calls) });
  assert.equal(answer.stopReason, "error");
  assert.equal(calls.length, 0);
});

test("the plan catalog has no ambient credential of its own", async () => {
  const previous = process.env.OPENAI_API_KEY;
  process.env.OPENAI_API_KEY = "sk-ambient";
  try {
    const catalog = createPlanCatalog();
    const model = catalog.getModel("openai", SUPPORTED);
    const calls = [];
    const answer = await catalog.completeSimple(model, context, { fetch: recordingFetch(calls) });
    assert.equal(answer.stopReason, "error");
    assert.equal(calls.length, 0);
  } finally {
    if (previous === undefined) delete process.env.OPENAI_API_KEY;
    else process.env.OPENAI_API_KEY = previous;
  }
});

test("usage-limit errors from the plan route surface their documented code", async () => {
  const catalog = createPlanCatalog();
  const models = withPlanToken(sharedRuntime(), catalog, "user-a-access");
  const calls = [];
  const body = JSON.stringify({
    error: {
      code: "subscription_sharing_usage_limit_exceeded",
      message: "Usage limit reached",
      type: "usage_limit",
      param: null,
    },
  });
  const answer = await models.completeSimple(models.getModel(CHATGPT_PROVIDER, SUPPORTED), context, {
    fetch: recordingFetch(calls, { status: 429, body }),
    maxRetries: 0,
  });
  assert.equal(answer.stopReason, "error");
  assert.match(answer.errorMessage ?? "", /subscription_sharing_usage_limit_exceeded/);
});

test("other providers pass through to the shared runtime unchanged", () => {
  const shared = sharedRuntime();
  const models = withPlanToken(shared, createPlanCatalog(), "user-a-access");
  assert.equal(models.getModel("not-registered", "x"), undefined);
  assert.deepEqual(
    models.getProviders().map((provider) => provider.id),
    shared.getProviders().map((provider) => provider.id),
  );
  assert.deepEqual(models.getModels(CHATGPT_PROVIDER), []);
});

test("plan tokens are required and API keys are refused", () => {
  assert.throws(() => withPlanToken(sharedRuntime(), createPlanCatalog(), ""));
  assert.throws(() => withPlanToken(sharedRuntime(), createPlanCatalog(), "sk-operator"));
  assert.equal(requestChatGPTToken({}), undefined);
  assert.equal(requestChatGPTToken({ "x-qdash-chatgpt-token": "abc" }), "abc");
  assert.throws(() => requestChatGPTToken({ "x-qdash-chatgpt-token": "sk-key" }));
  assert.throws(() => requestChatGPTToken({ "x-qdash-chatgpt-token": ["a", "b"] }));
  assert.throws(() => requestChatGPTToken({ "x-qdash-chatgpt-token": " " }));
});
