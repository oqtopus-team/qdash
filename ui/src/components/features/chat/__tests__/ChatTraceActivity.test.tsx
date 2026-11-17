import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { appendArgsDelta, endTool, startDraft, startTool } from "@/lib/copilotChatStream";

import type { TraceStep } from "@/types/copilotChat";

import { ChatTraceSummary, LiveTrace, TurnActivity, currentActivity } from "../ChatTrace";
import { commandName } from "../ToolStepDetails";

afterEach(cleanup);

type ToolStep = Extract<TraceStep, { kind: "tool" }>;

function tool(overrides: Partial<ToolStep>): ToolStep {
  return {
    kind: "tool",
    id: "t1",
    tool: "qdash_get_figure",
    label: "Get figure",
    status: "running",
    startedAt: 0,
    ...overrides,
  };
}

function expanded(name: RegExp): string | null {
  return screen.getByRole("button", { name }).getAttribute("aria-expanded");
}

describe("tool step transitions", () => {
  it("keeps every row folded by default while it is written, run and finished", () => {
    const { rerender } = render(
      <LiveTrace steps={[tool({ status: "drafting", draft: { qid: "Q01" }, args: undefined })]} />,
    );
    expect(expanded(/Writing a get figure call.*Preparing/)).toBe("false");

    rerender(<LiveTrace steps={[tool({ status: "running", args: { qid: "Q01" } })]} />);
    expect(expanded(/Get figure.*Running/)).toBe("false");

    rerender(<LiveTrace steps={[tool({ status: "done", args: { qid: "Q01" }, endedAt: 2000 })]} />);
    expect(expanded(/Get figure.*Done/)).toBe("false");
  });

  it("folds live workspace, code mode and save-flow calls too", () => {
    render(
      <LiveTrace
        steps={[
          tool({
            id: "w",
            tool: "write",
            label: "Write",
            status: "drafting",
            draft: { path: "fit.py" },
          }),
          tool({ id: "b", tool: "bash", label: "Bash", args: { command: "bun run test" } }),
          tool({ id: "c", tool: "codemode", label: "Codemode", args: { code: "1" } }),
          tool({
            id: "f",
            tool: "qdash_save_flow",
            label: "Save flow",
            status: "drafting",
            draft: { name: "rabi", code: "x" },
          }),
        ]}
      />,
    );
    for (const name of [/Writing fit.py/, /Running bun/, /Running a script/, /Writing flow rabi/]) {
      expect(expanded(name)).toBe("false");
    }
    expect(screen.queryByText("bun run test")).toBeNull();
  });

  it("keeps a row the user opened open from draft to running to done", () => {
    const draft = appendArgsDelta(startDraft([], { index: 0, tool: "bash", label: "Bash" }), {
      index: 0,
      path: ["command"],
      delta: "bun run test",
    });
    const { rerender } = render(<LiveTrace steps={draft} />);
    fireEvent.click(screen.getByRole("button", { name: /Writing a command/ }));
    expect(expanded(/Writing a command/)).toBe("true");

    // The draft's ID is replaced by the execution's when the call starts.
    const running = startTool(draft, {
      id: "execution-1",
      tool: "bash",
      label: "Bash",
      args: { command: "bun run test" },
    });
    expect(running[0]).toMatchObject({ id: "execution-1", status: "running" });
    rerender(<LiveTrace steps={running} />);
    expect(expanded(/Running bun/)).toBe("true");

    const done = endTool(running, { id: "execution-1", tool: "bash", output: "ok" });
    rerender(<LiveTrace steps={done} />);
    expect(expanded(/Ran bun.*Done/)).toBe("true");
  });

  it("keeps a row the user folded again folded as its call finishes", () => {
    const running = startTool([], {
      id: "execution-1",
      tool: "write",
      label: "Write",
      args: { path: "fit.py", content: "x = 1" },
    });
    const { rerender } = render(<LiveTrace steps={running} />);
    fireEvent.click(screen.getByRole("button", { name: /Writing fit.py/ }));
    fireEvent.click(screen.getByRole("button", { name: /Writing fit.py/ }));
    rerender(<LiveTrace steps={endTool(running, { id: "execution-1", tool: "write" })} />);
    expect(expanded(/Wrote fit.py/)).toBe("false");
  });

  it("draws one icon per row and no spinner", () => {
    const { container } = render(
      <LiveTrace steps={[tool({ tool: "bash", label: "Bash", args: { command: "ls -la" } })]} />,
    );
    const row = screen.getByRole("button", { name: /Running ls/ });
    expect(row.querySelectorAll("svg:not(.lucide-chevron-right)")).toHaveLength(1);
    expect(container.querySelector(".animate-spin")).toBeNull();
    expect(container.querySelector(".chain-marker")).toBeNull();
  });

  it("shows a tool this UI does not know by its own label and status", () => {
    render(
      <LiveTrace
        steps={[
          tool({ id: "x1", tool: "acme_lookup", label: "Acme lookup", args: { key: "v" } }),
          tool({
            id: "x2",
            tool: "acme_lookup",
            label: "Acme lookup",
            status: "error",
            endedAt: 1000,
            args: { key: "v" },
            output: "acme: not found",
          }),
        ]}
      />,
    );
    expect(expanded(/Acme lookup.*Running/)).toBe("false");
    const failed = screen.getByRole("button", { name: /Acme lookup.*Failed/ });
    expect(failed.querySelectorAll("svg:not(.lucide-chevron-right)")).toHaveLength(1);
    expect(screen.getByTestId("tool-failure-line").textContent).toBe("acme: not found");
    // Its raw arguments stay in the details, not on the row.
    expect(failed.textContent).not.toContain("key");
    expect(currentActivity([tool({ tool: "acme_lookup", label: "Acme lookup" })], null)).toBe(
      "Running Acme lookup",
    );
  });

  it("marks a failed call in text and keeps its last error line visible while folded", () => {
    render(
      <ChatTraceSummary
        trace={{
          durationMs: 4000,
          steps: [
            tool({
              id: "b1",
              tool: "bash",
              label: "Bash",
              status: "error",
              endedAt: 2000,
              args: { command: "python fit.py" },
              output: "Traceback (most recent call last):\nFileNotFoundError: data.csv",
              exitCode: 1,
            }),
            tool({ id: "g1", status: "done", endedAt: 500, args: { qid: "Q01" } }),
          ],
        }}
      />,
    );
    // The folded summary already says something failed.
    const summary = screen.getByRole("button", { name: /used 2 tools/i });
    expect(summary.textContent).toContain("1 failed");

    fireEvent.click(summary);
    const failed = screen.getByRole("button", { name: /Ran.*Failed/ });
    expect(failed.getAttribute("aria-expanded")).toBe("false");
    expect(within(failed).getByText("Failed")).toBeTruthy();
    expect(screen.getByTestId("tool-failure-line").textContent).toBe("FileNotFoundError: data.csv");
    expect(screen.getByRole("button", { name: /Get figure.*Done/ })).toBeTruthy();

    // Opened, the full output replaces the one-line excerpt.
    fireEvent.click(failed);
    expect(screen.queryByTestId("tool-failure-line")).toBeNull();
  });

  it("tells a cancelled call apart from a failed one", () => {
    render(
      <ChatTraceSummary
        trace={{
          durationMs: 1000,
          steps: [
            tool({
              tool: "bash",
              label: "Bash",
              status: "cancelled",
              endedAt: 400,
              draft: { command: "ls" },
            }),
          ],
        }}
      />,
    );
    const summary = screen.getByRole("button", { name: /used 1 tool/i });
    expect(summary.textContent).toContain("1 not run");
    expect(summary.textContent).not.toContain("failed");
    fireEvent.click(summary);
    const row = screen.getByRole("button", { name: /Command not run/ });
    expect(within(row).getByText("Not run")).toBeTruthy();
    expect(within(row).queryByText("Failed")).toBeNull();
  });
});

