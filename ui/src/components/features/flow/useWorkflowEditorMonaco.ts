import type { EditorProps, Monaco, OnMount } from "@monaco-editor/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Pane } from "@/components/features/flow/useWorkflowEditorPanes";
import { formatFlowSource } from "@/client/flow/flow";
import { monoFontFamily, remeasureMonacoFontsWhenLoaded } from "@/lib/fonts";
import { attachPythonFormatter, type FormatRun } from "@/lib/pythonFormatter";

/** A mounted Monaco code editor. */
export type MonacoEditor = Parameters<OnMount>[0];

export type WordWrap = "on" | "off";

const DEFAULT_FONT_SIZE = 14;
const MIN_FONT_SIZE = 8;
const MAX_FONT_SIZE = 32;
const FONT_SIZE_STEP = 2;

export const EDITOR_OPTIONS = {
  minimap: { enabled: true, renderCharacters: false, maxColumn: 80, scale: 2 },
  fontSize: DEFAULT_FONT_SIZE,
  fontFamily: monoFontFamily,
  fontLigatures: true,
  lineNumbers: "on" as const,
  automaticLayout: true,
  scrollBeyondLastLine: true,
  padding: { top: 16, bottom: 16 },
  wordWrap: "on" as const,
  folding: true,
  foldingHighlight: true,
  renderLineHighlight: "all" as const,
  cursorStyle: "line" as const,
  cursorBlinking: "smooth" as const,
  cursorSmoothCaretAnimation: "on" as const,
  smoothScrolling: true,
  bracketPairColorization: { enabled: true },
  guides: {
    bracketPairs: true,
    indentation: true,
    highlightActiveIndentation: true,
  },
  renderWhitespace: "selection" as const,
  stickyScroll: { enabled: true },
  suggest: { showKeywords: true, showSnippets: true },
  quickSuggestions: { other: true, comments: false, strings: false },
  parameterHints: { enabled: true },
  matchBrackets: "always" as const,
  occurrencesHighlight: "singleFile" as const,
  selectionHighlight: true,
  linkedEditing: true,
  colorDecorators: true,
  scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10 },
} satisfies NonNullable<EditorProps["options"]>;

interface UseWorkflowEditorMonacoOptions {
  /** The pane whose editor the status bar follows and editor commands act on. */
  currentPane: Pane;
  /** Saves a pane's workflow; Cmd/Ctrl+S calls it for the pane it was pressed in. */
  onSave: (pane: Pane) => void;
  /** Reports a Format Document run started from the palette, the context menu or Shift+Alt+F. */
  onFormatRun: (run: FormatRun) => void;
}

/**
 * One Monaco editor per pane: mounting wires the Python formatter, the status bar's cursor and
 * selection, and the editor keybindings, and zoom and word wrap apply to both editors.
 */
