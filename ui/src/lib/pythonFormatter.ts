/**
 * Python formatting for Monaco editors through QDash's shared Ruff formatter.
 *
 * `attachPythonFormatter` connects one editor to a format request: Monaco's Format Document
 * (Shift+Alt+F, the context menu, or `editor.action.formatDocument`) then sends the editor's
 * text to the server and applies the result as an undoable edit. Monaco has one formatting
 * provider registry per language, so a single Python provider is registered while any editor
 * is attached, and it formats only the models of attached editors.
 *
 * `formatEditorDocument` runs the same action and reports what happened, so a save can store
 * exactly the text the editor shows. A result that answers after the text changed is never
 * applied.
 */
import type { FormatSourceResponse } from "@/schemas";
import { getApiErrorMessage } from "@/lib/utils/apiError";

/** Formats Python source on the server; nothing is saved or executed. */
export type PythonFormatter = (source: string) => Promise<FormatSourceResponse>;

/**
 * The outcome of formatting an editor's text. `text` is the text the editor holds afterwards:
 * the formatted source, or the source unchanged when it was not formatted. `stale` means the
 * text changed while the formatter ran, so the result was dropped.
 */
export type FormatRun =
  | { status: "formatted" | "unchanged"; text: string }
  | {
      status: "syntax_error";
      text: string;
      message: string;
      line: number | null;
      column: number | null;
    }
  | { status: "failed"; text: string; error: unknown }
  | { status: "unavailable"; text: string }
  | { status: "stale"; text: null };

export const FORMAT_DOCUMENT_ACTION = "editor.action.formatDocument";

interface Disposable {
  dispose: () => void;
}

interface TextModelLike {
  uri: { toString: () => string };
  getValue: () => string;
  getVersionId: () => number;
  isDisposed: () => boolean;
  getFullModelRange: () => unknown;
}

interface CancellationTokenLike {
  isCancellationRequested: boolean;
}

interface FormattingProvider {
  displayName?: string;
  provideDocumentFormattingEdits: (
    model: TextModelLike,
    options: unknown,
    token: CancellationTokenLike,
  ) => Promise<Array<{ range: unknown; text: string }>>;
}

export interface FormatterMonaco {
  languages?: {
    registerDocumentFormattingEditProvider?: (
      languageSelector: string,
      provider: FormattingProvider,
    ) => Disposable;
  };
}

export interface FormatterEditor {
  getModel?: () => TextModelLike | null;
  onDidChangeModel?: (listener: () => void) => Disposable;
  onDidDispose?: (listener: () => void) => Disposable | void;
  getAction?: (id: string) => { run: () => Promise<void>; isSupported?: () => boolean } | null;
}

interface Attachment {
  format: PythonFormatter;
  onRun?: (run: FormatRun) => void;
  /** Runs started by `formatEditorDocument`, whose caller reports the outcome. */
  quiet: number;
  last: FormatRun | undefined;
}

interface Registry {
  attachments: Map<string, Attachment>;
  provider: Disposable | null;
}

const registries = new WeakMap<object, Registry>();
const editorAttachments = new WeakMap<object, Attachment>();

function runOf(source: string, response: FormatSourceResponse): FormatRun {
  if (response.status === "syntax_error") {
    return {
      status: "syntax_error",
      text: source,
      message: response.diagnostic?.message ?? "The source cannot be parsed",
      line: response.diagnostic?.line ?? null,
      column: response.diagnostic?.column ?? null,
    };
  }
  return { status: response.status, text: response.source };
}

function providerFor(registry: Registry): FormattingProvider {
  return {
    displayName: "Ruff",
    provideDocumentFormattingEdits: async (model, _options, token) => {
      const attachment = registry.attachments.get(model.uri.toString());
      if (!attachment) return [];
      const source = model.getValue();
      const version = model.getVersionId();
      let run: FormatRun;
      try {
        run = runOf(source, await attachment.format(source));
      } catch (error) {
        run = { status: "failed", text: source, error };
      }
      if (token.isCancellationRequested || model.isDisposed() || model.getVersionId() !== version) {
        run = { status: "stale", text: null };
      }
      attachment.last = run;
      if (attachment.quiet === 0) attachment.onRun?.(run);
      return run.status === "formatted"
        ? [{ range: model.getFullModelRange(), text: run.text }]
        : [];
    },
  };
}

