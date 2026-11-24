import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TraceStep, TurnConnection } from "@/types/agentChat";

import {
  ChatTraceSummary,
  LiveTrace,
  STEADY_PHASE_MS,
  TurnActivity,
  activeToolsMode,
  currentActivity,
  displayStatusMessage,
  toolLogoMode,
} from "../ChatTrace";
import { ChatStatusLine, chatStatus } from "../ChatTurnStatus";

vi.mock("@/client/execution/execution", () => ({ useGetExecution: vi.fn() }));

type ToolStep = Extract<TraceStep, { kind: "tool" }>;

function tool(overrides: Partial<ToolStep>): ToolStep {
  return {
    kind: "tool",
    id: "t1",
    tool: "qdash_get_figure",
    label: "Get figure",
    status: "done",
    startedAt: 0,
    endedAt: 1000,
    ...overrides,
  };
}

const running = (overrides: Partial<ToolStep>): ToolStep =>
  tool({ status: "running", endedAt: undefined, ...overrides });

const thinking = (endedAt?: number): TraceStep => ({
  kind: "thinking",
  text: "which qubit next",
  startedAt: Date.now() - 2000,
  ...(endedAt === undefined ? {} : { endedAt }),
});

const logos = () => screen.queryAllByTestId("activity-logo");
const footer = () => screen.getByTestId("turn-activity");
const status = () => within(footer()).getByRole("status");

/** The live message as ChatMessages lays it out: the trace, then the footer. */
function Live({
  steps,
  statusMessage = null,
}: {
  steps: TraceStep[];
  statusMessage?: string | null;
}) {
  return (
    <>
      <LiveTrace steps={steps} />
      <TurnActivity steps={steps} startedAt={Date.now() - 2000} statusMessage={statusMessage} />
    </>
  );
}

