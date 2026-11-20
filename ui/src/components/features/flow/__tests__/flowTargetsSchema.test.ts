import { describe, expect, it } from "vitest";

import { flowTargetsSchema, type FlowTargetsFormInput } from "../flowTargetsSchema";

/** Returns the messages the schema reports for the input. */
const messagesFor = (input: FlowTargetsFormInput) => {
  const result = flowTargetsSchema.safeParse(input);
  return result.success ? [] : result.error.issues.map((issue) => [issue.path, issue.message]);
};

const PAIR_FORMAT =
  "Use control-target pairs such as 63-85, separated by commas, spaces or new lines.";
const ID_FORMAT = "Use non-negative integer IDs separated by commas or spaces.";

describe("flowTargetsSchema", () => {
  it("normalizes MUX IDs to numbers and keeps exclusions as strings", () => {
    expect(
      flowTargetsSchema.parse({ mode: "mux", ids: " 01,\n2  10 ", excluded: "05, 7" }),
    ).toEqual({ mux_ids: [1, 2, 10], exclude_qids: ["05", "7"] });
    expect(flowTargetsSchema.parse({ mode: "mux", ids: "3", excluded: "  " })).toEqual({
      mux_ids: [3],
      exclude_qids: [],
    });
  });

  it("keeps qubit IDs as written and ignores exclusions", () => {
    expect(flowTargetsSchema.parse({ mode: "qubit", ids: "1, 01\n8", excluded: "x, x" })).toEqual({
      qids: ["1", "01", "8"],
    });
  });

  it("keeps the order and direction of coupling pairs", () => {
    expect(
      flowTargetsSchema.parse({
        mode: "pairs",
        ids: " 63-85, 85-63\n64-42  39-61\n",
        excluded: "",
      }),
    ).toEqual({
      coupling_pairs: [
        ["63", "85"],
        ["85", "63"],
        ["64", "42"],
        ["39", "61"],
      ],
    });
  });

  it.each<[FlowTargetsFormInput, string]>([
    [{ mode: "pairs", ids: "63-85-1", excluded: "" }, PAIR_FORMAT],
    [{ mode: "pairs", ids: "63, 85", excluded: "" }, PAIR_FORMAT],
    [{ mode: "pairs", ids: "63-63, 1-x", excluded: "" }, PAIR_FORMAT],
    [{ mode: "pairs", ids: " \n ", excluded: "" }, "Enter at least one coupling pair."],
    [{ mode: "pairs", ids: "63-63, 63-63", excluded: "" }, "Each pair needs two different qubits."],
    [{ mode: "pairs", ids: "63-85\n63-85", excluded: "" }, "Remove duplicate coupling pairs."],
    [{ mode: "mux", ids: "", excluded: "x" }, "Enter at least one target ID."],
    [{ mode: "qubit", ids: " \n ", excluded: "" }, "Enter at least one target ID."],
    [{ mode: "mux", ids: "-1", excluded: "" }, ID_FORMAT],
    [{ mode: "mux", ids: "1, 1", excluded: "y" }, ID_FORMAT],
    [{ mode: "mux", ids: "9007199254740993", excluded: "" }, ID_FORMAT],
    [{ mode: "qubit", ids: "1.5", excluded: "" }, ID_FORMAT],
    [{ mode: "mux", ids: "1, 01", excluded: "" }, "Remove duplicate target IDs."],
    [{ mode: "qubit", ids: "2 2", excluded: "" }, "Remove duplicate target IDs."],
    [{ mode: "mux", ids: "1", excluded: "5, 5" }, "Remove duplicate target IDs."],
  ])("reports one message on ids: %o", (input, message) => {
    expect(messagesFor(input)).toEqual([[["ids"], message]]);
  });

  it("accepts unsafe integers only as qubit IDs", () => {
    expect(
      flowTargetsSchema.parse({ mode: "qubit", ids: "9007199254740993", excluded: "" }),
    ).toEqual({ qids: ["9007199254740993"] });
  });

  it("compares exclusions as strings", () => {
    expect(flowTargetsSchema.parse({ mode: "mux", ids: "1", excluded: "5, 05" })).toEqual({
      mux_ids: [1],
      exclude_qids: ["5", "05"],
    });
  });
});
