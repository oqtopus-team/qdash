import assert from "node:assert/strict";
import { homedir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { qdashContextPath } from "../.test-dist/lib/context-path.js";

test("the persisted QDash context follows PI_CODING_AGENT_DIR", () => {
  const previous = process.env.PI_CODING_AGENT_DIR;
  try {
    process.env.PI_CODING_AGENT_DIR = "/tmp/isolated-pi-agent";
    assert.equal(qdashContextPath(), join("/tmp/isolated-pi-agent", "qdash-context.json"));
    delete process.env.PI_CODING_AGENT_DIR;
    assert.equal(qdashContextPath(), join(homedir(), ".pi", "agent", "qdash-context.json"));
  } finally {
    if (previous === undefined) delete process.env.PI_CODING_AGENT_DIR;
    else process.env.PI_CODING_AGENT_DIR = previous;
  }
});