beforeEach(() => {
  // jsdom has no 2D canvas; the mark's drawing is covered in ActivityLogo.test.tsx.
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/** Lucide icons drawn in an element, apart from disclosure chevrons. */
const icons = (el: Element) => el.querySelectorAll("svg:not(.lucide-chevron-right)");

describe("one live presentation", () => {
  it("draws no Brain on a live thought: the footer shows the mark and names it", () => {
    render(<Live steps={[tool({ id: "a" }), thinking()]} />);
    // The thought's row offers its text so far, as plain text, never a second "Thinking".
    const row = screen.getByRole("button", { name: "Thought so far" });
    expect(row.querySelector(".lucide-brain")).toBeNull();
    expect(icons(row)).toHaveLength(0);
    expect(row.querySelector(".loader-text-shimmer")).toBeNull();
    expect(screen.queryByText("Thinking", { selector: "button *" })).toBeNull();
    expect(document.querySelectorAll(".lucide-brain")).toHaveLength(0);
    // The earlier, finished call keeps its static icon.
    expect(icons(screen.getByRole("button", { name: /Get figure.*Done/ }))).toHaveLength(1);
    expect(logos()).toHaveLength(1);
    expect(within(footer()).getByTestId("activity-logo")).toHaveAttribute("data-mode", "thinking");
    expect(status()).toBeVisible();
    expect(status().textContent).toBe("Thinking");
  });

  it("has no row for a live thought with no text yet", () => {
    render(<Live steps={[{ kind: "thinking", text: "", startedAt: Date.now() }]} />);
    expect(screen.queryByTestId("trace-work")).toBeNull();
    expect(status().textContent).toBe("Thinking");
  });

  it("draws no icon on a running call: the footer names it beside the one mark", () => {
    render(<Live steps={[running({ tool: "bash", label: "Bash", args: { command: "ls" } })]} />);
    const row = screen.getByRole("button", { name: /Running ls/ });
    expect(icons(row)).toHaveLength(0);
    expect(row.querySelector(".loader-text-shimmer")).toBeNull();
    expect(row.querySelector("canvas")).toBeNull();
    // Its icon's place is held, so the title does not move when the call ends.
    expect(within(row).getByTestId("icon-slot")).toBeTruthy();
    expect(logos()).toHaveLength(1);
    expect(status().textContent).toBe("Running ls");
    // The footer names the call: the row only opens its details, with no second heading
    // or timer. Its name stays for assistive tech.
    expect(screen.getAllByText("Running ls")).toHaveLength(2);
    expect(within(row).getByText("Running ls")).toHaveClass("sr-only");
    expect(within(row).getByText("Details")).toBeVisible();
    expect(within(row).queryByText(/\d+s$/)).toBeNull();
  });

  it("names each call in its row when several run and the footer counts them", () => {
    render(
      <Live
        steps={[
          running({ id: "a", tool: "bash", label: "Bash", args: { command: "ls" } }),
          running({ id: "b", tool: "bash", label: "Bash", args: { command: "uv run fit" } }),
        ]}
      />,
    );
    expect(status().textContent).toBe("Running 2 tools");
    fireEvent.click(screen.getByTestId("tool-group-summary"));
    for (const name of ["Running ls", "Running uv"]) {
      const row = screen.getByRole("button", { name: new RegExp(name) });
      expect(within(row).getByText(name)).not.toHaveClass("sr-only");
      expect(icons(row)).toHaveLength(0);
    }
  });

  it("gives the running call its title back while the footer shows only a lost connection", () => {
    const steps = [running({ tool: "bash", label: "Bash", args: { command: "ls" } })];
    render(
      <>
        <LiveTrace steps={steps} activityInFooter={false} />
        <TurnActivity
          steps={steps}
          startedAt={Date.now()}
          statusMessage={null}
          connection={{ state: "reconnecting", lastUpdateAt: Date.now() - 2000, attempt: 1 }}
        />
      </>,
    );
    const row = screen.getByRole("button", { name: /Running ls/ });
    expect(within(row).getByText("Running ls")).not.toHaveClass("sr-only");
    expect(icons(row)).toHaveLength(0);
    expect(logos()).toHaveLength(0);
    expect(status().textContent).toBe("Connection lost, reconnecting");
  });

  it("draws no wrench on a live group, only its count; the footer says what runs", () => {
    render(<Live steps={[tool({ id: "a" }), running({ id: "b" }), running({ id: "c" })]} />);
    const summary = screen.getByTestId("tool-group-summary");
    expect(summary.querySelector(".lucide-wrench")).toBeNull();
    expect(icons(summary)).toHaveLength(0);
    expect(summary.querySelector(".loader-text-shimmer")).toBeNull();
    expect(summary.textContent).toContain("3 tool calls");
    expect(summary.textContent).not.toContain("Running");
    expect(logos()).toHaveLength(1);
    expect(status().textContent).toBe("Running 2 tools");
  });

  it("keeps meaningful static icons on settled history: tools, failures, not run, thoughts", () => {
    const steps: TraceStep[] = [
      { kind: "thinking", text: "plan", startedAt: 0, endedAt: 2000 },
      tool({ id: "a", tool: "bash", label: "Bash", args: { command: "ls" } }),
      tool({ id: "b", status: "error", output: "boom" }),
      tool({ id: "c", status: "cancelled" }),
    ];
    render(<ChatTraceSummary trace={{ steps, durationMs: 4000 }} />);
    const summary = screen.getByTestId("tool-group-summary");
    expect(summary.querySelector(".lucide-wrench")).not.toBeNull();
    fireEvent.click(summary);
    expect(
      screen.getByRole("button", { name: /Thought for 2s/ }).querySelector(".lucide-brain"),
    ).not.toBeNull();
    expect(icons(screen.getByRole("button", { name: /Ran ls/ }))).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: /Get figure.*Failed/ }).querySelector(".lucide-circle-x"),
    ).not.toBeNull();
    expect(
      screen.getByRole("button", { name: /Get figure.*Not run/ }).querySelector(".lucide-ban"),
    ).not.toBeNull();
    expect(logos()).toHaveLength(0);
  });

  it("keeps settled rows' icons while a later call runs", () => {
    render(
      <Live
        steps={[
          tool({ id: "a", tool: "bash", label: "Bash", args: { command: "ls" } }),
          { kind: "text", text: "Now the figure." },
          running({ id: "b" }),
        ]}
      />,
    );
    expect(icons(screen.getByRole("button", { name: /Ran ls/ }))).toHaveLength(1);
    // The running call has nothing to show beyond its name, which the footer gives.
    expect(screen.queryByRole("button", { name: /Get figure.*Running/ })).toBeNull();
    expect(status().textContent).toBe("Running Get figure");
    expect(logos()).toHaveLength(1);
  });

  it("announces the activity once across the title line and the footer", () => {
    const steps = [running({ tool: "bash", label: "Bash", args: { command: "ls" } })];
    const header = chatStatus({
      run: { turn: { steps, startedAt: 0 }, statusMessage: null },
      messages: [],
    } as unknown as Parameters<typeof chatStatus>[0]);
    render(
      <>
        <ChatStatusLine status={header} />
        <Live steps={steps} />
      </>,
    );
    expect(screen.queryByTestId("chat-status")).toBeNull();
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.getAllByText("Running ls", { selector: "[role=status]" })).toHaveLength(1);
    expect(logos()).toHaveLength(1);
  });

  it("is a fixed 20px slot with no negative margin, beside a visible label", () => {
    render(<Live steps={[thinking()]} />);
    const [mark] = logos();
    expect(mark.style.width).toBe("20px");
    expect(mark.style.height).toBe("20px");
    expect(mark.className).not.toMatch(/-m-/);
    expect(mark.parentElement).toBe(footer());
    expect(footer().className).not.toMatch(/(^|\s)-m/);
    expect(status()).not.toHaveClass("sr-only");
    expect(mark.nextElementSibling).toBe(status());
  });

  it("never animates a saved trace", () => {
    render(<ChatTraceSummary trace={{ steps: [thinking()], durationMs: 2000 }} />);
    expect(logos()).toHaveLength(0);
  });
});

