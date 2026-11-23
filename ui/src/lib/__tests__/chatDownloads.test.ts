import { afterEach, describe, expect, it, vi } from "vitest";

import {
  answerFileName,
  answerMarkdown,
  codeBlockTitle,
  codeFileName,
  downloadText,
  fenceTitle,
  fencedCode,
  hasAnswerMarkdown,
  safeFileName,
  writtenFiles,
} from "@/lib/chatDownloads";
import type { TraceStep } from "@/types/copilotChat";

function blocks(...items: object[]): string {
  return JSON.stringify({ blocks: items, assessment: null });
}

function write(
  id: string,
  path: unknown,
  content: unknown,
  status = "done",
): Extract<TraceStep, { kind: "tool" }> {
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

afterEach(() => {
  vi.restoreAllMocks();
});

describe("chatDownloads", () => {
  it("keeps only a safe last path segment as the file name", () => {
    expect(safeFileName("/workspace/owner/session/out/report.md")).toBe("report.md");
    expect(safeFileName("..\\..\\etc\\passwd")).toBe("passwd");
    expect(safeFileName("../")).toBe("download.txt");
    expect(safeFileName(".env")).toBe("env");
    expect(safeFileName('a<b>:"c|?.md')).toBe("a_b_c_.md");
    const long = safeFileName(`${"n".repeat(300)}.csv`);
    expect(long).toHaveLength(120);
    expect(long.endsWith(".csv")).toBe(true);
  });

  it("names a code block by its title or language", () => {
    expect(codeFileName("python")).toBe("snippet.py");
    expect(codeFileName(undefined)).toBe("snippet.txt");
    expect(codeFileName("python", "analysis/fit.py")).toBe("fit.py");
    expect(codeFileName("yaml", "config")).toBe("config.yaml");
    expect(codeFileName("python:fit.py")).toBe("snippet.py");
    expect(codeFileName("mermaid")).toBe("snippet.mmd");
    expect(codeFileName("python", "../../.bashrc")).toBe("bashrc.py");
  });

  it("reads a file name from a fence's info string", () => {
    expect(fenceTitle('python title="analysis/fit.py"')).toBe("analysis/fit.py");
    expect(fenceTitle("python title='fit v2.py'")).toBe("fit v2.py");
    expect(fenceTitle("json filename=run.json")).toBe("run.json");
    expect(fenceTitle("bash file=setup.sh {1,3}")).toBe("setup.sh");
    expect(fenceTitle("python:src/fit.py")).toBe("src/fit.py");
    expect(fenceTitle("python fit.py")).toBe("fit.py");
    expect(fenceTitle("python")).toBeUndefined();
    expect(fenceTitle("python {1,3}")).toBeUndefined();
    expect(fenceTitle('python title=""')).toBeUndefined();
  });

  it("finds fenced code blocks with their titles, also inside lists and quotes", () => {
    const markdown = [
      "Intro",
      '```python title="a.py"',
      "x = 1",
      "",
      "```",
      "- item",
      "  ~~~yaml file=b.yaml",
      "  k: v",
      "    nested: 1",
      "  ~~~",
      "> ```sh",
      "> echo hi",
      "> ```",
      "````md",
      "```",
      "inner",
      "```",
      "````",
    ].join("\n");
    expect(fencedCode(markdown)).toEqual([
      { code: "x = 1\n", title: "a.py" },
      { code: "k: v\n  nested: 1", title: "b.yaml" },
      { code: "echo hi", title: undefined },
      { code: "```\ninner\n```", title: undefined },
    ]);
    // Rendered code ends with a newline; the source's trailing newlines do not matter.
    expect(codeBlockTitle(markdown, "k: v\n  nested: 1\n")).toBe("b.yaml");
    expect(codeBlockTitle(markdown, "echo hi\n")).toBeUndefined();
    expect(codeBlockTitle(markdown, "x = 1\n", 1)).toBeUndefined();
    expect(codeBlockTitle(markdown, "missing")).toBeUndefined();
  });

  it("turns an answer into Markdown with its text and proposed code", () => {
    const content = blocks(
      { type: "text", content: "## T1 summary\n\nQ05 is stable." },
      { type: "chart", content: null, chart: { data: [], layout: {} } },
      {
        type: "edit",
        content: null,
        chart: null,
        edit: {
          summary: "Raise shots",
          code: "shots = 2048\nprint('```')",
          flowName: "daily",
          chipId: null,
          pagePath: "/flow",
        },
      },
    );
    const markdown = answerMarkdown(content);
    expect(markdown).toContain("## T1 summary\n\nQ05 is stable.");
    expect(markdown).toContain("**Proposed change to `daily`:** Raise shots");
    // The fence is longer than the backticks inside the code.
    expect(markdown).toContain("````python\nshots = 2048\nprint('```')\n````");
    expect(markdown.endsWith("\n")).toBe(true);
    expect(answerMarkdown("plain **answer**")).toBe("plain **answer**\n");
    expect(hasAnswerMarkdown(blocks({ type: "chart", content: null }))).toBe(false);
  });

  it("names an answer file by its first heading or the time", () => {
    expect(answerFileName(blocks({ type: "text", content: "# `T1` / T2 report\n\nok" }))).toBe(
      "T1-T2-report.md",
    );
    expect(answerFileName("no heading", new Date(2026, 10, 23, 9, 5))).toBe(
      "qdash-answer-20261123-0905.md",
    );
  });

  it("offers each finished write once, with its newest content", () => {
    const steps: TraceStep[] = [
      write("1", "out/report.md", "v1"),
      write("2", "data.csv", "a,b\n"),
      write("3", "out/report.md", "v2"),
      write("4", "failed.txt", "x", "error"),
      write("5", "cut.txt", undefined),
      { ...write("6", "", ""), args: '{"path":"trunc.md","content":"…' },
      write("7", "fit.py", "a = 1"),
      { ...write("8", "fit.py", undefined), tool: "edit" },
      write("9", "plot.py", "b = 2"),
      { ...write("10", "", ""), tool: "edit", args: '{"path":"plot.py","edits":[{"oldText":"…' },
      { kind: "text", text: "done" },
    ];
    expect(writtenFiles(steps)).toEqual([
      { path: "data.csv", fileName: "data.csv", content: "a,b\n" },
      { path: "out/report.md", fileName: "report.md", content: "v2" },
    ]);
    expect(writtenFiles(undefined)).toEqual([]);
  });

  it("removes obsolete snapshots when an overwrite has unavailable content", () => {
    const original = write("1", "report.md", "old content");
    expect(
      writtenFiles([
        original,
        { ...write("2", "", ""), args: '{"path":"report.md","content":"truncated' },
      ]),
    ).toEqual([]);
    expect(writtenFiles([original, write("2", "report.md", undefined)])).toEqual([]);
    // If truncation hides the path, none of the previous snapshots are reliable.
    expect(
      writtenFiles([original, { ...write("2", "", ""), args: '{"content":"truncated' }]),
    ).toEqual([]);
  });

  it("hides a snapshot after any attempted change to the same file", () => {
    const original = write("1", "out/report.md", "v1");
    const keep = write("2", "notes.md", "n");
    // A failed or running overwrite may still have changed the file.
    expect(writtenFiles([original, keep, write("3", "out/report.md", "v2", "error")])).toEqual([
      { path: "notes.md", fileName: "notes.md", content: "n" },
    ]);
    expect(writtenFiles([original, write("3", "out/report.md", "v2", "running")])).toEqual([]);
    // A cancelled call never ran.
    expect(writtenFiles([original, write("3", "out/report.md", "v2", "cancelled")])).toHaveLength(
      1,
    );
    // Relative and absolute forms of the same path match.
    expect(
      writtenFiles([
        original,
        { ...write("3", "/workspace/s1/out/report.md", undefined), tool: "edit" },
      ]),
    ).toEqual([]);
    expect(
      writtenFiles([original, { ...write("3", "./out//report.md", undefined), tool: "edit" }]),
    ).toEqual([]);
    expect(
      writtenFiles([original, { ...write("3", "other/report.md", undefined), tool: "edit" }]),
    ).toHaveLength(1);
  });

  it("does not offer a write the turn ended before it finished", () => {
    const original = write("1", "fit.py", "old");
    const interrupted = { ...write("2", "fit.py", "new"), interrupted: true };
    expect(writtenFiles([interrupted])).toEqual([]);
    // It also hides the earlier snapshot, since the file may have changed.
    expect(writtenFiles([original, interrupted])).toEqual([]);
  });

  it("downloads text through a temporary object URL", () => {
    vi.useFakeTimers();
    const createObjectURL = vi.fn(() => "blob:qdash");
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    downloadText("report.md", "# Hi\n");

    const blob = (createObjectURL.mock.calls[0] as unknown as [Blob])[0];
    expect(blob.type).toBe("text/markdown;charset=utf-8");
    expect(click).toHaveBeenCalledOnce();
    const link = click.mock.instances[0] as unknown as HTMLAnchorElement;
    expect(link.download).toBe("report.md");
    expect(document.querySelector("a[download]")).toBeNull();
    vi.runAllTimers();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:qdash");
    vi.useRealTimers();
  });
});
