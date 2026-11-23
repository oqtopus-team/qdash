import { FORMAT_DOCUMENT_ACTION, type FormatterMonaco } from "@/lib/pythonFormatter";

type Register = NonNullable<
  NonNullable<FormatterMonaco["languages"]>["registerDocumentFormattingEditProvider"]
>;

interface ProviderEntry {
  selector: string;
  provider: Parameters<Register>[1];
  disposed: boolean;
}

/** A Monaco stand-in with a formatting provider registry. */
export function createFakeMonaco() {
  const providers: ProviderEntry[] = [];
  const monaco: FormatterMonaco = {
    languages: {
      registerDocumentFormattingEditProvider: (selector, provider) => {
        const entry = { selector, provider, disposed: false };
        providers.push(entry);
        return { dispose: () => void (entry.disposed = true) };
      },
    },
  };
  const active = () => providers.filter((entry) => !entry.disposed);
  return { monaco, providers, active };
}

let modelCount = 0;

/**
 * An editor stand-in. Its Format Document asks the registered provider and applies the edits
 * as one undoable edit, as Monaco does; `type` is a user edit and `undo` reverts the last
 * undoable edit. `onChange` receives every change of the text, like the editor's onChange.
 */
export function createFakeEditor(
  fake: ReturnType<typeof createFakeMonaco>,
  initial: string,
  options: { onChange?: (text: string) => void; writable?: boolean } = {},
) {
  let value = initial;
  let version = 1;
  let disposed = false;
  const undoStack: string[] = [];
  const disposeListeners: Array<() => void> = [];
  const modelListeners: Array<() => void> = [];
  const makeModel = () => {
    modelCount += 1;
    const uri = `inmemory://model/${modelCount}`;
    return {
      uri: { toString: () => uri },
      getValue: () => value,
      getVersionId: () => version,
      isDisposed: () => disposed,
      getFullModelRange: () => ({ full: true }),
    };
  };
  let model = makeModel();
  const setText = (text: string, undoable: boolean) => {
    if (undoable) undoStack.push(value);
    value = text;
    version += 1;
    options.onChange?.(text);
  };
  const editor = {
    getModel: () => model,
    onDidChangeModel: (listener: () => void) => {
      modelListeners.push(listener);
      return { dispose: () => undefined };
    },
    onDidDispose: (listener: () => void) => {
      disposeListeners.push(listener);
      return { dispose: () => undefined };
    },
    getAction: (id: string) =>
      id === FORMAT_DOCUMENT_ACTION
        ? {
            isSupported: () => options.writable !== false,
            run: async () => {
              const [entry] = fake.active();
              if (!entry) return;
              const before = version;
              const edits = await entry.provider.provideDocumentFormattingEdits(
                model,
                {},
                { isCancellationRequested: version !== before },
              );
              // Monaco drops edits computed for an older text.
              if (version !== before) return;
              for (const edit of edits) setText(edit.text, true);
            },
          }
        : null,
    type: (text: string) => setText(text, false),
    undo: () => {
      const previous = undoStack.pop();
      if (previous !== undefined) setText(previous, false);
    },
    swapModel: () => {
      model = makeModel();
      modelListeners.forEach((listener) => listener());
    },
    dispose: () => {
      disposed = true;
      disposeListeners.forEach((listener) => listener());
    },
  };
  return editor;
}

/** A promise with its resolve function, to answer a request after the test acts. */
export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
