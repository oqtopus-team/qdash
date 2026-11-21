import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { usePacedText } from "../ToolStepDetails";

import { ChatTraceSummary, LiveTrace } from "../ChatTrace";

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
              runId: "evr_1",
            },
          },
        ]}
      />,
    );
    expect(screen.getByText("vllm/nvidia/Ising-Calibration-1.5-31B-NVFP4")).toBeTruthy();
    expect(screen.getByText("What the model saw")).toBeTruthy();
    expect(screen.getByText("recorded as an evaluation").getAttribute("href")).toBe(
      "/evaluations/evr_1",
    );
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

  it("shows a classify call as a tool step while the classifier works", () => {
    render(
      <LiveTrace
        steps={[
          {
            kind: "tool",
            id: "k1",
            tool: "classify",
            label: "Classify",
            status: "running",
            startedAt: Date.now(),
            args: {
              question: "What most likely caused this fit failure?",
              categories: [
                { name: "readout_problem", description: "Weak or noisy readout." },
                { name: "drive_problem", description: "Drive amplitude or frequency off." },
              ],
              context: "Q04 rabi: fit did not converge; readout SNR 0.8",
            },
          },
        ]}
      />,
    );
    expect(screen.getByText("Classifying")).toBeTruthy();
    // The question is the row's preview, and the details list the candidates.
    expect(screen.getAllByText("What most likely caused this fit failure?").length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText("readout_problem")).toBeTruthy();
    expect(screen.queryByTestId("classification-panel")).toBeNull();
  });

  it("shows what the classifier chose, which model it was, and every category's share", () => {
    render(
      <ChatTraceSummary
        trace={{
          durationMs: 2000,
          steps: [
            {
              kind: "tool",
              id: "k1",
              tool: "classify",
              label: "Classify",
              status: "done",
              startedAt: 0,
              endedAt: 800,
              args: {
                question: "What most likely caused this fit failure?",
                categories: [
                  { name: "readout_problem", description: "Weak or noisy readout." },
                  { name: "drive_problem", description: "Drive amplitude or frequency off." },
                ],
                context: "Q04 rabi: fit did not converge; readout SNR 0.8",
              },
              classification: {
                classifier: "system-one-classifier/Open-Jev",
                outcome: "classified",
                category: "readout_problem",
                probability: 0.8,
                margin: 0.6,
                probabilities: [
                  { category: "readout_problem", probability: 0.8 },
                  { category: "drive_problem", probability: 0.2 },
                ],
              },
            },
          ],
        }}
      />,
    );
    // A single call is its own row, with no group to open first.
    expect(screen.queryByTestId("tool-group-summary")).toBeNull();
    expect(screen.getByText("Classified as readout_problem")).toBeTruthy();
    expect(screen.getByText("Classified")).toBeTruthy();
    expect(screen.getByText("system-one-classifier/Open-Jev")).toBeTruthy();
    expect(screen.getByText(/80%, lead 60%/)).toBeTruthy();
    expect(screen.getByText("All categories")).toBeTruthy();
    expect(screen.getByLabelText("drive_problem probability").getAttribute("value")).toBe("20");
  });

  it("marks an unclear answer and a failed classification", () => {
    render(
      <LiveTrace
        steps={[
          {
            kind: "tool",
            id: "k1",
            tool: "classify",
            label: "Classify",
            status: "done",
            startedAt: 0,
            endedAt: 500,
            classification: {
              classifier: "c/jev",
              outcome: "ambiguous",
              category: "drive_problem",
              probability: 0.45,
              margin: 0.05,
            },
          },
          {
            kind: "tool",
            id: "k2",
            tool: "classify",
            label: "Classify",
            status: "error",
            startedAt: 0,
            endedAt: 5000,
            classification: {
              classifier: "c/jev",
              outcome: "failed",
              reason: "timed out after 5 s",
            },
          },
        ]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Used 2 tools/ }));
    expect(screen.getByText("Classification unclear")).toBeTruthy();
    expect(screen.getByText("Unclear")).toBeTruthy();
    expect(screen.getByText("drive_problem")).toBeTruthy();
    expect(screen.getByText("Classification failed")).toBeTruthy();
    expect(screen.getByText("No answer")).toBeTruthy();
    expect(screen.getByText("The classifier gave no answer: timed out after 5 s.")).toBeTruthy();
    expect(screen.getAllByTestId("classification-panel")).toHaveLength(2);
  });

  it("shows code being written live, with the file it goes to", () => {
    render(
      <LiveTrace
        steps={[
          {
            kind: "tool",
            id: "c1",
            tool: "write",
            label: "Write",
            status: "drafting",
            startedAt: 0,
            draft: { path: "fit.py", content: "import numpy as np\nT1 = 2" },
            draftIndex: 0,
          },
        ]}
      />,
    );
    // Folded while it is written; the live code is one click away.
    const row = screen.getByRole("button", { name: /Writing fit.py/ });
    expect(row.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(row);
    expect(row.getAttribute("aria-expanded")).toBe("true");
    const live = screen.getByTestId("live-code");
    expect(live.textContent).toContain("fit.py · python");
    expect(live.textContent).toContain("import numpy as np");
    expect(live.textContent?.endsWith("T1 = 2▍")).toBe(true);
  });

  it("shows a finished command with its output and exit status", () => {
    render(
      <LiveTrace
        steps={[
          {
            kind: "tool",
            id: "c1",
            tool: "bash",
            label: "Bash",
            status: "error",
            startedAt: 0,
            endedAt: 2000,
            args: { command: "python fit.py" },
            output: "FileNotFoundError: data.csv",
            exitCode: 1,
          },
        ]}
      />,
    );
    // The row names the program only; the failure's last line stays visible while folded.
    const row = screen.getByRole("button", { name: /Ran python.*Failed/ });
    expect(row.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("$ python fit.py")).toBeNull();
    expect(screen.getByTestId("tool-failure-line").textContent).toBe("FileNotFoundError: data.csv");
    // Opened, the raw command, its output and the exit status are in the details.
    fireEvent.click(row);
    expect(screen.getByTestId("tool-code").textContent).toContain("python fit.py");
    expect(screen.queryByTestId("tool-failure-line")).toBeNull();
    expect(screen.getByText("FileNotFoundError: data.csv")).toBeTruthy();
    expect(screen.getByText("exit 1")).toBeTruthy();
  });

  it("shows a code mode script with its output and the tool calls it made", () => {
    render(
      <ChatTraceSummary
        trace={{
          durationMs: 3000,
          steps: [
            {
              kind: "tool",
              id: "s1",
              tool: "codemode",
              label: "Codemode",
              status: "done",
              startedAt: 0,
              endedAt: 2000,
              args: { code: "const chips = await tools.qdash_list_chips({});" },
              output: "B: 80 us\n\nTool calls: 1\nok        qdash_list_chips (12 ms)",
            },
          ],
        }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Ran a script/ }));
    expect(screen.getByText(/ok\s+qdash_list_chips \(12 ms\)/)).toBeTruthy();
    expect(screen.getByText("javascript")).toBeTruthy();
  });

  it("folds a live code mode step, showing its failure until it is opened", () => {
    render(
      <LiveTrace
        steps={[
          {
            kind: "tool",
            id: "s2",
            tool: "codemode",
            label: "Code mode script",
            status: "error",
            startedAt: 0,
            endedAt: 1000,
            args: { code: "await tools.qdash_list_cryostats({});" },
            output:
              "Script failed\n\nTool calls: 1, 1 failed\nerror     qdash_list_cryostats (3 ms): QDash answered 503",
          },
        ]}
      />,
    );
    const row = screen.getByRole("button", { name: /Ran a script.*Failed/ });
    expect(row.getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByTestId("tool-failure-line").textContent).toMatch(
      /qdash_list_cryostats \(3 ms\): QDash answered 503/,
    );
    fireEvent.click(row);
    // Open, not only mounted: folded output stays mounted under aria-hidden="true".
    const output = screen.getByText(/qdash_list_cryostats \(3 ms\): QDash answered 503/);
    expect(output.closest("[aria-hidden]")?.getAttribute("aria-hidden")).toBe("false");
    expect(
      screen.getByText("javascript").closest("[aria-hidden]")?.getAttribute("aria-hidden"),
    ).toBe("false");
  });

  it("folds a finished workspace step in the summary until it is opened", () => {
    render(
      <ChatTraceSummary
        trace={{
          durationMs: 3000,
          steps: [
            {
              kind: "tool",
              id: "c1",
              tool: "bash",
              label: "Bash",
              status: "done",
              startedAt: 0,
              endedAt: 2000,
              args: { command: "python fit.py" },
              output: "T1 = 24.3 us",
            },
          ],
        }}
      />,
    );
    expect(
      screen.getByText("T1 = 24.3 us").closest("[aria-hidden]")?.getAttribute("aria-hidden"),
    ).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: /Ran/ }));
    expect(
      screen.getByText("T1 = 24.3 us").closest("[aria-hidden]")?.getAttribute("aria-hidden"),
    ).toBe("false");
  });

  it("paces streamed code so a burst is typed out over a moment, never trailing far", () => {
    vi.useFakeTimers();
    try {
      const { result, rerender } = renderHook(({ text }) => usePacedText(text), {
        initialProps: { text: "import" },
      });
      expect(result.current).toBe("import");
      const full = `import numpy as np\n${"x = 1\n".repeat(40)}`;
      rerender({ text: full });
      expect(result.current).toBe("import");
      act(() => vi.advanceTimersByTime(16));
      expect(result.current.length).toBeGreaterThan("import".length);
      expect(result.current.length).toBeLessThan(full.length);
      act(() => vi.advanceTimersByTime(400));
      expect(result.current).toBe(full);
      // A different text (a new draft) shows at once.
      rerender({ text: "print(1)" });
      expect(result.current).toBe("print(1)");
    } finally {
      vi.useRealTimers();
    }
  });
});
