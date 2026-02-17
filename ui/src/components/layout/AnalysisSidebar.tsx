"use client";

import React from "react";
import { Bot } from "lucide-react";
import { useAnalysisChatContext } from "@/contexts/AnalysisChatContext";
import { AnalysisChatPanel } from "@/components/features/metrics/AnalysisChatPanel";

export function AnalysisSidebar() {
  const { isOpen, activeSession, openGeneralChat } = useAnalysisChatContext();

  return (
    <>
      {/* Right-edge floating tab — always visible when sidebar is closed */}
      {!isOpen && (
        <button
          onClick={openGeneralChat}
          className="fixed right-0 top-1/2 -translate-y-1/2 z-[9998] flex flex-col items-center gap-1.5 bg-primary text-primary-content px-1.5 py-3 rounded-l-xl shadow-lg hover:px-2 transition-all duration-200"
          title="Ask AI"
        >
          <Bot className="w-5 h-5" />
          <span
            className="text-[10px] font-semibold select-none"
            style={{ writingMode: "vertical-rl" }}
          >
            Ask AI
          </span>
        </button>
      )}

      {/* Slide-in sidebar panel */}
      <div
        className={`fixed top-0 right-0 h-screen z-[9999] transition-transform duration-300 ease-in-out w-80 shadow-2xl ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {isOpen && (
          <AnalysisChatPanel context={activeSession?.context ?? null} />
        )}
      </div>
    </>
  );
}
