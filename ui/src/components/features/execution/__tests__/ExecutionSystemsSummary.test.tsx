import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ExecutionSystemsSummary } from "@/components/features/execution/ExecutionSystemsSummary";

describe("ExecutionSystemsSummary", () => {
  afterEach(cleanup);

  it("renders nothing without System information", () => {
    const { container } = render(<ExecutionSystemsSummary note={{ flow_run_id: "x" }} />);
    expect(container.innerHTML).toBe("");
  });

  it("shows the Systems used and the couplings skipped across Systems", () => {
    render(
      <ExecutionSystemsSummary
        note={{
          system_ids: ["144Qv3", "144Qv3-quel3"],
          cross_system_couplings: ["3-24", ["7", "28"]],
        }}
      />,
    );
    expect(screen.getByText("144Qv3")).toBeTruthy();
    expect(screen.getByText("144Qv3-quel3")).toBeTruthy();
    expect(screen.getByText("Couplings skipped across Systems (2)")).toBeTruthy();
    expect(screen.getByText("3-24")).toBeTruthy();
    expect(screen.getByText("7-28")).toBeTruthy();
  });
});
