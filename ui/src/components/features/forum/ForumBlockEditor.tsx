"use client";

import Image from "next/image";
import { useEffect, useState, type MutableRefObject } from "react";

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
  editable?: boolean;
}

type ForumBlock = Record<string, unknown> & {
  type?: string;
  props?: Record<string, unknown>;
  content?: unknown;
  children?: ForumBlock[];
};

function textFromInlineContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object" && "text" in item) {
        const text = (item as { text?: unknown }).text;
        return typeof text === "string" ? text : "";
      }
      return "";
    })
    .join("");
}

function renderViewerBlock(block: ForumBlock, index: number) {
  const props = block.props ?? {};
  const text = textFromInlineContent(block.content);
  const children = Array.isArray(block.children) ? block.children : [];

  if (block.type === "image") {
    const url = typeof props.url === "string" ? props.url : "";
    const caption = typeof props.caption === "string" ? props.caption : "";
    const width = typeof props.previewWidth === "number" ? props.previewWidth : undefined;
    if (!url) return null;
    return (
      <figure key={String(block.id ?? index)} className="my-3">
        <Image
          src={url}
          alt={typeof props.name === "string" ? props.name : caption}
          width={width ?? 800}
          height={450}
          unoptimized
          style={
            width
              ? { width, maxWidth: "100%", height: "auto" }
              : { maxWidth: "100%", height: "auto" }
          }
          className="rounded border border-base-300"
        />
        {caption && (
          <figcaption className="mt-1 text-xs text-base-content/50">{caption}</figcaption>
        )}
      </figure>
    );
  }

  const key = String(block.id ?? index);
  if (block.type === "heading") {
    const level = props.level === 1 || props.level === 2 || props.level === 3 ? props.level : 3;
    const className = level === 1 ? "text-xl" : level === 2 ? "text-lg" : "text-base";
    return (
      <h3 key={key} className={`my-2 font-semibold ${className}`}>
        {text}
      </h3>
    );
  }
  if (block.type === "bulletListItem") {
    return (
      <li key={key} className="ml-5 list-disc">
        {text}
      </li>
    );
  }
  if (block.type === "numberedListItem") {
    return (
      <li key={key} className="ml-5 list-decimal">
        {text}
      </li>
    );
  }
  if (block.type === "quote") {
    return (
      <blockquote key={key} className="my-2 border-l-2 border-base-300 pl-3 text-base-content/70">
        {text}
      </blockquote>
    );
  }
  if (block.type === "codeBlock") {
    return (
      <pre key={key} className="my-2 overflow-x-auto rounded bg-base-200 p-3 text-xs">
        <code>{text}</code>
      </pre>
    );
  }

  return (
    <div key={key} className="my-1">
      {text && <p>{text}</p>}
      {children.length > 0 && <div className="ml-4">{children.map(renderViewerBlock)}</div>}
    </div>
  );
}

export function ForumBlockViewer({ blocks }: { blocks: Record<string, unknown>[] }) {
  return (
    <div className="text-sm leading-6 text-base-content/80">
      {(blocks as ForumBlock[]).map(renderViewerBlock)}
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
    <div className="wiring-blocknote">
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
      />
    </div>
  );
}
