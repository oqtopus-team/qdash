import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LiveTrace } from "../ChatTrace";

afterEach(cleanup);

describe("ChatTrace", () => {
  it("shows which model judged a plot and what it was sent", () => {
    render(
      <LiveTrace
        steps={[
          {
            kind: "tool",
            id: "c1",
            tool: "qcal_evaluate",
            label: "Evaluate Calibration Plot",
            status: "done",
            startedAt: 0,
            endedAt: 1000,
            evaluation: {
              prompt:
                "Reference for this experiment:\n## Experiment: CheckRabi\n\nExperiment context:\nRabi on Q05",
              model: "vllm/nvidia/Ising-Calibration-1.5-31B-NVFP4",
            },
          },
        ]}
      />,
    );
    expect(screen.getByText("vllm/nvidia/Ising-Calibration-1.5-31B-NVFP4")).toBeTruthy();
    expect(screen.getByText("What the model saw")).toBeTruthy();
    expect(screen.getByText(/## Experiment: CheckRabi/)).toBeTruthy();
    expect(screen.queryByText(/fallback/)).toBeNull();
  });

  it("flags a fallback judge and says nothing for ordinary tools", () => {
    render(
      <LiveTrace
        steps={[
          {
            kind: "tool",
            id: "c1",
            tool: "qcal_evaluate",
            label: "Evaluate Calibration Plot",
            status: "done",
            startedAt: 0,
            endedAt: 1000,
            evaluation: { prompt: "p", fallback: true },
          },
          {
            kind: "tool",
            id: "c2",
            tool: "qdash_get_figure",
            label: "Get figure",
            status: "done",
            startedAt: 0,
            endedAt: 1000,
          },
        ]}
      />,
    );
    expect(screen.getByText(/fallback, no calibration VLM configured/)).toBeTruthy();
    expect(screen.getByText("the conversation model")).toBeTruthy();
    expect(screen.getAllByText("What the model saw")).toHaveLength(1);
  });
});
