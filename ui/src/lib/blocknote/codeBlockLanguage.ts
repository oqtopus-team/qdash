import { useEffect } from "react";

import { blockNoteSchema } from "./codeBlock";
import { detectCodeLanguage } from "./detectCodeLanguage";

type QDashEditor = (typeof blockNoteSchema)["BlockNoteEditor"];

type BlockRecord = Record<string, unknown>;

function inlineText(node: unknown): string {
  if (Array.isArray(node)) return node.map(inlineText).join("");
  if (node === null || typeof node !== "object") return "";
  const obj = node as BlockRecord;
  if (typeof obj.text === "string") return obj.text;
  return inlineText(obj.content);
}

function isAutoLanguage(language: unknown): boolean {
  return language === undefined || language === "text";
}

function detectBlockLanguage(block: BlockRecord): string | null {
  if (block.type !== "codeBlock") return null;
  const props = (block.props ?? {}) as BlockRecord;
  if (!isAutoLanguage(props.language)) return null;
  return detectCodeLanguage(inlineText(block.content));
}

function withDetectedLanguage(block: BlockRecord): BlockRecord {
  const children = block.children;
  const next: BlockRecord = Array.isArray(children)
    ? { ...block, children: withDetectedCodeLanguages(children as BlockRecord[]) }
    : { ...block };

  const detected = detectBlockLanguage(next);
  if (!detected) return next;

  const props = (next.props ?? {}) as BlockRecord;
  return { ...next, props: { ...props, language: detected } };
}

/** Returns a copy of `blocks` with languages detected for plain-text code blocks. */
export function withDetectedCodeLanguages(blocks: BlockRecord[]): BlockRecord[] {
  return blocks.map(withDetectedLanguage);
}

/** Walks `blocks` recursively and returns the detected language for each auto code block. */
export function collectCodeLanguageUpdates(
  blocks: BlockRecord[],
): { id: string; language: string }[] {
  const updates: { id: string; language: string }[] = [];

  const visit = (block: BlockRecord) => {
    const detected = detectBlockLanguage(block);
    if (detected) {
      updates.push({ id: block.id as string, language: detected });
    }
    const children = block.children;
    if (Array.isArray(children)) {
      (children as BlockRecord[]).forEach(visit);
    }
  };

  blocks.forEach(visit);
  return updates;
}

const DETECTION_DEBOUNCE_MS = 500;

/** Detects and applies languages for auto code blocks as the editor's content changes. */
export function useCodeBlockLanguageDetection(editor: QDashEditor): void {
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;

    const unsubscribe = editor.onChange(() => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        const updates = collectCodeLanguageUpdates(editor.document as unknown as BlockRecord[]);
        for (const { id, language } of updates) {
          editor.updateBlock(id, { type: "codeBlock", props: { language } });
        }
      }, DETECTION_DEBOUNCE_MS);
    });

    return () => {
      if (timer) clearTimeout(timer);
      unsubscribe();
    };
  }, [editor]);
}
