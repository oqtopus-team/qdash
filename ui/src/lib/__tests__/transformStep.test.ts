import { cleanup, render, screen } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { TransformStepOutcome } from "@/components/features/execution/TransformStepOutcome";
import { transformRecordOf, transformSummary } from "@/lib/transformStep";

afterEach(cleanup);

const malformed = [
  { kind: "unknown" },
  { kind: "cr_schedule", groups: "bad" },
  { kind: "cr_schedule", groups: ["0-1"] },
  { kind: "cr_schedule", groups: [[{ pair: "0-1" }]] },
  { kind: "filter", input_qids: "0" },
  { kind: "filter", output_qids: [null] },
  { kind: "transform", input_couplings: null },
  { kind: "transform", output_couplings: [1] },
  { kind: "filter", excluded: {} },
  { kind: "filter", excluded: [null] },
  { kind: "filter", excluded: [{ target: "0", reason: {} }] },
  { kind: "filter", criteria: {} },
  { kind: "filter", source_step: [] },
  { kind: "filter", source_call_id: 1 },
  { kind: "filter", metric: {} },
  { kind: "filter", threshold: "30" },
  { kind: "filter", threshold: Number.NaN },
  { kind: "filter", source_found: "false" },
  { kind: "cr_schedule", direction: {} },
  { kind: "cr_schedule", message: {} },
  { kind: "cr_schedule", max_parallel_ops: 1.5 },
];

describe("untrusted transform history", () => {
  it.each(malformed)(
    "rejects malformed record %j and renders the missing-outcome fallback",
    (record) => {
      const note = { step_kind: "transform", transform_result: record };
      expect(transformRecordOf(note)).toBeNull();
      render(createElement(TransformStepOutcome, { note, status: "completed" }));
      expect(screen.getByText(/No outcome was recorded/)).toBeTruthy();
      expect(screen.queryByRole("list", { name: "CR groups" })).toBeNull();
    },
  );

  it.each([null, [], "bad", { transform_result: [] }])("ignores non-object history %j", (note) => {
    expect(transformRecordOf(note)).toBeNull();
  });

  it("accepts nullable metadata, omitted defaults and future extra fields", () => {
    const record = transformRecordOf({
      transform_result: {
        kind: "cr_schedule",
        groups: [["0-1"], ["2-3", "4-5"]],
        criteria: null,
        source_found: null,
        max_parallel_ops: 2,
        direction: "forward",
        future_field: { retained: true },
      },
    });
    expect(record).not.toBeNull();
    expect(transformSummary(record!)).toBe("3 pairs in 2 groups");
    expect(
      transformRecordOf({ transform_result: { kind: "transform", groups: null } }),
    ).not.toBeNull();
  });
});
