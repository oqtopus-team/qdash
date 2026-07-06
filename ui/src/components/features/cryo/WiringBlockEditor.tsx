"use client";

import { useEffect } from "react";

import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";

import { uploadInlineFile } from "@/lib/blocknote/inlineFileUpload";

import "./blocknote-theme.css";

interface WiringBlockEditorProps {
  /** Current document, as opaque BlockNote JSON objects. */
  initialBlocks: Record<string, unknown>[] | undefined;
  /** Markdown to import on first mount when no blocks are present (migration). */
  legacyMarkdown?: string;
  editable: boolean;
  /** Called whenever the document changes. */
  onChange?: (blocks: Record<string, unknown>[], markdown: string) => void;
  /** BlockNote color scheme — match the page theme. */
  colorScheme: "light" | "dark";
}

export function WiringBlockEditor({
  initialBlocks,
  legacyMarkdown,
  editable,
  onChange,
  colorScheme,
}: WiringBlockEditorProps) {
  const editor = useCreateBlockNote({
    // Use the full default schema — image, file, video, audio, table,
    // toggle, checklist, code, quote, divider, headings.
    initialContent:
      initialBlocks && initialBlocks.length > 0
        ? // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (initialBlocks as any)
        : undefined,
    // Inline base64 upload — keeps everything in the cool-down document.
    uploadFile: uploadInlineFile,
  });

  // First-time migration: if no blocks but legacy markdown exists, import it.
  useEffect(() => {
    if (!editable) return;
    if (initialBlocks && initialBlocks.length > 0) return;
    if (!legacyMarkdown || !legacyMarkdown.trim()) return;
    let cancelled = false;
    void (async () => {
      const blocks = await editor.tryParseMarkdownToBlocks(legacyMarkdown);
      if (!cancelled && blocks.length > 0) {
        editor.replaceBlocks(editor.document, blocks);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editor]);

  return (
    <BlockNoteView
      editor={editor}
      editable={editable}
      theme={colorScheme}
      onChange={
        onChange
          ? () => {
              const blocks = editor.document as unknown as Record<string, unknown>[];
              void Promise.resolve(editor.blocksToMarkdownLossy(editor.document)).then((md) =>
                onChange(blocks, md),
              );
            }
          : undefined
      }
    />
  );
}
