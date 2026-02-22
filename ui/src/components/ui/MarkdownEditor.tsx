"use client";

import React, { useRef, useState, useCallback } from "react";
import {
  Bold,
  Italic,
  Strikethrough,
  Code,
  Link,
  Quote,
  List,
  ListOrdered,
  ImageIcon,
  Bot,
} from "lucide-react";
import { MarkdownContent } from "./MarkdownContent";

interface MentionCandidate {
  id: string;
  label: string;
  icon?: React.ReactNode;
}

interface MarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit?: () => void;
  placeholder?: string;
  rows?: number;
  disabled?: boolean;
  submitLabel?: string;
  isSubmitting?: boolean;
  onImageUpload?: (file: File) => Promise<string>;
  mentionCandidates?: MentionCandidate[];
}

type ToolbarAction = {
  icon: React.ReactNode;
  title: string;
  apply: (text: string, start: number, end: number) => WrapResult;
};

type WrapResult = {
  text: string;
  selectionStart: number;
  selectionEnd: number;
};

function wrapSelection(
  text: string,
  start: number,
  end: number,
  prefix: string,
  suffix: string,
): WrapResult {
  const selected = text.slice(start, end);
  const placeholder = selected || "text";
  const newText =
    text.slice(0, start) + prefix + placeholder + suffix + text.slice(end);
  return {
    text: newText,
    selectionStart: start + prefix.length,
    selectionEnd: start + prefix.length + placeholder.length,
  };
}

function insertLinePrefix(
  text: string,
  start: number,
  end: number,
  prefix: string,
): WrapResult {
  const selected = text.slice(start, end);
  if (selected) {
    const lines = selected.split("\n");
    const prefixed = lines.map((line) => prefix + line).join("\n");
    const newText = text.slice(0, start) + prefixed + text.slice(end);
    return {
      text: newText,
      selectionStart: start,
      selectionEnd: start + prefixed.length,
    };
  }
  const newText = text.slice(0, start) + prefix + "item" + text.slice(end);
  return {
    text: newText,
    selectionStart: start + prefix.length,
    selectionEnd: start + prefix.length + 4,
  };
}

const ICON_SIZE = "h-3.5 w-3.5";

const toolbarActions: ToolbarAction[] = [
  {
    icon: <Bold className={ICON_SIZE} />,
    title: "Bold",
    apply: (text, start, end) => wrapSelection(text, start, end, "**", "**"),
  },
  {
    icon: <Italic className={ICON_SIZE} />,
    title: "Italic",
    apply: (text, start, end) => wrapSelection(text, start, end, "*", "*"),
  },
  {
    icon: <Strikethrough className={ICON_SIZE} />,
    title: "Strikethrough",
    apply: (text, start, end) => wrapSelection(text, start, end, "~~", "~~"),
  },
  {
    icon: <Code className={ICON_SIZE} />,
    title: "Code",
    apply: (text, start, end) => {
      const selected = text.slice(start, end);
      if (selected.includes("\n") || (!selected && start === end)) {
        // Multi-line or empty: insert code block
        if (selected) {
          return wrapSelection(text, start, end, "```\n", "\n```");
        }
        const block = "```\ncode\n```";
        const newText = text.slice(0, start) + block + text.slice(end);
        return {
          text: newText,
          selectionStart: start + 4,
          selectionEnd: start + 8,
        };
      }
      return wrapSelection(text, start, end, "`", "`");
    },
  },
  {
    icon: <Link className={ICON_SIZE} />,
    title: "Link",
    apply: (text, start, end) => {
      const selected = text.slice(start, end);
      const label = selected || "text";
      const inserted = `[${label}](url)`;
      const newText = text.slice(0, start) + inserted + text.slice(end);
      if (selected) {
        // Select the url part
        return {
          text: newText,
          selectionStart: start + label.length + 3,
          selectionEnd: start + label.length + 6,
        };
      }
      return {
        text: newText,
        selectionStart: start + 1,
        selectionEnd: start + 5,
      };
    },
  },
  {
    icon: <Quote className={ICON_SIZE} />,
    title: "Quote",
    apply: (text, start, end) => insertLinePrefix(text, start, end, "> "),
  },
  {
    icon: <List className={ICON_SIZE} />,
    title: "Bullet List",
    apply: (text, start, end) => insertLinePrefix(text, start, end, "- "),
  },
  {
    icon: <ListOrdered className={ICON_SIZE} />,
    title: "Ordered List",
    apply: (text, start, end) => insertLinePrefix(text, start, end, "1. "),
  },
];

