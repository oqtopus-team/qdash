import { describe, expect, it, vi } from "vitest";

import {
  attachPythonFormatter,
  describeFormatProblem,
  formatEditorDocument,
} from "@/lib/pythonFormatter";
import type { FormatSourceResponse } from "@/schemas";

import { createFakeEditor, createFakeMonaco, deferred } from "./fakeMonaco";

const formatted = (source: string): FormatSourceResponse => ({ status: "formatted", source });

describe("attachPythonFormatter", () => {
  it("shares one Python provider among editors and removes it with the last editor", () => {
    const fake = createFakeMonaco();
    const first = createFakeEditor(fake, "a=1\n");
    const second = createFakeEditor(fake, "b=1\n");
    const format = vi.fn();

    attachPythonFormatter(fake.monaco, first, { format });
    attachPythonFormatter(fake.monaco, second, { format });

    expect(fake.providers).toHaveLength(1);
    expect(fake.providers[0].selector).toBe("python");
    first.dispose();
    expect(fake.active()).toHaveLength(1);
    second.dispose();
    expect(fake.active()).toHaveLength(0);
  });

  it("formats only the models of attached editors", async () => {
    const fake = createFakeMonaco();
    const editor = createFakeEditor(fake, "a=1\n");
    const handle = attachPythonFormatter(fake.monaco, editor, {
      format: async () => formatted("a = 1\n"),
    });
    const provider = fake.providers[0].provider;
    const token = { isCancellationRequested: false };

    expect(await provider.provideDocumentFormattingEdits(editor.getModel(), {}, token)).toEqual([
      { range: { full: true }, text: "a = 1\n" },
    ]);
    const previous = editor.getModel();
    editor.swapModel();
    expect(await provider.provideDocumentFormattingEdits(previous, {}, token)).toEqual([]);
    expect(
      await provider.provideDocumentFormattingEdits(editor.getModel(), {}, token),
    ).toHaveLength(1);

    handle.dispose();
    expect(fake.active()).toHaveLength(0);
  });

  it("reports an explicit Format Document run and applies it as an undoable edit", async () => {
    const fake = createFakeMonaco();
    const editor = createFakeEditor(fake, "a=1\n");
    const onRun = vi.fn();
    attachPythonFormatter(fake.monaco, editor, { format: async () => formatted("a = 1\n"), onRun });

    await editor.getAction("editor.action.formatDocument")?.run();

    expect(editor.getModel().getValue()).toBe("a = 1\n");
    expect(onRun).toHaveBeenCalledWith({ status: "formatted", text: "a = 1\n" });
    editor.undo();
    expect(editor.getModel().getValue()).toBe("a=1\n");
  });

  it("keeps the text on a syntax error or a failed request", async () => {
    const fake = createFakeMonaco();
    const editor = createFakeEditor(fake, "def f(:\n");
    const onRun = vi.fn();
    const format = vi
      .fn()
      .mockResolvedValueOnce({
        status: "syntax_error",
        source: "def f(:\n",
        diagnostic: { message: "Expected a parameter", line: 1, column: 7 },
      })
      .mockRejectedValueOnce({ response: { data: { detail: "Formatting failed: busy" } } });
    attachPythonFormatter(fake.monaco, editor, { format, onRun });
    const action = editor.getAction("editor.action.formatDocument");

    await action?.run();
    await action?.run();

    expect(editor.getModel().getValue()).toBe("def f(:\n");
    expect(describeFormatProblem(onRun.mock.calls[0][0])).toBe("Line 1:7: Expected a parameter");
    expect(describeFormatProblem(onRun.mock.calls[1][0])).toBe("Formatting failed: busy");
  });
});

describe("formatEditorDocument", () => {
  it("returns the formatted text without notifying the explicit-run listener", async () => {
    const fake = createFakeMonaco();
    const editor = createFakeEditor(fake, "a=1\n");
    const onRun = vi.fn();
    const format = vi.fn(async () => formatted("a = 1\n"));
    attachPythonFormatter(fake.monaco, editor, { format, onRun });

    const run = await formatEditorDocument(editor, "a=1\n");

    expect(run).toEqual({ status: "formatted", text: "a = 1\n" });
    expect(format).toHaveBeenCalledWith("a=1\n");
    expect(onRun).not.toHaveBeenCalled();
  });

  it("drops a result that answers after the text changed", async () => {
    const fake = createFakeMonaco();
    const editor = createFakeEditor(fake, "a=1\n");
    const answer = deferred<FormatSourceResponse>();
    attachPythonFormatter(fake.monaco, editor, { format: () => answer.promise });

    const pending = formatEditorDocument(editor, "a=1\n");
    editor.type("a=2\n");
    answer.resolve(formatted("a = 1\n"));

    expect(await pending).toEqual({ status: "stale", text: null });
    expect(editor.getModel().getValue()).toBe("a=2\n");
  });

  it("reports the text as written when it cannot be formatted", async () => {
    const fake = createFakeMonaco();
    const editor = createFakeEditor(fake, "def f(:\n");
    attachPythonFormatter(fake.monaco, editor, {
      format: async () => ({ status: "syntax_error", source: "def f(:\n" }),
    });

    const run = await formatEditorDocument(editor, "def f(:\n");

    expect(run).toEqual(expect.objectContaining({ status: "syntax_error", text: "def f(:\n" }));
  });

  it("does not format a read-only or detached editor", async () => {
    const fake = createFakeMonaco();
    const readOnly = createFakeEditor(fake, "a=1\n", { writable: false });
    const format = vi.fn();
    attachPythonFormatter(fake.monaco, readOnly, { format });
    const detached = createFakeEditor(fake, "b=1\n");

    expect(await formatEditorDocument(readOnly, "a=1\n")).toEqual({
      status: "unavailable",
      text: "a=1\n",
    });
    expect(await formatEditorDocument(detached, "b=1\n")).toEqual({
      status: "unavailable",
      text: "b=1\n",
    });
    expect(await formatEditorDocument(null, "c=1\n")).toEqual({
      status: "unavailable",
      text: "c=1\n",
    });
    expect(format).not.toHaveBeenCalled();
  });

  it("stops formatting an editor once it is disposed", async () => {
    const fake = createFakeMonaco();
    const editor = createFakeEditor(fake, "a=1\n");
    const format = vi.fn();
    attachPythonFormatter(fake.monaco, editor, { format });

    editor.dispose();

    expect((await formatEditorDocument(editor, "a=1\n")).status).toBe("unavailable");
    expect(format).not.toHaveBeenCalled();
  });
});
