"use client";

import { Bot } from "lucide-react";
import { useAnalysisChatContext } from "@/contexts/AnalysisChatContext";
import { AnalysisChatPanel } from "@/components/features/metrics/AnalysisChatPanel";

export function AnalysisSidebar() {
  const { isOpen, activeSession, openGeneralChat, closeAnalysisChat } = useAnalysisChatContext();

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

      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          onClick={closeAnalysisChat}
          aria-hidden="true"
        />
      )}

      {/* Full-screen overlay below lg; inline flex panel at lg+ */}
      <div
        className={`bg-base-100 overflow-hidden transition-[width] duration-300 ease-in-out max-lg:fixed max-lg:inset-y-0 max-lg:right-0 max-lg:z-50 lg:h-screen lg:flex-shrink-0 lg:border-l lg:border-base-300 ${
          isOpen ? "max-lg:w-full lg:w-[28rem] xl:w-[32rem]" : "w-0"
        }`}
      >
        {isOpen && (
          <div className="h-full w-screen max-w-full lg:w-[28rem] xl:w-[32rem]">
            <AnalysisChatPanel context={activeSession?.context ?? null} />
          </div>
        )}
      </div>
    </>
  );
}
