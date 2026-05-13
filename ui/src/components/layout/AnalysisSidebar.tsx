"use client";

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
          className="fixed right-0 top-1/2 -translate-y-1/2 z-50 flex flex-col items-center gap-1.5 bg-primary text-primary-content px-1.5 py-3 rounded-l-xl shadow-lg hover:px-2 transition-all duration-200"
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

      {/* Inline sidebar panel — participates in flex layout to push main content */}
      <div
        className={`h-screen flex-shrink-0 border-l border-base-300 bg-base-100 transition-[width] duration-300 ease-in-out overflow-hidden ${
          isOpen ? "w-[28rem] xl:w-[32rem]" : "w-0"
        }`}
      >
        {isOpen && (
          <div className="w-[28rem] xl:w-[32rem] h-full">
            <AnalysisChatPanel context={activeSession?.context ?? null} />
          </div>
        )}
      </div>
    </>
  );
}
