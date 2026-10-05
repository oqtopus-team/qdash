import assert from "node:assert/strict";
import { test } from "node:test";

import { Type } from "typebox";

import { buildQDashExtension } from "../src/durable-tools.ts";

function registered(name) {
  let calls = 0;
  return {
    definition: {
      name,
      label: name,
      description: name,
      parameters: Type.Object({}),
      execute: async () => {
        calls += 1;
        return { content: [], details: {} };
      },
    },
    calls: () => calls,
  };
}

test("only explicitly reviewed pi-qdash tools enter the durable registry", () => {
  const extension = buildQDashExtension(
    [
      {
        tools: new Map([
          ["qdash_get_default_chip", registered("qdash_get_default_chip")],
          ["qdash_create_forum_post", registered("qdash_create_forum_post")],
          ["qdash_future_unreviewed_tool", registered("qdash_future_unreviewed_tool")],
        ]),
      },
    ],
    {},
    "/tmp/work",
  );

  assert.deepEqual(extension.tools.map((tool) => tool.name), ["qdash_get_default_chip"]);
});

test("experimental write tools require opt-in and are not replayed after interruption", async () => {
  const write = registered("qdash_create_forum_post");
  const extension = buildQDashExtension(
    [
      {
        tools: new Map([
          ["qdash_get_default_chip", registered("qdash_get_default_chip")],
          ["qdash_create_forum_post", write],
          ["qdash_future_unreviewed_tool", registered("qdash_future_unreviewed_tool")],
        ]),
      },
    ],
    {},
    "/tmp/work",
    true,
  );

  assert.deepEqual(
    extension.tools.map((tool) => tool.name),
    ["qdash_get_default_chip", "qdash_create_forum_post"],
  );
  const writeTool = extension.tools.find((tool) => tool.name === "qdash_create_forum_post");
  assert.equal(writeTool.replay, "unsafe");

  const context = { abortSignal: new AbortController().signal };
  await assert.rejects(
    () => writeTool.execute({}, {}, context),
    /requires confirmWrite: true/,
  );
  assert.equal(write.calls(), 0);

  await writeTool.execute({ confirmWrite: true }, {}, context);
  assert.equal(write.calls(), 1);
});
