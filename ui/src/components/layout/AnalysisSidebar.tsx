"use client";

import React from "react";
import { useAnalysisChatContext } from "@/contexts/AnalysisChatContext";
import { AnalysisChatPanel } from "@/components/features/metrics/AnalysisChatPanel";

export function AnalysisSidebar() {
  const { isOpen, context } = useAnalysisChatContext();

  return (
    <div
      className={`fixed top-0 right-0 h-screen z-[9999] transition-transform duration-300 ease-in-out w-80 shadow-2xl ${
        isOpen ? "translate-x-0" : "translate-x-full"
      }`}
    >
      {isOpen && <AnalysisChatPanel context={context} />}
    </div>
  );
}
