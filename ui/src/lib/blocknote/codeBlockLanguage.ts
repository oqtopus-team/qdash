import { useEffect } from "react";

import { blockNoteSchema } from "./codeBlock";
import { detectCodeLanguage } from "./detectCodeLanguage";

type QDashEditor = (typeof blockNoteSchema)["BlockNoteEditor"];

type BlockRecord = Record<string, unknown>;

/** Returns the concatenated plain text of an inline content node or list. */
function inlineText(node: unknown): string {
  if (Array.isArray(node)) return node.map(inlineText).join("");
  if (node === null || typeof node !== "object") return "";
  const obj = node as BlockRecord;
  if (typeof obj.text === "string") return obj.text;
  return inlineText(obj.content);
}

/** Returns whether `language` means auto-detect (unset or `"text"`), as opposed to an explicit choice such as `"txt"` (Plain Text). */
function isAutoLanguage(language: unknown): boolean {
  return !language || language === "text";
}

/** Returns the detected language for an auto code block's content, or `null` if the block is not a code block, is not auto, or detection is unsure. */
function detectBlockLanguage(block: BlockRecord): string | null {
  if (block.type !== "codeBlock") return null;
  const props = (block.props ?? {}) as BlockRecord;
  if (!isAutoLanguage(props.language)) return null;
  return detectCodeLanguage(inlineText(block.content));
}

/** Returns a copy of `block`, and its children, with the language detected if it is an auto code block. */
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

/** Returns a copy of `blocks` with languages detected for auto code blocks. */
export function withDetectedCodeLanguages(blocks: BlockRecord[]): BlockRecord[] {
  return blocks.map(withDetectedLanguage);
}

type BlockChangeRecord = {
  type: "insert" | "delete" | "update" | "move";
  block: BlockRecord;
  prevBlock?: BlockRecord;
};

/** Returns the ids of code blocks inserted, or updated with changed text, by `changes`. */
export function changedCodeBlockIds(changes: BlockChangeRecord[]): string[] {
  const ids: string[] = [];

  for (const change of changes) {
    if (change.block.type !== "codeBlock") continue;

    if (change.type === "insert") {
      ids.push(change.block.id as string);
    } else if (change.type === "update" && change.prevBlock) {
      if (inlineText(change.block.content) !== inlineText(change.prevBlock.content)) {
        ids.push(change.block.id as string);
      }
    }
  }

  return ids;
}

const DETECTION_DEBOUNCE_MS = 500;

/** Detects and applies languages for auto code blocks whose text content changes. */
export function useCodeBlockLanguageDetection(editor: QDashEditor): void {
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const pendingIds = new Set<string>();

    const unsubscribe = editor.onChange((_editor, context) => {
      const changedIds = changedCodeBlockIds(
        context.getChanges() as unknown as BlockChangeRecord[],
      );
      if (changedIds.length === 0) return;
      for (const id of changedIds) pendingIds.add(id);

      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        const ids = [...pendingIds];
        pendingIds.clear();
        for (const id of ids) {
          const block = editor.getBlock(id) as BlockRecord | undefined;
          if (!block) continue;
          const detected = detectBlockLanguage(block);
          if (detected) {
            editor.updateBlock(id, { type: "codeBlock", props: { language: detected } });
          }
        }
      }, DETECTION_DEBOUNCE_MS);
    });

    return () => {
      if (timer) clearTimeout(timer);
      unsubscribe();
    };
  }, [editor]);
}
