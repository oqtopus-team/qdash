"use client";

import { useCallback, useEffect, useState, type MutableRefObject } from "react";

import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";
import {
  SuggestionMenuController,
  useCreateBlockNote,
  type DefaultReactSuggestionItem,
} from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";

import { DARK_THEMES, type ThemeName } from "@/constants/themes";
import { uploadInlineFile } from "@/lib/blocknote/inlineFileUpload";

// Reuse the cryo BlockNote theme (scoped to the `.wiring-blocknote` wrapper).
import "../cryo/blocknote-theme.css";

function useThemeScheme(): "light" | "dark" {
  const [scheme, setScheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    const compute = () => {
      const t = document.documentElement.getAttribute("data-theme")?.toLowerCase() ?? "";
      setScheme(DARK_THEMES.includes(t as ThemeName) ? "dark" : "light");
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

function cloneBlocks(blocks: Record<string, unknown>[]): Record<string, unknown>[] {
  if (typeof structuredClone === "function") {
    return structuredClone(blocks);
  }
  return JSON.parse(JSON.stringify(blocks)) as Record<string, unknown>[];
}

export type ForumBlockSnapshot = {
  blocks: Record<string, unknown>[];
  markdown: string;
};

export type ForumBlockSnapshotGetter = () => Promise<ForumBlockSnapshot>;

export type ForumMentionCandidate = {
  id: string;
  label: string;
  secondaryLabel?: string;
};

export function filterForumMentionCandidates(
  candidates: ForumMentionCandidate[],
  query: string,
): ForumMentionCandidate[] {
  const normalizedQuery = query.toLowerCase();
  return candidates.filter(
    (candidate) =>
      candidate.id.toLowerCase().includes(normalizedQuery) ||
      candidate.label.toLowerCase().includes(normalizedQuery) ||
      candidate.secondaryLabel?.toLowerCase().includes(normalizedQuery),
  );
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
  /** Imperative snapshot used by external Save buttons to avoid stale React state. */
  snapshotRef?: MutableRefObject<ForumBlockSnapshotGetter | null>;
  mentionCandidates?: ForumMentionCandidate[];
  editable?: boolean;
}

export function ForumBlockViewer({ blocks }: { blocks: Record<string, unknown>[] }) {
  const colorScheme = useThemeScheme();
  const editor = useCreateBlockNote(
    {
      // Use the same full schema as the editor so tables and other rich blocks
      // render consistently in forum previews.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      initialContent: blocks.length > 0 ? (blocks as any) : undefined,
    },
    [blocks],
  );

  return (
    <div className="forum-blocknote wiring-blocknote">
      <BlockNoteView editor={editor} editable={false} theme={colorScheme} />
    </div>
  );
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
  snapshotRef,
  mentionCandidates = [],
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
  const getMentionItems = useCallback(
    async (query: string): Promise<DefaultReactSuggestionItem[]> =>
      filterForumMentionCandidates(mentionCandidates, query).map((candidate) => ({
        title: candidate.label,
        subtext: candidate.secondaryLabel
          ? `@${candidate.id} · ${candidate.secondaryLabel}`
          : `@${candidate.id}`,
        onItemClick: () =>
          editor.insertInlineContent([
            {
              type: "text",
              text: `@${candidate.id}`,
              styles: { bold: true, textColor: "blue", backgroundColor: "blue" },
            },
            { type: "text", text: " ", styles: {} },
          ]),
      })),
    [editor, mentionCandidates],
  );

  useEffect(() => {
    if (!snapshotRef) return;
    snapshotRef.current = async () => ({
      blocks: cloneBlocks(editor.document as unknown as Record<string, unknown>[]),
      markdown: await editor.blocksToMarkdownLossy(editor.document),
    });
    return () => {
      snapshotRef.current = null;
    };
  }, [editor, snapshotRef]);

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
    <div className="forum-blocknote wiring-blocknote">
      <BlockNoteView
        editor={editor}
        editable={editable}
        theme={colorScheme}
        onChange={() => {
          const blocks = cloneBlocks(editor.document as unknown as Record<string, unknown>[]);
          void Promise.resolve(editor.blocksToMarkdownLossy(editor.document)).then((md) =>
            onChange(blocks, md),
          );
        }}
      >
        {editable && mentionCandidates.length > 0 && (
          <SuggestionMenuController triggerCharacter="@" getItems={getMentionItems} />
        )}
      </BlockNoteView>
    </div>
  );
}