export function MarkdownEditor({
  value,
  onChange,
  onSubmit,
  placeholder = "Write a comment...",
  rows = 3,
  disabled = false,
  submitLabel,
  isSubmitting = false,
  onImageUpload,
  mentionCandidates,
}: MarkdownEditorProps) {
  const [tab, setTab] = useState<"write" | "preview">("write");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const valueRef = useRef(value);
  valueRef.current = value;

  // Mention autocomplete state
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState("");
  const [mentionStart, setMentionStart] = useState(0);
  const [mentionIndex, setMentionIndex] = useState(0);
  const mentionRef = useRef<HTMLDivElement>(null);

  const filteredMentions = (mentionCandidates ?? []).filter((c) =>
    c.id.toLowerCase().startsWith(mentionQuery.toLowerCase()),
  );

  const closeMention = useCallback(() => {
    setMentionOpen(false);
    setMentionQuery("");
    setMentionIndex(0);
  }, []);

  const selectMention = useCallback(
    (candidate: MentionCandidate) => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      const before = valueRef.current.slice(0, mentionStart);
      const after = valueRef.current.slice(textarea.selectionStart);
      const inserted = `@${candidate.id} `;
      onChange(before + inserted + after);
      closeMention();
      requestAnimationFrame(() => {
        textarea.focus();
        const pos = mentionStart + inserted.length;
        textarea.setSelectionRange(pos, pos);
      });
    },
    [mentionStart, onChange, closeMention],
  );

  const insertImageMarkdown = useCallback(
    async (file: File) => {
      if (!onImageUpload) return;
      const textarea = textareaRef.current;
      const pos = textarea?.selectionStart ?? valueRef.current.length;
      const placeholder = "![Uploading...]()";
      const before = valueRef.current.slice(0, pos);
      const after = valueRef.current.slice(pos);
      onChange(before + placeholder + after);

      try {
        const url = await onImageUpload(file);
        const current = valueRef.current;
        const idx = current.indexOf(placeholder);
        if (idx !== -1) {
          onChange(
            current.slice(0, idx) +
              `![image](${url})` +
              current.slice(idx + placeholder.length),
          );
        } else {
          onChange(current + `\n![image](${url})`);
        }
      } catch {
        const current = valueRef.current;
        onChange(current.replace(placeholder, ""));
      }
    },
    [onImageUpload, onChange],
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      if (!onImageUpload) return;
      const items = e.clipboardData?.items;
      if (!items) return;
      for (const item of items) {
        if (item.type.startsWith("image/")) {
          e.preventDefault();
          const file = item.getAsFile();
          if (file) insertImageMarkdown(file);
          return;
        }
      }
    },
    [onImageUpload, insertImageMarkdown],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLTextAreaElement>) => {
      if (!onImageUpload) return;
      const files = e.dataTransfer?.files;
      if (!files) return;
      for (const file of files) {
        if (file.type.startsWith("image/")) {
          e.preventDefault();
          insertImageMarkdown(file);
          return;
        }
      }
    },
    [onImageUpload, insertImageMarkdown],
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent<HTMLTextAreaElement>) => {
      if (!onImageUpload) return;
      e.preventDefault();
    },
    [onImageUpload],
  );

  const applyAction = useCallback(
    (action: ToolbarAction) => {
      const textarea = textareaRef.current;
      if (!textarea) return;

      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const result = action.apply(value, start, end);

      onChange(result.text);

      // Restore cursor position after React re-render
      requestAnimationFrame(() => {
        textarea.focus();
        textarea.setSelectionRange(result.selectionStart, result.selectionEnd);
      });
    },
    [value, onChange],
  );

  const handleTextChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const newValue = e.target.value;
      onChange(newValue);

      if (!mentionCandidates?.length) return;

      const cursor = e.target.selectionStart;
      // Look backwards for @ trigger
      const textBefore = newValue.slice(0, cursor);
      const atMatch = textBefore.match(/(^|[\s(])@(\w*)$/);
      if (atMatch) {
        const atPos = textBefore.lastIndexOf("@");
        setMentionStart(atPos);
        setMentionQuery(atMatch[2]);
        setMentionOpen(true);
        setMentionIndex(0);
      } else {
        closeMention();
      }
    },
    [onChange, mentionCandidates, closeMention],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Mention popup navigation
    if (mentionOpen && filteredMentions.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMentionIndex((i) => (i + 1) % filteredMentions.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setMentionIndex(
          (i) => (i - 1 + filteredMentions.length) % filteredMentions.length,
        );
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        selectMention(filteredMentions[mentionIndex]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        closeMention();
        return;
      }
    }

    if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && onSubmit) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className="w-full">
      {/* Tabs */}
      <div className="tabs tabs-bordered tabs-xs mb-0">
        <button
          type="button"
          className={`tab ${tab === "write" ? "tab-active" : ""}`}
          onClick={() => setTab("write")}
        >
          Write
        </button>
        <button
          type="button"
          className={`tab ${tab === "preview" ? "tab-active" : ""}`}
          onClick={() => setTab("preview")}
        >
          Preview
        </button>
      </div>

      {tab === "write" ? (
        <div>
          {/* Toolbar */}
          <div className="flex items-center gap-0.5 px-1 py-1 border border-base-300 border-b-0 rounded-t-none bg-base-200/50">
            {toolbarActions.map((action) => (
              <button
                key={action.title}
                type="button"
                className="btn btn-ghost btn-xs px-1.5"
                title={action.title}
                onClick={() => applyAction(action)}
                disabled={disabled}
              >
                {action.icon}
              </button>
            ))}
            {onImageUpload && (
              <>
                <button
                  type="button"
                  className="btn btn-ghost btn-xs px-1.5"
                  title="Upload Image"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={disabled}
                >
                  <ImageIcon className={ICON_SIZE} />
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/gif,image/webp"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) insertImageMarkdown(file);
                    e.target.value = "";
                  }}
                />
              </>
            )}
          </div>

          {/* Textarea + mention popup */}
          <div className="relative">
            <textarea
              ref={textareaRef}
              className="textarea textarea-bordered w-full rounded-t-none border-t-0 text-sm resize-none focus:outline-none"
              placeholder={placeholder}
              value={value}
              onChange={handleTextChange}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onBlur={() => setTimeout(closeMention, 150)}
              rows={rows}
              disabled={disabled}
            />
            {mentionOpen && filteredMentions.length > 0 && (
              <div
                ref={mentionRef}
                className="absolute bottom-full left-0 mb-1 z-50 bg-base-100 border border-base-300 rounded-lg shadow-lg py-1 min-w-[180px]"
              >
                {filteredMentions.map((candidate, i) => (
                  <button
                    key={candidate.id}
                    type="button"
                    className={`flex items-center gap-2 w-full px-3 py-1.5 text-sm text-left hover:bg-base-200 ${
                      i === mentionIndex ? "bg-base-200" : ""
                    }`}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      selectMention(candidate);
                    }}
                  >
                    {candidate.icon ?? (
                      <Bot className="h-3.5 w-3.5 text-primary" />
                    )}
                    <span className="font-medium">@{candidate.id}</span>
                    {candidate.label && (
                      <span className="text-base-content/50 text-xs">
                        {candidate.label}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="border border-base-300 rounded-b-lg p-3 min-h-[4rem]">
          {value.trim() ? (
            <MarkdownContent content={value} />
          ) : (
            <p className="text-sm text-base-content/40 italic">
              Nothing to preview
            </p>
          )}
        </div>
      )}

      {/* Submit button */}
      {submitLabel && (
        <div className="flex justify-end mt-2">
          <button
            type="button"
            className="btn btn-sm btn-primary"
            disabled={disabled || isSubmitting || !value.trim()}
            onClick={onSubmit}
          >
            {isSubmitting ? (
              <span className="loading loading-spinner loading-xs"></span>
            ) : (
              submitLabel
            )}
          </button>
        </div>
      )}
    </div>
  );
}
