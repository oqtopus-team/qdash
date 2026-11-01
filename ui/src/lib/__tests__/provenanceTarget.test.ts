import { describe, expect, it } from "vitest";

import {
  entityIdFor,
  firstPublishedParameter,
  publishedParameters,
  resolveParameterQid,
} from "@/lib/provenanceTarget";

describe("resolveParameterQid", () => {
  it("keeps the task target for self and coupling roles", () => {
    expect(resolveParameterQid("3", undefined)).toBe("3");
    expect(resolveParameterQid("0-1", "coupling")).toBe("0-1");
  });

  it("picks one qubit of a coupling for control and target roles", () => {
    expect(resolveParameterQid("0-1", "control")).toBe("0");
    expect(resolveParameterQid("0-1", "target")).toBe("1");
    expect(resolveParameterQid("5", "control")).toBe("5");
  });
});

describe("publishedParameters", () => {
  it("lists one target per parameter, using the recorded name and role", () => {
    const targets = publishedParameters("0-1", {
      zx90_amplitude: { value: 0.1, qid_role: "coupling" },
      control_frequency: { value: 7.1, parameter_name: "qubit_frequency", qid_role: "control" },
      duplicate: { value: 1, parameter_name: "qubit_frequency", qid_role: "control" },
      raw: 3,
    });

    expect(targets).toEqual([
      { parameterName: "zx90_amplitude", qid: "0-1" },
      { parameterName: "qubit_frequency", qid: "0" },
      { parameterName: "raw", qid: "0-1" },
    ]);
  });

  it("is empty without outputs", () => {
    expect(publishedParameters("0", undefined)).toEqual([]);
  });
});

describe("firstPublishedParameter", () => {
  it("prefers the first output and falls back to the first input", () => {
    expect(firstPublishedParameter("2", { t1: { value: 1 } }, { x: { value: 2 } })).toEqual({
      parameterName: "t1",
      qid: "2",
    });
    expect(firstPublishedParameter("2", {}, { qubit_frequency: { value: 2 } })).toEqual({
      parameterName: "qubit_frequency",
      qid: "2",
    });
    expect(firstPublishedParameter("2", null, null)).toBeNull();
  });
});

describe("entityIdFor", () => {
  it("matches the server's entity id format", () => {
    expect(entityIdFor({ parameterName: "t1", qid: "4" }, "20260101-001", "task-9")).toBe(
      "t1:4:20260101-001:task-9",
    );
  });
});
