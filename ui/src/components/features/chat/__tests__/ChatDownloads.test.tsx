import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/Tooltip";
import { endTool, startTool, toPersistedTrace } from "@/lib/agentChatStream";
import type { TraceStep } from "@/types/agentChat";
import { AssistantMessage } from "../ChatMessages";

vi.mock("@/components/features/chat/ChatPlotlyChart", () => ({ ChatPlotlyChart: () => null }));

const saveBlob = vi.hoisted(() => vi.fn<(blob: Blob, filename: string) => void>());
vi.mock("@/lib/utils/download", () => ({ saveBlob }));

beforeEach(() => saveBlob.mockReset());
afterEach(cleanup);

function renderAnswer(content: string) {
  render(
    <TooltipProvider>
      <AssistantMessage
        message={{ role: "assistant", content }}
        isLast
        canRetry={false}
        onRetry={vi.fn()}
        onAnswer={vi.fn()}
        onDecide={vi.fn()}
        onOther={vi.fn()}
        onRate={vi.fn()}
      />
    </TooltipProvider>,
  );
}

async function savedFile(): Promise<{ name: string; text: string }> {
  expect(saveBlob).toHaveBeenCalledOnce();
  const [blob, name] = saveBlob.mock.calls[0];
  return { name, text: await blob.text() };
}

function answer(extra: object = {}, steps?: TraceStep[]): string {
  return JSON.stringify({
    blocks: [{ type: "text", content: "## T1 report\n\nQ05 is stable.", chart: null }],
    assessment: null,
    ...(steps ? { trace: { steps, durationMs: 5 } } : {}),
    ...extra,
  });
}

type ToolStep = Extract<TraceStep, { kind: "tool" }>;

function write(id: string, path: string, content: string, status = "done"): ToolStep {
  return {
    kind: "tool",
    id,
    tool: "write",
    label: "Write",
    status: status as "done",
    startedAt: 0,
    args: { path, content },
  };
}

/** A live turn's steps folded and stored as the chat stores them, then read back. */
function storedSteps(steps: TraceStep[]): TraceStep[] {
  const trace = toPersistedTrace(
    { steps: [...steps, { kind: "text", text: "ok" }], startedAt: 0 },
    9,
  );
  return (JSON.parse(JSON.stringify(trace)) as { steps: TraceStep[] }).steps;
}

function finishedWrite(id: string, path: string, content: string): TraceStep[] {
  return endTool(startTool([], { id, tool: "write", label: "Write", args: { path, content } }), {
    id,
    tool: "write",
    output: "Wrote file",
  });
}

describe("saving an answer as Markdown", () => {
  it("saves a completed answer, named by its heading", async () => {
    renderAnswer(answer());
    fireEvent.click(screen.getByRole("button", { name: "Save as Markdown" }));
    expect(await savedFile()).toEqual({
      name: "T1-report.md",
      text: "## T1 report\n\nQ05 is stable.\n",
    });
  });

  it("saves a plain-text answer", async () => {
    renderAnswer("Plain **answer**");
    fireEvent.click(screen.getByRole("button", { name: "Save as Markdown" }));
    expect((await savedFile()).text).toBe("Plain **answer**\n");
  });

  it("is not offered for an answer in progress, stopped, or without text", () => {
    renderAnswer(answer({ in_progress: true }));
    expect(screen.queryByRole("button", { name: "Save as Markdown" })).toBeNull();
    cleanup();
    renderAnswer(answer({ stopped: true }));
    expect(screen.queryByRole("button", { name: "Save as Markdown" })).toBeNull();
    cleanup();
    renderAnswer(JSON.stringify({ blocks: [{ type: "chart", content: null }], assessment: null }));
    expect(screen.queryByRole("button", { name: "Save as Markdown" })).toBeNull();
  });
});

describe("downloading written files", () => {
  it("offers the original write content held by the chat", async () => {
    renderAnswer(answer({}, [write("1", "/workspace/s1/out/report.md", "# Report\n")]));
    const group = screen.getByRole("group", { name: "Files written in this answer" });
    expect(group).toHaveTextContent("Original write content from this answer");
    expect(group).toHaveTextContent("Later changes to these files are not included.");

    fireEvent.click(
      within(group).getByRole("button", {
        name: "Download original write content of /workspace/s1/out/report.md",
      }),
    );
    expect(await savedFile()).toEqual({ name: "report.md", text: "# Report\n" });
  });

  it("hides a snapshot that a later edit or unknown overwrite made obsolete", () => {
    renderAnswer(
      answer({}, [
        write("1", "fit.py", "a = 1"),
        { ...write("2", "fit.py", ""), tool: "edit" },
        write("3", "data.csv", "a,b"),
        { ...write("4", "", ""), args: '{"content":"cut short' },
      ]),
    );
    expect(screen.queryByRole("group", { name: "Files written in this answer" })).toBeNull();
  });

  it("offers a large file after the answer is stored and reloaded", async () => {
    const content = `${"row,value\n".repeat(2_000)}end\n`;
    renderAnswer(answer({}, storedSteps(finishedWrite("w1", "out/table.csv", content))));
    fireEvent.click(
      screen.getByRole("button", { name: "Download original write content of out/table.csv" }),
    );
    expect(await savedFile()).toEqual({ name: "table.csv", text: content });
  });

  it("offers nothing for a stored write that was cut short or still running", () => {
    // Older chats stored every call's arguments cut to a JSON prefix.
    const legacy = `${JSON.stringify({ path: "out/big.csv", content: "x".repeat(5_000) }).slice(0, 4_000)}…`;
    renderAnswer(answer({}, [{ ...write("1", "", ""), args: legacy }]));
    expect(screen.queryByRole("group", { name: "Files written in this answer" })).toBeNull();
    cleanup();

    const running = startTool([], {
      id: "w1",
      tool: "write",
      label: "Write",
      args: { path: "fit.py", content: "a = 1" },
    });
    renderAnswer(answer({ stopped: true }, storedSteps(running)));
    expect(screen.queryByRole("group", { name: "Files written in this answer" })).toBeNull();
  });
});
