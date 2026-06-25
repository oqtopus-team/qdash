"use client";

import { useCallback } from "react";

import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Image from "@tiptap/extension-image";
import { TableKit } from "@tiptap/extension-table";

import "./tiptap-demo.css";

const SAMPLE_HTML = `
<h1>Tiptap デモ</h1>
<p>これは <strong>Tiptap</strong> エディタです。ツールバーのボタンは<strong>すべて自前実装</strong>です（ヘッドレスなので標準 UI が無い）。</p>
<table>
  <tr><th>機能</th><th>このデモでの状態</th></tr>
  <tr><td>テーブル</td><td>拡張 + 自前 CSS で実現</td></tr>
  <tr><td>画像リサイズ</td><td>ハンドル無し（標準では非対応）</td></tr>
</table>
<p>スラッシュメニューやドラッグハンドルは標準では付かない。</p>
`;

interface TiptapEditorProps {
  /** Fires on every change with the ProseMirror JSON and the serialized HTML. */
  onChange?: (json: unknown, html: string) => void;
}

const BTN = "btn btn-xs btn-ghost border border-base-300 normal-case font-normal";

function ToolbarButton({
  editor,
  label,
  title,
  onClick,
  active,
  disabled,
}: {
  editor: Editor;
  label: string;
  title: string;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
}) {
  // `editor` is accepted so the button re-renders with the editor's state.
  void editor;
  return (
    <button
      type="button"
      title={title}
      className={`${BTN} ${active ? "btn-active" : ""}`}
      disabled={disabled}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

/**
 * A deliberately hand-rolled Tiptap editor + toolbar.
 *
 * The point of this component is to show — side by side with BlockNote — how
 * much UI you author yourself when using Tiptap (the headless framework):
 * every toolbar button, the table/image insert commands, and all content CSS
 * (see tiptap-demo.css) are written here by hand. BlockNote ships all of this.
 */
export function TiptapEditor({ onChange }: TiptapEditorProps) {
  const editor = useEditor({
    extensions: [
      StarterKit,
      Image,
      // TableKit bundles Table + TableRow + TableHeader + TableCell (Tiptap v3).
      TableKit.configure({ table: { resizable: true } }),
    ],
    content: SAMPLE_HTML,
    immediatelyRender: false,
    // Tiptap v3 no longer re-renders on every transaction by default, so the
    // toolbar's active/disabled states would go stale. Opt back in for this demo.
    shouldRerenderOnTransaction: true,
    onUpdate: ({ editor }) => onChange?.(editor.getJSON(), editor.getHTML()),
  });

  const addImage = useCallback(() => {
    if (!editor) return;
    const url = window.prompt("画像 URL（または data: URL）を入力");
    if (url) editor.chain().focus().setImage({ src: url }).run();
  }, [editor]);

  if (!editor) {
    return <div className="p-3 text-sm text-base-content/50">Loading Tiptap…</div>;
  }

  return (
    <div>
      {/* Hand-built toolbar — none of this is provided by Tiptap. */}
      <div className="flex flex-wrap gap-1 border-b border-base-300 p-2 bg-base-200/40">
        <ToolbarButton
          editor={editor}
          label="B"
          title="Bold"
          active={editor.isActive("bold")}
          onClick={() => editor.chain().focus().toggleBold().run()}
        />
        <ToolbarButton
          editor={editor}
          label="i"
          title="Italic"
          active={editor.isActive("italic")}
          onClick={() => editor.chain().focus().toggleItalic().run()}
        />
        <ToolbarButton
          editor={editor}
          label="S"
          title="Strike"
          active={editor.isActive("strike")}
          onClick={() => editor.chain().focus().toggleStrike().run()}
        />
        <ToolbarButton
          editor={editor}
          label="</>"
          title="Inline code"
          active={editor.isActive("code")}
          onClick={() => editor.chain().focus().toggleCode().run()}
        />
        <span className="mx-1 w-px bg-base-300" />
        <ToolbarButton
          editor={editor}
          label="H1"
          title="Heading 1"
          active={editor.isActive("heading", { level: 1 })}
          onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
        />
        <ToolbarButton
          editor={editor}
          label="H2"
          title="Heading 2"
          active={editor.isActive("heading", { level: 2 })}
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        />
        <ToolbarButton
          editor={editor}
          label="• List"
          title="Bullet list"
          active={editor.isActive("bulletList")}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
        />
        <ToolbarButton
          editor={editor}
          label="1. List"
          title="Ordered list"
          active={editor.isActive("orderedList")}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
        />
        <ToolbarButton
          editor={editor}
          label="❝ Quote"
          title="Blockquote"
          active={editor.isActive("blockquote")}
          onClick={() => editor.chain().focus().toggleBlockquote().run()}
        />
        <ToolbarButton
          editor={editor}
          label="Code block"
          title="Code block"
          active={editor.isActive("codeBlock")}
          onClick={() => editor.chain().focus().toggleCodeBlock().run()}
        />
        <span className="mx-1 w-px bg-base-300" />
        <ToolbarButton
          editor={editor}
          label="⊞ Table"
          title="Insert 3×3 table"
          onClick={() =>
            editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
          }
        />
        <ToolbarButton
          editor={editor}
          label="🖼 Image"
          title="Insert image by URL"
          onClick={addImage}
        />
        <span className="mx-1 w-px bg-base-300" />
        <ToolbarButton
          editor={editor}
          label="↶"
          title="Undo"
          disabled={!editor.can().undo()}
          onClick={() => editor.chain().focus().undo().run()}
        />
        <ToolbarButton
          editor={editor}
          label="↷"
          title="Redo"
          disabled={!editor.can().redo()}
          onClick={() => editor.chain().focus().redo().run()}
        />
      </div>

      <div className="tiptap-demo">
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}
