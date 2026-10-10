"use client";

import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { ArrowUp, Check, ChevronDown, Cpu, Paperclip, Square, X } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import {
  ACCEPT_ATTRIBUTE,
  MAX_ATTACHMENTS,
  acceptedImageFiles,
  pastedImageFiles,
  type StagedAttachment,
} from "@/lib/chatAttachments";
import type { ModelOption } from "@/lib/copilotModels";

const MAX_HEIGHT_PX = 240;

interface ChatComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  placeholder?: string;
  modelOptions: ModelOption[];
  selectedModelKey: string;
  onModelChange: (key: string) => void;
  /** Figures staged for the next message; omit to hide attachments entirely. */
  attachments?: StagedAttachment[];
  isStaging?: boolean;
  attachmentNotice?: string;
  /** Files picked, pasted, or dropped; the owner stages them. */
  onAttach?: (files: File[]) => void;
  onRemoveAttachment?: (id: string) => void;
  /** Narrow surfaces: smaller type and a shorter model label. */
  compact?: boolean;
}

export interface ChatComposerHandle {
  focus: () => void;
}

export const ChatComposer = forwardRef<ChatComposerHandle, ChatComposerProps>(function ChatComposer(
  {
    value,
    onChange,
    onSubmit,
    onStop,
    isStreaming,
    disabled = false,
    placeholder = "Ask about calibration data...",
    modelOptions,
    selectedModelKey,
    onModelChange,
    attachments,
    isStaging = false,
    attachmentNotice,
    onAttach,
    onRemoveAttachment,
    compact = false,
  },
  ref,
) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState("");
  useImperativeHandle(ref, () => ({ focus: () => textareaRef.current?.focus() }), []);

  // Grow with the content up to MAX_HEIGHT_PX, then scroll.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  const canAttach = Boolean(onAttach) && !isStreaming && !disabled;
  const attachmentsFull = (attachments?.length ?? 0) >= MAX_ATTACHMENTS;
  const canSend = value.trim().length > 0 && !isStreaming && !disabled && !isStaging;

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.nativeEvent.isComposing) return;
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (canSend) onSubmit();
      }
    },
    [canSend, onSubmit],
  );

  // Screenshots pasted from the clipboard arrive as files; text pastes as usual.
  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      if (!canAttach) return;
      const files = pastedImageFiles(e.clipboardData);
      if (files.length === 0) return;
      e.preventDefault();
      setNotice("");
      onAttach?.(files);
    },
    [canAttach, onAttach],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLFormElement>) => {
      e.preventDefault();
      setDragging(false);
      if (!e.dataTransfer.files.length) return;
      if (!canAttach) {
        setNotice("Images cannot be attached while this chat is busy.");
        return;
      }
      const files = acceptedImageFiles(e.dataTransfer.files);
      setNotice(
        files.length < e.dataTransfer.files.length
          ? "Only PNG and JPEG images can be attached."
          : "",
      );
      if (files.length) onAttach?.(files);
    },
    [canAttach, onAttach],
  );

  const handleFilesPicked = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = acceptedImageFiles(e.target.files);
      // Reset so picking the same file again fires a change event.
      e.target.value = "";
      setNotice("");
      if (canAttach && files.length) onAttach?.(files);
    },
    [canAttach, onAttach],
  );

  const selected = modelOptions.find((o) => o.key === selectedModelKey) ?? modelOptions[0];

  return (
    <form
      className={`chat-composer ${dragging ? "ring-2 ring-primary/40" : ""}`}
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSubmit();
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(canAttach);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      {(notice || attachmentNotice) && (
        <p role="alert" className="text-xs text-error px-1 pb-2">
          {notice || attachmentNotice}
        </p>
      )}
      {isStaging && (
        <p role="status" className="text-xs text-base-content/60 px-1 pb-2">
          Preparing images…
        </p>
      )}
      {attachments && attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 px-1 pb-2" aria-label="Attached figures">
          {attachments.map((attachment) => (
            <div key={attachment.id} className="relative group/thumb">
              {/* eslint-disable-next-line @next/next/no-img-element -- data URL preview */}
              <img
                src={attachment.previewUrl}
                alt={attachment.name}
                title={attachment.name}
                className="h-16 w-16 rounded-lg object-cover border border-base-300 bg-base-200"
              />
              {onRemoveAttachment && (
                <button
                  type="button"
                  onClick={() => onRemoveAttachment(attachment.id)}
                  className="absolute -top-1.5 -right-1.5 btn btn-circle btn-xs h-5 w-5 min-h-0 bg-base-content text-base-100 border-none opacity-0 group-hover/thumb:opacity-100 focus:opacity-100"
                  aria-label={`Remove ${attachment.name}`}
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      <textarea
        ref={textareaRef}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        placeholder={placeholder}
        rows={1}
        aria-label="Message"
        className={`w-full resize-none bg-transparent border-none outline-none focus:ring-0 leading-6 px-1 pt-1 placeholder:text-base-content/35 ${
          compact ? "text-sm" : "text-[15px]"
        }`}
      />
      <div className="flex items-center gap-2 pt-1">
        {onAttach && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT_ATTRIBUTE}
              multiple
              hidden
              onChange={handleFilesPicked}
            />
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  disabled={!canAttach || attachmentsFull}
                  onClick={() => fileInputRef.current?.click()}
                  className="btn btn-ghost btn-xs btn-circle h-7 w-7 text-base-content/60"
                  aria-label="Attach a figure"
                >
                  <Paperclip className="w-3.5 h-3.5" />
                </button>
              </TooltipTrigger>
              <TooltipContent>
                {attachmentsFull
                  ? `Up to ${MAX_ATTACHMENTS} figures per message`
                  : "Attach a figure (PNG/JPEG, or paste a screenshot)"}
              </TooltipContent>
            </Tooltip>
          </>
        )}
        {modelOptions.length > 1 && selected && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                disabled={isStreaming || disabled}
                className="btn btn-ghost btn-xs h-7 gap-1.5 rounded-lg font-normal text-base-content/60 max-w-[60%]"
                aria-label="Chat model"
              >
                <Cpu className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">
                  {compact ? (selected.model?.name ?? "Default model") : selected.label}
                </span>
                <ChevronDown className="w-3 h-3 shrink-0" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" side="top">
              {modelOptions.map((option) => (
                <DropdownMenuItem key={option.key} onSelect={() => onModelChange(option.key)}>
                  <span className="flex-1 truncate">{option.label}</span>
                  {option.key === selected.key && <Check className="w-3.5 h-3.5 text-primary" />}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        <div className="flex-1" />
        {isStreaming ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={onStop}
                className="btn btn-circle btn-sm bg-base-content text-base-100 hover:bg-base-content/80 border-none"
                aria-label="Stop generating"
              >
                <Square className="w-3 h-3 fill-current" />
              </button>
            </TooltipTrigger>
            <TooltipContent>Stop (Esc)</TooltipContent>
          </Tooltip>
        ) : (
          <button
            type="submit"
            disabled={!canSend}
            className="btn btn-circle btn-sm btn-primary disabled:bg-base-content/15 disabled:text-base-100"
            aria-label="Send message"
          >
            <ArrowUp className="w-4 h-4" />
          </button>
        )}
      </div>
    </form>
  );
});
