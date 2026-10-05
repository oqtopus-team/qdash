import assert from "node:assert/strict";
import { test } from "node:test";

import { Type } from "typebox";

import { buildQDashExtension } from "../src/durable-tools.ts";

function registered(name) {
  return {
    definition: {
      name,
      label: name,
      description: name,
      parameters: Type.Object({}),
      execute: async () => ({ content: [], details: {} }),
    },
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
