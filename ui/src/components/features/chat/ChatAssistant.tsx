"use client";

import { MessageCircle } from "lucide-react";
import { useAnalysisChatContext } from "@/contexts/AnalysisChatContext";

export function ChatAssistant() {
  const { isOpen, toggleAnalysisChat } = useAnalysisChatContext();

  return (
    <button
      onClick={toggleAnalysisChat}
      className={`group fixed bottom-6 right-6 z-[9999] flex items-center justify-center w-14 h-14 rounded-full shadow-xl transition-all duration-300 hover:scale-110 hover:shadow-2xl ${
        isOpen
          ? "bg-primary text-primary-content"
          : "bg-neutral text-neutral-content"
      }`}
      style={{
        boxShadow: "0 4px 24px rgba(0, 0, 0, 0.3)",
      }}
      aria-label={isOpen ? "Close chat" : "Open chat"}
      title="QDash Assistant"
    >
      <div className="relative flex items-center justify-center">
        <MessageCircle className="w-6 h-6 transition-transform group-hover:scale-110" />
        {!isOpen && (
          <span className="absolute -top-1 -right-1 w-3 h-3 bg-success rounded-full border-2 border-neutral" />
        )}
      </div>
    </button>
  );
}