describe("currentActivity", () => {
  it("reads the activity from the steps that are actually in flight", () => {
    expect(currentActivity([tool({ tool: "bash", label: "Bash", status: "drafting" })], null)).toBe(
      "Writing a command",
    );
    expect(
      currentActivity(
        [tool({ tool: "bash", label: "Bash", status: "running", args: { command: "ls" } })],
        null,
      ),
    ).toBe("Running ls");
    expect(currentActivity([tool({ status: "running" })], null)).toBe("Running Get figure");
    expect(
      currentActivity(
        [tool({ id: "a", status: "running" }), tool({ id: "b", status: "running" })],
        null,
      ),
    ).toBe("Running 2 tools");
    expect(currentActivity([{ kind: "thinking", text: "hm", startedAt: 0 }], null)).toBe(
      "Thinking",
    );
    expect(
      currentActivity(
        [tool({ status: "done", endedAt: 1 }), { kind: "text", text: "T1 is" }],
        null,
      ),
    ).toBe("Writing the answer");
  });

  it("falls back to the server's status, or to nothing, between events", () => {
    const finished = [tool({ status: "done", endedAt: 1 })];
    expect(currentActivity(finished, "Compacting context")).toBe("Compacting context");
    expect(currentActivity(finished, null)).toBeNull();
  });

  it("draws the footer only when no trace row shows the activity, but always announces it", () => {
    const startedAt = Date.now() - 5000;
    const { rerender } = render(
      <TurnActivity
        steps={[tool({ status: "running" })]}
        startedAt={startedAt}
        statusMessage={null}
      />,
    );
    // A running row already says this; the footer is screen-reader only, without a timer.
    const footer = screen.getByTestId("turn-activity");
    expect(footer.className).toBe("sr-only");
    expect(screen.getByRole("status").textContent).toBe("Running Get figure");
    expect(footer.textContent).toBe("Running Get figure");

    // Writing the answer has no row, so the footer is drawn with its timer.
    rerender(
      <TurnActivity
        steps={[tool({ status: "done", endedAt: 1 }), { kind: "text", text: "T1 is" }]}
        startedAt={startedAt}
        statusMessage={null}
      />,
    );
    // The same live region stays mounted across the switch.
    expect(screen.getByTestId("turn-activity")).toBe(footer);
    expect(footer.className).not.toContain("sr-only");
    expect(screen.getByRole("status").textContent).toBe("Writing the answer");
    expect(footer.textContent).toMatch(/Writing the answer\d+s/);
  });
});

describe("commandName", () => {
  it.each([
    `TOKEN="private value more" bun test`,
    "TOKEN='private value more' bun test",
    String.raw`TOKEN=private\ value\ more bun test`,
    `TOKEN="private; value more" bun test`,
    "sudo -u root bun test",
    "env -u TOKEN bun test",
  ])("does not expose fragments from unsupported shell syntax: %s", (command) => {
    expect(commandName(command)).toBeNull();
  });

  it("names the program a command runs", () => {
    expect(commandName("bun run test:run src/components/features/chat")).toBe("bun");
    expect(commandName("cd ui && bunx vitest run")).toBe("bunx");
    expect(commandName("FOO=1 sudo /usr/bin/python3 fit.py\nls")).toBe("python3");
    expect(commandName("\n  uv run pytest -q | tail -5")).toBe("uv");
  });

  it("gives null when there is no plain program name to show", () => {
    expect(commandName(undefined)).toBeNull();
    expect(commandName("")).toBeNull();
    expect(commandName("cd ui")).toBeNull();
    expect(commandName("$(cat script)")).toBeNull();
    expect(commandName("'quoted thing' arg")).toBeNull();
  });
});
