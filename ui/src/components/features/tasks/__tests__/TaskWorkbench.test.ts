import { describe, expect, it } from "vitest";

import { formatTaskParameter, parseTaskParameter } from "@/lib/utils/task-parameters";

describe("parseTaskParameter", () => {
  it("formats stored arrays as editable JSON", () => {
    expect(formatTaskParameter([3, 0, 2, 1])).toBe("[3,0,2,1]");
  });

  it("parses complete numeric values", () => {
    expect(parseTaskParameter("42", "int")).toBe(42);
    expect(parseTaskParameter(" 1.25 ", "float")).toBe(1.25);
  });

  it("rejects partial or non-finite numeric values", () => {
    expect(() => parseTaskParameter("1.5", "int")).toThrow("Expected an integer");
    expect(() => parseTaskParameter("10oops", "float")).toThrow("Expected a finite number");
    expect(() => parseTaskParameter("Infinity", "float")).toThrow("Expected a finite number");
  });

  it("accepts only explicit boolean values", () => {
    expect(parseTaskParameter("TRUE", "bool")).toBe(true);
    expect(parseTaskParameter(" false ", "bool")).toBe(false);
    expect(() => parseTaskParameter("yes", "bool")).toThrow("Expected true or false");
  });

  it("parses array-shaped run parameter JSON", () => {
    expect(parseTaskParameter("[0, 1, 2]", "np.linspace")).toEqual([0, 1, 2]);
    expect(parseTaskParameter("[-60, 5, 5]", "np.arange")).toEqual([-60, 5, 5]);
    expect(parseTaskParameter("[3, 0, 2, 1]", "list")).toEqual([3, 0, 2, 1]);
  });

  it("rejects invalid array-shaped parameters", () => {
    expect(() => parseTaskParameter('"not a list"', "list")).toThrow("Expected a JSON array");
    expect(() => parseTaskParameter("[5.75, 6.75]", "np.arange")).toThrow(
      "Expected exactly 3 array values",
    );
  });
});