describe("mark modes", () => {
  it("searches only for the named search tool, never by label", () => {
    expect(toolLogoMode(running({ tool: "qdash_search_source" }))).toBe("searching");
    // Same tool still being written: not searching yet.
    expect(toolLogoMode({ tool: "qdash_search_source", status: "drafting" })).toBe("working");
    expect(toolLogoMode(running({ tool: "acme_search", label: "Search docs" }))).toBe("working");
    expect(toolLogoMode(running({ tool: "qdash_query", label: "QDash Query" }))).toBe("working");
  });

  it("waits only on a person's answer; an execution wait is work", () => {
    expect(toolLogoMode(running({ tool: "qdash_wait_agent_intervention" }))).toBe("waiting");
    expect(toolLogoMode(running({ tool: "qdash_wait_execution" }))).toBe("working");
    expect(toolLogoMode(running({ tool: "qdash_wait_agent_action" }))).toBe("working");
  });

  it("shows one mode for calls in flight together: theirs if shared, else working", () => {
    const search = running({ tool: "qdash_search_source" });
    expect(activeToolsMode([search, { ...search, id: "s2" }])).toBe("searching");
    expect(activeToolsMode([search, running({ tool: "qdash_query" })])).toBe("working");
    expect(activeToolsMode([running({ tool: "qdash_wait_agent_intervention" }), running({})])).toBe(
      "working",
    );
  });

  it("draws a concurrent search and query as one working mark", () => {
    render(
      <Live
        steps={[
          running({ id: "s", tool: "qdash_search_source" }),
          running({ id: "q", tool: "qdash_query" }),
        ]}
      />,
    );
    expect(logos()).toHaveLength(1);
    expect(footer()).toHaveAttribute("data-mode", "working");
    // The footer names the calls in flight; the summary only counts them.
    expect(status().textContent).toBe("Running 2 tools");
    expect(screen.getByTestId("tool-group-summary").textContent).toContain("2 tool calls");
  });
});

describe("the server's thinking note", () => {
  it("reads as Thinking in the footer, the header and the stored activity", () => {
    expect(displayStatusMessage("AI is thinking...")).toBe("Thinking");
    expect(displayStatusMessage("Compacting context")).toBe("Compacting context");
    expect(displayStatusMessage(null)).toBeNull();
    const done = [tool({})];
    expect(currentActivity(done, "AI is thinking...")).toBe("Thinking");
    const header = chatStatus({
      run: { turn: { steps: done, startedAt: 0 }, statusMessage: "AI is thinking..." },
      messages: [],
    } as unknown as Parameters<typeof chatStatus>[0]);
    expect(header?.label).toBe("Thinking");
  });

  it("after a tool result shows the thinking mark and label, once", () => {
    render(<Live steps={[tool({})]} statusMessage="AI is thinking..." />);
    expect(status().textContent).toBe("Thinking");
    expect(footer().textContent).toMatch(/^Thinking\d+s$/);
    expect(screen.queryByText("AI is thinking...")).toBeNull();
    expect(logos()).toHaveLength(1);
    expect(footer()).toHaveAttribute("data-mode", "thinking");
  });

  it("before the first event shows the same, without typing dots", () => {
    render(<Live steps={[]} />);
    expect(status().textContent).toBe("Thinking");
    expect(footer().querySelector('[style*="loader-typing"]')).toBeNull();
    expect(logos()).toHaveLength(1);
  });

  it("keeps any other server status as sent", () => {
    render(<Live steps={[]} statusMessage="Compacting context" />);
    expect(status().textContent).toBe("Compacting context");
    expect(logos()).toHaveLength(1);
  });
});

