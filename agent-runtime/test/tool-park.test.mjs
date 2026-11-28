/**
 * pi-durable 1.7.0 lets a tool's `execute()` park (`{ kind: "sleep" }` or `{ kind: "wait" }`)
 * instead of returning a result, and run again once woken. QDash's waiting
 * tools park (see durable-waits.test.mjs); these tests pin that QDash's
 * layer around durable tools (model-only exposure and the tool policy's
 * internal-call check) passes a park through, keeps the tool's `cancel`, and keeps enforcing the policy
 * when the call wakes or parks on its own nested calls.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createModels } from "@earendil-works/pi-ai/models";
import {
  createRegistry,
  defineExtension,
  defineSignal,
  defineTool,
  Harness,
  MemoryStorage,
  ToolResultEntry,
} from "@earendil-works/pi-durable";
import { Type } from "typebox";

import { modelOnly, toolPolicyExtension } from "../src/codemode.ts";

const context = BACKGROUND_CONTEXT;

const Go = defineSignal({ name: "qdash-test.go", version: 1, schema: Type.Object({ note: Type.String() }) });

/** An internal tool only `caller` may call, like present_results' classifier. */
function internalTool(runs) {
  return defineTool({
    name: "internal_check",
    description: "internal",
    parameters: Type.Object({ n: Type.Number() }),
    replay: "safe",
    callers: ["tools"],
    execute: async ({ n }) => {
      runs.push(n);
      return { output: [{ type: "text", text: `checked ${n}` }] };
    },
  });
}

async function open(tools, { internalCalls }) {
  const faux = fauxProvider({ tokensPerSecond: 0 });
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  const registry = createRegistry();
  registry.install(defineExtension({ name: "tools", tools }));
  registry.install(toolPolicyExtension({ nestedTools: [], deferredTools: [], internalCalls }));
  const harness = await Harness.open(new MemoryStorage(), { models, registry, settings: { retry: { enabled: false } } }, context);
  const conversation = await harness.root(context, { agent: { model: { provider: model.provider, modelId: model.id } } });
  harness.resume();
  return { faux, harness, conversation };
}

