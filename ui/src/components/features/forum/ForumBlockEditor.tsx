"use client";

import { useEffect, useState } from "react";

import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";

import { uploadInlineFile } from "@/lib/blocknote/inlineFileUpload";

// Reuse the cryo BlockNote theme (scoped to the `.wiring-blocknote` wrapper).
import "../cryo/blocknote-theme.css";

function useThemeScheme(): "light" | "dark" {
  const [scheme, setScheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    const compute = () => {
      const t = document.documentElement.getAttribute("data-theme")?.toLowerCase() ?? "";
      const dark = ["dark", "night", "dracula", "dim", "abyss", "dev-dark"];
      setScheme(dark.includes(t) ? "dark" : "light");
    };
    compute();
    const obs = new MutationObserver(compute);
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => obs.disconnect();
  }, []);
  return scheme;
}

interface ForumBlockEditorProps {
  /** Current document, as opaque BlockNote JSON objects. */
  initialBlocks?: Record<string, unknown>[];
  /** Markdown to import on first mount when no blocks are present (legacy posts). */
  legacyMarkdown?: string;
  /** Upload handler returning a persistent server URL for the stored image. */
  onImageUpload: (file: File) => Promise<string>;
  /** Called whenever the document changes, with both the block JSON and a lossy markdown export. */
  onChange: (blocks: Record<string, unknown>[], markdown: string) => void;
  editable?: boolean;
}

/**
 * Forum rich-text editor built on BlockNote.
 *
 * Mirrors the cryo `WiringBlockEditor` (JSON source of truth + lossy markdown
 * projection). Images are stored as server URLs via `onImageUpload` — forum
 * documents stay small and the image blocks keep a portable `url`. Video,
 * audio, and generic file blocks are inlined as base64 data URLs (capped at
 * 5 MB) just like the cool-down editor, since the forum image endpoint only
 * accepts images.
 */
export function ForumBlockEditor({
  initialBlocks,
  legacyMarkdown,
  onImageUpload,
  onChange,
  editable = true,
}: ForumBlockEditorProps) {
  const colorScheme = useThemeScheme();
  const editor = useCreateBlockNote({
    // Use the full default schema — image, video, audio, file, table, list,
    // code, quote, heading, …
    initialContent:
      initialBlocks && initialBlocks.length > 0
        ? // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (initialBlocks as any)
        : undefined,
    // Images go to the server (portable url, small documents); video / audio /
    // file are inlined as base64 data URLs, matching the cool-down editor.
    uploadFile: (file: File) =>
      file.type.startsWith("image/") ? onImageUpload(file) : uploadInlineFile(file),
  });

  // First-time migration: import legacy markdown when a post has no blocks yet.
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
    <div className="wiring-blocknote">
      <BlockNoteView
        editor={editor}
        editable={editable}
        theme={colorScheme}
        onChange={() => {
          const blocks = editor.document as unknown as Record<string, unknown>[];
          void Promise.resolve(editor.blocksToMarkdownLossy(editor.document)).then((md) =>
            onChange(blocks, md),
          );
        }}
      />
    </div>
  );
}
