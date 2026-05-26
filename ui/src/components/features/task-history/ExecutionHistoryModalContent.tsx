"use client";

import type { ReactNode } from "react";
import { FileText, History, ListTodo } from "lucide-react";

export type ExecutionHistoryMobileTab = "history" | "tasks" | "details";

interface ExecutionHistoryModalContentProps {
  mobileTab: ExecutionHistoryMobileTab;
  onMobileTabChange: (tab: ExecutionHistoryMobileTab) => void;
  history: ReactNode;
  tasks: ReactNode;
  details: ReactNode;
  topContent?: ReactNode;
}

export function ExecutionHistoryModalContent({
  mobileTab,
  onMobileTabChange,
  history,
  tasks,
  details,
  topContent,
}: ExecutionHistoryModalContentProps) {
  return (
    <div className="h-full min-h-0 flex flex-col">
      {topContent && <div className="mb-3 shrink-0">{topContent}</div>}

      <div className="lg:hidden mb-3 shrink-0">
        <div className="tabs tabs-boxed bg-base-200">
          <button
            className={`tab gap-1 ${mobileTab === "history" ? "tab-active" : ""}`}
            onClick={() => onMobileTabChange("history")}
          >
            <History className="h-3 w-3" />
            History
          </button>
          <button
            className={`tab gap-1 ${mobileTab === "tasks" ? "tab-active" : ""}`}
            onClick={() => onMobileTabChange("tasks")}
          >
            <ListTodo className="h-3 w-3" />
            Tasks
          </button>
          <button
            className={`tab gap-1 ${mobileTab === "details" ? "tab-active" : ""}`}
            onClick={() => onMobileTabChange("details")}
          >
            <FileText className="h-3 w-3" />
            Details
          </button>
        </div>
      </div>

      <div className="lg:hidden flex-1 min-h-0 overflow-hidden">
        {mobileTab === "history" && history}
        {mobileTab === "tasks" && tasks}
        {mobileTab === "details" && details}
      </div>

      <div className="hidden lg:flex gap-4 h-full min-h-0">
        <div className="w-1/4 flex flex-col min-h-0 border-r border-base-300 pr-4">{history}</div>
        <div className="w-1/4 flex flex-col min-h-0 border-r border-base-300 pr-4">{tasks}</div>
        <div className="w-1/2 overflow-y-auto min-h-0">{details}</div>
      </div>
    </div>
  );
}