/**
 * Format `editor`'s Python text with `format` when Monaco's Format Document runs. Explicit runs
 * report to `onRun`; runs started by `formatEditorDocument` report to its caller instead.
 * The attachment follows the editor's model and ends when the editor is disposed or the
 * returned handle is disposed; the shared provider goes away with the last attachment.
 */
export function attachPythonFormatter(
  monaco: FormatterMonaco,
  editor: FormatterEditor,
  options: { format: PythonFormatter; onRun?: (run: FormatRun) => void },
): Disposable {
  const register = monaco.languages?.registerDocumentFormattingEditProvider;
  if (typeof register !== "function" || typeof editor.getModel !== "function") {
    return { dispose: () => undefined };
  }
  let registry = registries.get(monaco);
  if (!registry) {
    registry = { attachments: new Map(), provider: null };
    registries.set(monaco, registry);
  }
  const shared = registry;
  const attachment: Attachment = { ...options, quiet: 0, last: undefined };
  editorAttachments.set(editor, attachment);
  let key: string | null = null;

  const release = () => {
    if (key !== null && shared.attachments.get(key) === attachment) shared.attachments.delete(key);
    key = null;
  };
  const bind = () => {
    release();
    const model = editor.getModel?.();
    if (model) {
      key = model.uri.toString();
      shared.attachments.set(key, attachment);
    }
  };
  bind();
  if (!shared.provider) {
    shared.provider = register.call(monaco.languages, "python", providerFor(shared));
  }

  const modelListener = editor.onDidChangeModel?.(bind);
  let disposed = false;
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    modelListener?.dispose();
    release();
    if (editorAttachments.get(editor) === attachment) editorAttachments.delete(editor);
    if (shared.attachments.size === 0 && shared.provider) {
      shared.provider.dispose();
      shared.provider = null;
    }
  };
  editor.onDidDispose?.(dispose);
  return { dispose };
}

/**
 * Run Format Document on `editor` and report the outcome without notifying `onRun`. The
 * formatted text is applied as an undoable edit. `fallback` is the text to report when the
 * editor cannot be formatted (no formatter attached, read-only, or no model).
 */
export async function formatEditorDocument(
  editor: FormatterEditor | null | undefined,
  fallback: string,
): Promise<FormatRun> {
  const attachment = editor ? editorAttachments.get(editor) : undefined;
  const model = attachment ? editor?.getModel?.() : null;
  if (!editor || !attachment || !model) return { status: "unavailable", text: fallback };
  const action = editor.getAction?.(FORMAT_DOCUMENT_ACTION);
  if (!action || action.isSupported?.() === false) {
    return { status: "unavailable", text: model.getValue() };
  }
  const before = model.getValue();
  attachment.last = undefined;
  attachment.quiet += 1;
  try {
    await action.run();
  } finally {
    attachment.quiet -= 1;
  }
  // Set by the provider during the run; the cast undoes the narrowing from the reset above.
  const recorded = attachment.last as FormatRun | undefined;
  const run: FormatRun = recorded ?? { status: "unavailable", text: before };
  attachment.last = undefined;
  if (run.status === "stale" || model.isDisposed()) return { status: "stale", text: null };
  // The editor must hold exactly the text reported, or a later edit would be lost.
  if (model.getValue() !== run.text) return { status: "stale", text: null };
  return run;
}

/** A sentence for a run that left the text unformatted, or null when it formatted. */
export function describeFormatProblem(run: FormatRun): string | null {
  switch (run.status) {
    case "syntax_error": {
      const where =
        run.line !== null ? `Line ${run.line}${run.column !== null ? `:${run.column}` : ""}: ` : "";
      return `${where}${run.message}`;
    }
    case "failed":
      return getApiErrorMessage(run.error, "The formatter could not be reached");
    case "unavailable":
      return "Formatting is not available in this editor";
    case "stale":
      return "The text changed while it was being formatted";
    default:
      return null;
  }
}
