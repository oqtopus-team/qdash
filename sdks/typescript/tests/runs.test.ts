import { describe, expect, it } from "vitest";

import type { Context } from "../src/_http.js";
import { Executions } from "../src/runs.js";
import { QDashNotFoundError, QDashTimeoutError } from "../src/index.js";

type Answer = "running" | "completed" | "missing";

/**
 * Execution reads on a fake clock: `sleep` advances it without waiting, and each read takes
 * `readMilliseconds` and answers with the next status (the last one repeats).
 */
function polling(answers: Answer[], readMilliseconds = 0) {
  let clock = 0;
  const reads: number[] = [];
  const sleeps: number[] = [];
  const sleep = async (milliseconds: number) => {
    sleeps.push(milliseconds);
    clock += milliseconds;
  };
  const api = {
    execution: {
      getExecution: async () => {
        reads.push(clock);
        clock += readMilliseconds;
        const answer = answers.length > 1 ? answers.shift()! : answers[0]!;
        if (answer === "missing") throw new QDashNotFoundError("404 /executions/exec-1", { statusCode: 404 });
        return { name: "run", status: answer, task: [], note: {} };
      },
    },
  };
  const context = {
    api,
    config: {},
    reads: { attempts: 1, sleep },
    sleep,
    now: () => clock,
  } as unknown as Context;
  return { executions: new Executions(context), reads, sleeps };
}

describe("waiting for a run", () => {
  it("keeps the poll interval and shortens only the last wait to end at the deadline", async () => {
    const { executions, reads, sleeps } = polling(["running"]);
    await expect(executions.wait("exec-1", { timeoutSeconds: 12, pollIntervalSeconds: 5 })).rejects.toBeInstanceOf(
      QDashTimeoutError,
    );
    expect(sleeps).toEqual([5_000, 5_000, 2_000]);
    expect(reads).toEqual([0, 5_000, 10_000]);
  });

  it("does not sleep past the timeout when the interval is longer", async () => {
    const { executions, reads, sleeps } = polling(["running"]);
    await expect(executions.wait("exec-1", { timeoutSeconds: 10, pollIntervalSeconds: 600 })).rejects.toBeInstanceOf(
      QDashTimeoutError,
    );
    expect(sleeps).toEqual([10_000]);
    expect(reads).toEqual([0]);
  });

  it("does not start another read at the deadline even if it would return completed", async () => {
    const { executions, reads, sleeps } = polling(["running", "completed"]);
    await expect(executions.wait("exec-1", { timeoutSeconds: 3, pollIntervalSeconds: 60 })).rejects.toBeInstanceOf(
      QDashTimeoutError,
    );
    expect(reads).toEqual([0]);
    expect(sleeps).toEqual([3_000]);
  });

  it("returns a run that ends on a read before the deadline", async () => {
    const { executions } = polling(["running", "completed"]);
    await expect(executions.wait("exec-1", { timeoutSeconds: 3, pollIntervalSeconds: 1 })).resolves.toMatchObject({
      status: "completed",
    });
  });

  it("polls an execution that is not listed yet (404) within the same budget", async () => {
    const found = polling(["missing", "missing", "completed"]);
    await expect(found.executions.wait("exec-1", { timeoutSeconds: 30, pollIntervalSeconds: 5 })).resolves.toMatchObject({
      status: "completed",
    });
    expect(found.sleeps).toEqual([5_000, 5_000]);

    const never = polling(["missing"]);
    await expect(never.executions.wait("exec-1", { timeoutSeconds: 7, pollIntervalSeconds: 5 })).rejects.toBeInstanceOf(
      QDashTimeoutError,
    );
    expect(never.sleeps).toEqual([5_000, 2_000]);
  });

  it("gives up without another wait when a read itself runs past the deadline", async () => {
    // A read in flight is not cancelled at the deadline; nothing waits after it.
    const { executions, reads, sleeps } = polling(["running"], 15_000);
    await expect(executions.wait("exec-1", { timeoutSeconds: 10, pollIntervalSeconds: 5 })).rejects.toBeInstanceOf(
      QDashTimeoutError,
    );
    expect(reads).toEqual([0]);
    expect(sleeps).toEqual([]);
  });

  it("reads once and gives up with a zero timeout", async () => {
    const { executions, reads, sleeps } = polling(["running"]);
    await expect(executions.wait("exec-1", { timeoutSeconds: 0, pollIntervalSeconds: 5 })).rejects.toBeInstanceOf(
      QDashTimeoutError,
    );
    expect(reads).toEqual([0]);
    expect(sleeps).toEqual([]);
  });
});
