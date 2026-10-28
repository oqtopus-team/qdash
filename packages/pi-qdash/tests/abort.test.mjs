import assert from "node:assert/strict";
import test from "node:test";

import { WaitCancelled, withAbort } from "../.test-dist/lib/abort.js";

test("a wait returns as cancelled the moment the host aborts", async () => {
  const controller = new AbortController();
  const never = new Promise(() => {});
  const waiting = withAbort(never, controller.signal, "waiting for execution 1");
  controller.abort();
  await assert.rejects(waiting, (error) => error instanceof WaitCancelled && /keeps running in QDash/.test(error.message));
  await assert.rejects(withAbort(never, controller.signal, "x"), WaitCancelled);
});

test("without a signal, or when the wait finishes first, the value passes through", async () => {
  assert.equal(await withAbort(Promise.resolve(1), undefined, "x"), 1);
  const controller = new AbortController();
  assert.equal(await withAbort(Promise.resolve(2), controller.signal, "x"), 2);
  await assert.rejects(withAbort(Promise.reject(new Error("boom")), controller.signal, "x"), /boom/);
});