/** The tool task of model call `callId`, once the Harness reports it sleeping. */
async function parkedCall(harness, callId) {
  for (let i = 0; i < 300; i++) {
    const { tasks } = await harness.inspect(context);
    const task = tasks.find((candidate) => candidate.record.kind === "pi.tool" && candidate.record.input?.callId === callId);
    if (task?.state.kind === "sleeping") return task.record.id;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  throw new Error(`call ${callId} never parked`);
}

async function toolResults(conversation) {
  const view = await conversation.context(context);
  return view.entries.filter((entry) => ToolResultEntry.is(entry)).map((entry) => entry.model[0]);
}

test("a caller that parks keeps its park, wakes on a signal, and may call its internal tool after the wake", async () => {
  const runs = [];
  const wakes = [];
  const caller = modelOnly(
    defineTool({
      name: "parking_caller",
      description: "parks until signalled, then calls its internal tool",
      parameters: Type.Object({}),
      replay: "safe",
      execute: async (_args, api, ctx) => {
        if (api.wake === undefined) {
          // Before the park, the internal call is the caller's own.
          await api.executeTool("internal_check", { n: 1 }, ctx);
          return { kind: "sleep", checkpoint: { step: 1 }, signals: [Go.key("go")] };
        }
        wakes.push({ reason: api.wake.reason, checkpoint: api.checkpoint });
        const signal = await api.readSignal(Go, "go", ctx);
        const nested = await api.executeTool("internal_check", { n: 2 }, ctx, { key: "after-wake" });
        return {
          output: [{ type: "text", text: `woke with ${signal.value.note}; ${nested.structuredOutput}` }],
        };
      },
    }),
  );
  const chat = await open([caller, internalTool(runs)], { internalCalls: { internal_check: ["parking_caller"] } });
  try {
    chat.faux.setResponses([
      fauxAssistantMessage([fauxToolCall("parking_caller", {}, { id: "c1" })], { stopReason: "toolUse" }),
      fauxAssistantMessage(fauxText("done")),
    ]);
    const submission = await chat.conversation.submit({ type: "input", content: "go" }, context);
    // The wrapped caller parked: its task sleeps instead of ending invalid_park.
    const taskId = await parkedCall(chat.harness, "c1");
    assert.deepEqual(runs, [1]);
    assert.equal(await chat.harness.signal(taskId, Go, "go", { note: "approved" }, context), "delivered");
    const settled = await submission.wait(context);
    assert.equal(settled.status, "done");

    const [result] = await toolResults(chat.conversation);
    assert.equal(result.isError, false, JSON.stringify(result));
    assert.equal(result.content[0].text, "woke with approved; checked 2");
    assert.deepEqual(wakes, [{ reason: "signal", checkpoint: { step: 1 } }]);
    // The policy still knows the woken call as the internal tool's caller.
    assert.deepEqual(runs, [1, 2]);
  } finally {
    await chat.harness.close(context);
  }
});

test("a tool that is not an internal tool's caller stays blocked from it after a wake", async () => {
  const runs = [];
  const intruder = modelOnly(
    defineTool({
      name: "intruder",
      description: "not a caller of internal_check",
      parameters: Type.Object({}),
      replay: "safe",
      execute: async (_args, api, ctx) => {
        if (api.wake === undefined) return { kind: "sleep", signals: [Go.key("go")] };
        const nested = await api.executeTool("internal_check", { n: 9 }, ctx, { key: "after-wake" });
        return { output: [{ type: "text", text: nested.isError ? "blocked" : "ran" }] };
      },
    }),
  );
  const chat = await open([intruder, internalTool(runs)], { internalCalls: { internal_check: ["parking_caller"] } });
  try {
    chat.faux.setResponses([
      fauxAssistantMessage([fauxToolCall("intruder", {}, { id: "i1" })], { stopReason: "toolUse" }),
      fauxAssistantMessage(fauxText("done")),
    ]);
    const submission = await chat.conversation.submit({ type: "input", content: "go" }, context);
    const taskId = await parkedCall(chat.harness, "i1");
    await chat.harness.signal(taskId, Go, "go", { note: "x" }, context);
    assert.equal((await submission.wait(context)).status, "done");
    const [result] = await toolResults(chat.conversation);
    assert.equal(result.content[0].text, "blocked");
    assert.deepEqual(runs, []);
  } finally {
    await chat.harness.close(context);
  }
});

test("aborting a parked caller runs the tool's own cancel", async () => {
  const cancelled = [];
  const caller = modelOnly(
    defineTool({
      name: "parking_caller",
      description: "parks until signalled",
      parameters: Type.Object({}),
      replay: "safe",
      execute: async () => ({ kind: "sleep", checkpoint: { job: "j-1" }, signals: [Go.key("go")] }),
      cancel: async (_args, api) => {
        cancelled.push(api.checkpoint);
      },
    }),
  );
  const chat = await open([caller, internalTool([])], { internalCalls: { internal_check: ["parking_caller"] } });
  try {
    chat.faux.setResponses([
      fauxAssistantMessage([fauxToolCall("parking_caller", {}, { id: "c1" })], { stopReason: "toolUse" }),
      fauxAssistantMessage(fauxText("never")),
    ]);
    await chat.conversation.submit({ type: "input", content: "go" }, context);
    await parkedCall(chat.harness, "c1");
    await chat.conversation.abort(context);
    assert.deepEqual(cancelled.slice(0, 1), [{ job: "j-1" }]);
  } finally {
    await chat.harness.close(context);
  }
});

test("a caller may park on an internal call it started without waiting", async () => {
  const runs = [];
  const caller = modelOnly(
    defineTool({
      name: "parking_caller",
      description: "starts its internal tool, parks on it, and reads it after the wake",
      parameters: Type.Object({}),
      replay: "safe",
      execute: async (_args, api, ctx) => {
        // The nested call's policy check runs after this run returned its park,
        // so no code of the caller is executing in this process by then.
        if (api.wake === undefined) {
          const started = await api.executeTool("internal_check", { n: 3 }, ctx, { key: "check", wait: false });
          return { kind: "wait", checkpoint: { taskId: started.taskId }, on: [started.taskId], policy: "all" };
        }
        const again = await api.executeTool("internal_check", { n: 3 }, ctx, { key: "check", wait: false });
        const result = await again.result(ctx);
        return { output: [{ type: "text", text: `${api.wake.reason}: ${result.isError ? "blocked" : result.structuredOutput}` }] };
      },
    }),
  );
  const chat = await open([caller, internalTool(runs)], { internalCalls: { internal_check: ["parking_caller"] } });
  try {
    chat.faux.setResponses([
      fauxAssistantMessage([fauxToolCall("parking_caller", {}, { id: "c1" })], { stopReason: "toolUse" }),
      fauxAssistantMessage(fauxText("done")),
    ]);
    assert.equal((await (await chat.conversation.submit({ type: "input", content: "go" }, context)).wait(context)).status, "done");
    const [result] = await toolResults(chat.conversation);
    assert.equal(result.content[0].text, "tasks: checked 3");
    assert.deepEqual(runs, [3]);
  } finally {
    await chat.harness.close(context);
  }
});
