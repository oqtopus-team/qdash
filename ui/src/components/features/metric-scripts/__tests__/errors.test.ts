import { describe, expect, it } from "vitest";

import { describeMetricError, errorStatus } from "../errors";

function apiError(status: number, detail: unknown) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    response: { status, data: { detail } },
  });
}

describe("describeMetricError", () => {
  it("reads a worker failure's message, diagnostics and log", () => {
    const described = describeMetricError(
      apiError(422, {
        message: "Metric 't1' raised ZeroDivisionError",
        diagnostics: [{ message: "division by zero", line: 7 }, { line: 9 }],
        log: "debug output",
      }),
      "Failed",
    );

    expect(described).toEqual({
      status: 422,
      message: "Metric 't1' raised ZeroDivisionError",
      diagnostics: [{ message: "division by zero", line: 7 }],
      log: "debug output",
      queueFull: false,
    });
  });

  it("shows the message of an unavailable runner (503)", () => {
    const described = describeMetricError(
      apiError(503, {
        message: "The metric script runner is not available",
        diagnostics: [],
        log: "",
      }),
      "Failed to evaluate",
    );

    expect(described.status).toBe(503);
    expect(described.message).toBe("The metric script runner is not available");
    expect(described.queueFull).toBe(false);
    expect(errorStatus(apiError(503, {}))).toBe(503);
  });

  it("flags a full queue (429) with a string detail", () => {
    const described = describeMetricError(
      apiError(429, "Metric script evaluation queue is full"),
      "Failed",
    );

    expect(described.queueFull).toBe(true);
    expect(described.message).toBe("Metric script evaluation queue is full");
  });

  it("falls back when the detail has no message", () => {
    expect(describeMetricError(apiError(500, {}), "Failed").message).toBe("Failed");
    expect(describeMetricError(new Error("Network Error"), "Failed")).toMatchObject({
      status: null,
      message: "Network Error",
    });
  });
});
