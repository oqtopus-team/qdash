"use client";

import { useState } from "react";
import { MessageCircle, X, Trash2, Maximize2, Minimize2 } from "lucide-react";
import Image from "next/image";
import { AssistantThread } from "./AssistantThread";

interface ChatPopupProps {
  onClear: () => void;
  initialMessage?: string;
  suggestions?: Array<{ label: string; prompt: string }>;
}

export function ChatPopup({
  onClear,
  initialMessage,
  suggestions,
}: ChatPopupProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  const toggleOpen = () => setIsOpen((prev) => !prev);
  const toggleExpanded = () => setIsExpanded((prev) => !prev);

  if (!isOpen) {
    return (
      <button
        onClick={toggleOpen}
        className="group fixed bottom-6 right-6 z-[9999] flex items-center justify-center w-14 h-14 rounded-full shadow-xl transition-all duration-300 hover:scale-110 hover:shadow-2xl bg-neutral text-neutral-content"
        style={{
          boxShadow: "0 4px 24px rgba(0, 0, 0, 0.3)",
        }}
        aria-label="Open chat"
        title="QDash Assistant"
      >
        {/* Icon */}
        <div className="relative flex items-center justify-center">
          <MessageCircle className="w-6 h-6 transition-transform group-hover:scale-110" />
          <span className="absolute -top-1 -right-1 w-3 h-3 bg-success rounded-full border-2 border-neutral" />
        </div>
      </button>
    );
  }

  return (
    <div
      className={`flex flex-col bg-base-100 rounded-2xl shadow-2xl border border-base-300 transition-all duration-300 overflow-hidden ${
        isExpanded
          ? "w-[700px] max-w-[calc(100vw-2rem)]"
          : "w-[420px] max-w-[calc(100vw-2rem)]"
      }`}
      style={{
        position: "fixed",
        bottom: "1.5rem",
        right: "1.5rem",
        top: "auto",
        height: isExpanded
          ? "min(550px, calc(100vh - 8rem))"
          : "min(480px, calc(100vh - 8rem))",
        zIndex: 9999,
      }}
    >
      {/* Header */}
      <ChatHeader
        isExpanded={isExpanded}
        onToggleExpanded={toggleExpanded}
        onClose={toggleOpen}
        onClear={onClear}
      />

      {/* Thread */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <AssistantThread
          initialMessage={initialMessage}
          suggestions={suggestions}
        />
      </div>
    </div>
  );
}

// Chat header component
interface ChatHeaderProps {
  isExpanded: boolean;
  onToggleExpanded: () => void;
  onClose: () => void;
  onClear: () => void;
}

function ChatHeader({
  isExpanded,
  onToggleExpanded,
  onClose,
  onClear,
}: ChatHeaderProps) {
  return (
    <div
      className="flex items-center justify-between px-4 py-3 border-b border-base-300 shrink-0"
      style={{
        background:
          "linear-gradient(135deg, oklch(var(--b2)) 0%, oklch(var(--b1)) 100%)",
      }}
    >
      <div className="flex items-center gap-3">
        {/* Logo/Avatar */}
        <div
          className="w-8 h-8 rounded-xl flex items-center justify-center shadow-sm"
          style={{
            background:
              "linear-gradient(135deg, oklch(var(--p) / 0.15) 0%, oklch(var(--s) / 0.15) 100%)",
          }}
        >
          <Image
            src="/oqtopus_logo.svg"
            alt="OQTOPUS"
            width={24}
            height={24}
            className="object-contain"
          />
        </div>
        <div>
          <h3 className="font-semibold text-base-content text-sm leading-tight">
            QDash Assistant
          </h3>
          <p className="text-xs text-base-content/50">Powered by AI</p>
        </div>
      </div>

      <div className="flex gap-1">
        <button
          onClick={onClear}
          className="btn btn-ghost btn-sm btn-square hover:bg-base-300"
          aria-label="Clear messages"
          title="Clear conversation"
        >
          <Trash2 className="w-4 h-4 opacity-60" />
        </button>
        <button
          onClick={onToggleExpanded}
          className="btn btn-ghost btn-sm btn-square hover:bg-base-300"
          aria-label={isExpanded ? "Minimize" : "Expand"}
          title={isExpanded ? "Minimize" : "Expand"}
        >
          {isExpanded ? (
            <Minimize2 className="w-4 h-4 opacity-60" />
          ) : (
            <Maximize2 className="w-4 h-4 opacity-60" />
          )}
        </button>
        <button
          onClick={onClose}
          className="btn btn-ghost btn-sm btn-square hover:bg-error/20 hover:text-error"
          aria-label="Close chat"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
