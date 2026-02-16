"use client";

import { MessageCircle, PanelRightClose } from "lucide-react";
import { useAnalysisChatContext } from "@/contexts/AnalysisChatContext";

export function ChatAssistant() {
  const { isOpen, toggleAnalysisChat } = useAnalysisChatContext();

  return (
    <button
      onClick={toggleAnalysisChat}
      className={`group fixed z-[9999] flex items-center justify-center rounded-full shadow-xl transition-all duration-300 hover:scale-110 hover:shadow-2xl ${
        isOpen
          ? "bottom-6 right-[21.5rem] w-10 h-10 bg-base-300 text-base-content/70 hover:bg-base-content/20"
          : "bottom-6 right-6 w-14 h-14 bg-neutral text-neutral-content"
      }`}
      style={{
        boxShadow: isOpen
          ? "0 2px 12px rgba(0, 0, 0, 0.15)"
          : "0 4px 24px rgba(0, 0, 0, 0.3)",
      }}
      aria-label={isOpen ? "Close chat" : "Open chat"}
      title={isOpen ? "Close sidebar" : "QDash Assistant"}
    >
      <div className="relative flex items-center justify-center">
        {isOpen ? (
          <PanelRightClose className="w-4 h-4" />
        ) : (
          <>
            <MessageCircle className="w-6 h-6 transition-transform group-hover:scale-110" />
            <span className="absolute -top-1 -right-1 w-3 h-3 bg-success rounded-full border-2 border-neutral" />
          </>
        )}
      </div>
    </button>
  );
}
