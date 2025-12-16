"use client";

import { useState } from "react";
import { MessageCircle, X, Trash2, Maximize2, Minimize2 } from "lucide-react";
import { useGetCopilotConfig } from "@/client/metrics/metrics";
import { AssistantThread } from "./AssistantThread";

export function ChatPopup() {
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  // Fetch copilot config using generated client
  const { data: copilotConfig } = useGetCopilotConfig();

  // Get initial message from config
  const configData = copilotConfig?.data as
    | { initial_message?: string }
    | undefined;
  const initialMessage = configData?.initial_message;

  const toggleOpen = () => setIsOpen((prev) => !prev);

  if (!isOpen) {
    return (
      <button
        onClick={toggleOpen}
        className="btn btn-circle btn-primary btn-lg shadow-xl hover:scale-110 transition-transform duration-200"
        style={{
          position: "fixed",
          bottom: "1.5rem",
          right: "1.5rem",
          zIndex: 9999,
        }}
        aria-label="Open chat"
        title="QDash Assistant"
      >
        <MessageCircle className="w-6 h-6" />
      </button>
    );
  }

  const toggleExpanded = () => setIsExpanded((prev) => !prev);

  return (
    <div
      className={`flex flex-col bg-base-100 rounded-xl shadow-2xl border border-base-300 transition-all duration-200 ${
        isExpanded
          ? "w-[700px] max-w-[calc(100vw-2rem)]"
          : "w-[420px] max-w-[calc(100vw-2rem)]"
      }`}
      style={{
        position: "fixed",
        bottom: "1rem",
        right: "1rem",
        top: "auto",
        height: isExpanded
          ? "min(700px, calc(100vh - 2rem))"
          : "min(580px, calc(100vh - 2rem))",
        zIndex: 9999,
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-base-300 bg-base-200 rounded-t-xl shrink-0">
        <h3 className="font-semibold text-base-content text-sm">QDash Assistant</h3>
        <div className="flex gap-0.5">
          <ClearMessagesButton />
          <button
            onClick={toggleExpanded}
            className="btn btn-ghost btn-sm btn-square"
            aria-label={isExpanded ? "Minimize" : "Expand"}
            title={isExpanded ? "Minimize" : "Expand"}
          >
            {isExpanded ? (
              <Minimize2 className="w-4 h-4" />
            ) : (
              <Maximize2 className="w-4 h-4" />
            )}
          </button>
          <button
            onClick={toggleOpen}
            className="btn btn-ghost btn-sm btn-square"
            aria-label="Close chat"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Thread */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <AssistantThread initialMessage={initialMessage} />
      </div>
    </div>
  );
}

// Clear messages button
function ClearMessagesButton() {
  const handleClear = () => {
    // Reload to clear messages
    window.location.reload();
  };

  return (
    <button
      onClick={handleClear}
      className="btn btn-ghost btn-sm btn-square"
      aria-label="Clear messages"
      title="Clear messages"
    >
      <Trash2 className="w-4 h-4" />
    </button>
  );
}
