import { blockNoteSchema } from "./codeBlock";
import { detectCodeLanguage } from "./detectCodeLanguage";

type QDashEditor = (typeof blockNoteSchema)["BlockNoteEditor"];
type QDashBlock = (typeof blockNoteSchema)["Block"];

type BlockRecord = Record<string, unknown>;

function inlineText(node: unknown): string {
  if (Array.isArray(node)) return node.map(inlineText).join("");
  if (node === null || typeof node !== "object") return "";
  const obj = node as BlockRecord;
  if (typeof obj.text === "string") return obj.text;
  return inlineText(obj.content);
}

function isEmptyCodeBlock(block: QDashBlock): boolean {
  return block.type === "codeBlock" && inlineText(block.content).trim() === "";
}

/** Sets the language of an empty code block from the pasted text. */
export function codeBlockPasteHandler({
  event,
  editor,
  defaultPasteHandler,
}: {
  event: ClipboardEvent;
  editor: QDashEditor;
  defaultPasteHandler: (context?: {
    prioritizeMarkdownOverHTML?: boolean;
    plainTextAsMarkdown?: boolean;
  }) => boolean | undefined;
}): boolean | undefined {
  const { block } = editor.getTextCursorPosition();
  const wasEmptyCodeBlock = isEmptyCodeBlock(block);

  const handled = defaultPasteHandler();

  if (wasEmptyCodeBlock) {
    const text = event.clipboardData?.getData("text/plain");
    const language = text ? detectCodeLanguage(text) : null;
    if (language) {
      editor.updateBlock(block.id, { type: "codeBlock", props: { language } });
    }
  }

  return handled;
}

function withDetectedLanguage(block: BlockRecord): BlockRecord {
  const children = block.children;
  const next: BlockRecord = Array.isArray(children)
    ? { ...block, children: withDetectedCodeLanguages(children as BlockRecord[]) }
    : { ...block };

  if (next.type !== "codeBlock") return next;

  const props = (next.props ?? {}) as BlockRecord;
  const language = props.language;
  if (language !== undefined && language !== "text") return next;

  const detected = detectCodeLanguage(inlineText(next.content));
  if (!detected) return next;

  return { ...next, props: { ...props, language: detected } };
}

/** Returns a copy of `blocks` with languages detected for plain-text code blocks. */
export function withDetectedCodeLanguages(blocks: BlockRecord[]): BlockRecord[] {
  return blocks.map(withDetectedLanguage);
}