describe("a steady footer", () => {
  const bash = running({ id: "a", tool: "bash", label: "Bash", args: { command: "ls" } });
  const bashDone = { ...bash, status: "done" as const, endedAt: 1000 };
  const next = running({ id: "b", tool: "qdash_get_figure", label: "Get figure" });
  const lost = { state: "reconnecting", lastUpdateAt: Date.now() - 2000, attempt: 1 };

  function setup(steps: TraceStep[], statusMessage: string | null = null) {
    vi.useFakeTimers();
    const view = render(
      <TurnActivity steps={steps} startedAt={Date.now()} statusMessage={statusMessage} />,
    );
    const update = (s: TraceStep[], message: string | null = null, connection: unknown = null) =>
      view.rerender(
        <TurnActivity
          steps={s}
          startedAt={Date.now()}
          statusMessage={message}
          connection={connection as TurnConnection | null}
        />,
      );
    return { ...view, update };
  }

  it("always shows a label beside the mark, never the mark alone", () => {
    setup([bash]);
    expect(logos()).toHaveLength(1);
    expect(status()).toBeVisible();
    expect(status()).not.toHaveClass("sr-only");
    expect(status().textContent).toBe("Running ls");
  });

  it("shows meaningful server status immediately after a tool", () => {
    const { update } = setup([bash]);
    update([bashDone], "Compacting context");
    expect(status().textContent).toBe("Compacting context");
  });

  it("does not flash Thinking in the short gap between two calls", () => {
    const { update } = setup([bash]);
    const mark = logos()[0];
    const region = status();
    expect(footer()).toHaveAttribute("data-mode", "working");

    update([bashDone], "AI is thinking...");
    act(() => vi.advanceTimersByTime(STEADY_PHASE_MS - 200));
    // Mode and label hold: the generic thought has not lasted yet.
    expect(footer()).toHaveAttribute("data-mode", "working");
    expect(status().textContent).toBe("Running ls");

    // The next call is named at once: the label is never a stale tool.
    update([bashDone, next]);
    expect(status().textContent).toBe("Running Get figure");
    act(() => vi.advanceTimersByTime(STEADY_PHASE_MS * 2));
    expect(footer()).toHaveAttribute("data-mode", "working");
    expect(status().textContent).toBe("Running Get figure");
    // The same canvas and live region the whole time: nothing remounted.
    expect(logos()[0]).toBe(mark);
    expect(status()).toBe(region);
  });

  it("shows a generic thought and a new mode once they have held", () => {
    const { update } = setup([bash]);
    update([bashDone], "AI is thinking...");
    act(() => vi.advanceTimersByTime(STEADY_PHASE_MS));
    expect(footer()).toHaveAttribute("data-mode", "thinking");
    expect(footer().textContent).toMatch(/^Thinking\d+s$/);

    // The search is named at once; its decorative mode follows once it holds.
    const search = running({ id: "s", tool: "qdash_search_source", label: "Search source" });
    update([bashDone, search]);
    expect(status().textContent).toBe(currentActivity([search], null));
    expect(status().textContent).not.toBe("Thinking");
    expect(footer()).toHaveAttribute("data-mode", "thinking");
    act(() => vi.advanceTimersByTime(STEADY_PHASE_MS));
    expect(footer()).toHaveAttribute("data-mode", "searching");
  });

  it("counts several calls in flight, and names the last when only one runs", () => {
    const { update } = setup([bash]);
    update([bash, next]);
    expect(status().textContent).toBe("Running 2 tools");
    update([bashDone, next]);
    expect(status().textContent).toBe("Running Get figure");
  });

  it("shows a wait on a person at once", () => {
    const { update } = setup([bash]);
    update([bashDone, running({ id: "w", tool: "qdash_wait_agent_intervention" })]);
    expect(footer()).toHaveAttribute("data-mode", "waiting");
    expect(status().textContent).toBe("Waiting for the expert's answer");
  });

  it("drops mark and label at once when the connection is lost, and restores both", () => {
    const { update } = setup([bash]);
    update([bash], null, lost);
    expect(logos()).toHaveLength(0);
    expect(screen.queryByTestId("turn-activity-label")).toBeNull();
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(status().textContent).toBe("Connection lost, reconnecting");
    expect(screen.getByTestId("turn-connection").className).toMatch(/text-warning/);

    update([bash], null, { state: "live", lastUpdateAt: Date.now(), attempt: 0 });
    expect(logos()).toHaveLength(1);
    expect(status().textContent).toBe("Running ls");
    expect(footer()).toHaveAttribute("data-mode", "working");
  });

  it("leaves no timer behind when the turn ends", () => {
    const { update, unmount } = setup([bash]);
    update([bashDone], "AI is thinking...");
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