export function useWorkflowEditorMonaco({
  currentPane,
  onSave,
  onFormatRun,
}: UseWorkflowEditorMonacoOptions) {
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });
  const [selection, setSelection] = useState({ lines: 0, chars: 0 });
  const [fontSize, setFontSize] = useState(DEFAULT_FONT_SIZE);
  const [wordWrap, setWordWrap] = useState<WordWrap>("on");
  const editorRefs = useRef<Record<Pane, MonacoEditor | null>>({
    primary: null,
    secondary: null,
  });
  const monacoRef = useRef<Monaco | null>(null);

  // Editor commands registered at mount call the latest callbacks (avoids stale closures).
  const onSaveRef = useRef(onSave);
  const onFormatRunRef = useRef(onFormatRun);
  useEffect(() => {
    onSaveRef.current = onSave;
    onFormatRunRef.current = onFormatRun;
  });

  const zoomIn = useCallback(
    () => setFontSize((prev) => Math.min(prev + FONT_SIZE_STEP, MAX_FONT_SIZE)),
    [],
  );
  const zoomOut = useCallback(
    () => setFontSize((prev) => Math.max(prev - FONT_SIZE_STEP, MIN_FONT_SIZE)),
    [],
  );
  const resetZoom = useCallback(() => setFontSize(DEFAULT_FONT_SIZE), []);
  const toggleWordWrap = useCallback(
    () => setWordWrap((prev) => (prev === "on" ? "off" : "on")),
    [],
  );

  // Sync fontSize and wordWrap to both editors
  useEffect(() => {
    for (const editor of Object.values(editorRefs.current)) {
      editor?.updateOptions({ fontSize, wordWrap });
    }
  }, [fontSize, wordWrap]);

  // The status bar follows the active pane's cursor.
  const activePaneRef = useRef<Pane>(currentPane);
  useEffect(() => {
    activePaneRef.current = currentPane;
    const position = editorRefs.current[currentPane]?.getPosition?.();
    setCursorPosition(
      position ? { line: position.lineNumber, column: position.column } : { line: 1, column: 1 },
    );
    setSelection({ lines: 0, chars: 0 });
  }, [currentPane]);

  const mountEditor = useCallback(
    (pane: Pane, editor: MonacoEditor, monaco: Monaco) => {
      editorRefs.current[pane] = editor;
      monacoRef.current = monaco;
      // A pane that opens another workflow remounts its editor; forget the disposed one.
      editor.onDidDispose(() => {
        if (editorRefs.current[pane] === editor) editorRefs.current[pane] = null;
      });
      remeasureMonacoFontsWhenLoaded(monaco);
      // Format Document formats with the project's Ruff settings; detached when the editor goes.
      attachPythonFormatter(monaco, editor, {
        format: async (source) => (await formatFlowSource({ source })).data,
        onRun: (run) => onFormatRunRef.current(run),
      });
      editor.onDidChangeCursorPosition((e) => {
        if (activePaneRef.current !== pane) return;
        setCursorPosition({
          line: e.position.lineNumber,
          column: e.position.column,
        });
      });
      editor.onDidChangeCursorSelection((e) => {
        if (activePaneRef.current !== pane) return;
        const sel = e.selection;
        if (sel.startLineNumber === sel.endLineNumber && sel.startColumn === sel.endColumn) {
          setSelection({ lines: 0, chars: 0 });
        } else {
          const model = editor.getModel();
          if (model) {
            const text = model.getValueInRange(sel);
            const lines = sel.endLineNumber - sel.startLineNumber + 1;
            setSelection({ lines, chars: text.length });
          }
        }
      });
      // Cmd/Ctrl+S saves the workflow of the pane it was pressed in.
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => onSaveRef.current(pane));
      // Alt+Z → toggle word wrap
      editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.KeyZ, toggleWordWrap);
    },
    [toggleWordWrap],
  );

  // Each pane's editor reports to its own pane.
  const handleMount = useMemo<Record<Pane, OnMount>>(
    () => ({
      primary: (editor, monaco) => mountEditor("primary", editor, monaco),
      secondary: (editor, monaco) => mountEditor("secondary", editor, monaco),
    }),
    [mountEditor],
  );

  /** The mounted editor of a pane, or null while it has none. */
  const editorFor = (pane: Pane) => editorRefs.current[pane];

  /** Focuses the active pane's editor and runs one of its actions, such as Go to Line. */
  const runActiveEditorAction = (actionId: string) => {
    const editor = editorRefs.current[currentPane];
    editor?.focus();
    void editor?.getAction(actionId)?.run();
  };

  const toggleMinimap = () => {
    const editor = editorRefs.current[currentPane];
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;
    const current = editor.getOption(monaco.editor.EditorOption.minimap);
    editor.updateOptions({ minimap: { enabled: !current?.enabled } });
  };

  return {
    cursorPosition,
    selection,
    fontSize,
    wordWrap,
    isZoomed: fontSize !== DEFAULT_FONT_SIZE,
    zoomPercent: Math.round((fontSize / DEFAULT_FONT_SIZE) * 100),
    zoomIn,
    zoomOut,
    resetZoom,
    toggleWordWrap,
    handleMount,
    editorFor,
    runActiveEditorAction,
    toggleMinimap,
  };
}
