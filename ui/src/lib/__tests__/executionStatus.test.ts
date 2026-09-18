import { describe, it, expect } from "vitest";

import {
  isExecutionCancellable,
  isExecutionInProgress,
  isExecutionTerminal,
} from "../executionStatus";

describe("isExecutionInProgress", () => {
  it.each(["scheduled", "pending", "running", "cancelling"])("is true for %s", (status) => {
    expect(isExecutionInProgress(status)).toBe(true);
  });

  it.each(["completed", "failed", "cancelled"])("is false for %s", (status) => {
    expect(isExecutionInProgress(status)).toBe(false);
  });

  it("is false for a missing status", () => {
    expect(isExecutionInProgress(undefined)).toBe(false);
    expect(isExecutionInProgress(null)).toBe(false);
  });
});

describe("isExecutionCancellable", () => {
  it.each(["scheduled", "pending", "running"])("is true for %s", (status) => {
    expect(isExecutionCancellable(status)).toBe(true);
  });

  it("is false while a cancellation is already being applied", () => {
    expect(isExecutionCancellable("cancelling")).toBe(false);
  });

  it.each(["completed", "failed", "cancelled"])("is false for %s", (status) => {
    expect(isExecutionCancellable(status)).toBe(false);
  });
});

describe("isExecutionTerminal", () => {
  it.each(["completed", "failed", "cancelled"])("is true for %s", (status) => {
    expect(isExecutionTerminal(status)).toBe(true);
  });

  it("is false for cancelling, which is still waiting on Prefect", () => {
    expect(isExecutionTerminal("cancelling")).toBe(false);
  });

  it("is false for an unknown status", () => {
    expect(isExecutionTerminal("something-else")).toBe(false);
  });
});
