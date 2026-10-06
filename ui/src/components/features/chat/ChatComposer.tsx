"use client";

import React, { forwardRef, useCallback, useEffect, useImperativeHandle, useRef } from "react";
import { ArrowUp, Check, ChevronDown, Cpu, Square } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
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
    compact = false,
  },
  ref,
) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => ({ focus: () => textareaRef.current?.focus() }), []);

  // Grow with the content up to MAX_HEIGHT_PX, then scroll.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  const canSend = value.trim().length > 0 && !isStreaming && !disabled;

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

  const selected = modelOptions.find((o) => o.key === selectedModelKey) ?? modelOptions[0];

  return (
    <form
      className="chat-composer"
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSubmit();
      }}
    >
      <textarea
        ref={textareaRef}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        rows={1}
        aria-label="Message"
        className={`w-full resize-none bg-transparent border-none outline-none focus:ring-0 leading-6 px-1 pt-1 placeholder:text-base-content/35 ${
          compact ? "text-sm" : "text-[15px]"
        }`}
      />
      <div className="flex items-center gap-2 pt-1">
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
