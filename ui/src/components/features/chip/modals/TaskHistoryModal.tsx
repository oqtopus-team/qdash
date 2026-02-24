"use client";

import React, { useState, useRef, useLayoutEffect, useMemo } from "react";
import Link from "next/link";
import { ChevronRight, History, FileText, GitBranch, Bot } from "lucide-react";

import type { Task } from "@/schemas";

import { formatDateTime, formatDateTimeCompact } from "@/lib/utils/datetime";

import { useGetQubitTaskHistory } from "@/client/task-result/task-result";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { ParametersTable } from "@/components/features/metrics/ParametersTable";
import { TaskResultIssues } from "@/components/features/metrics/TaskResultIssues";
import type { AnalysisContext } from "@/hooks/useAnalysisChat";
import { useAnalysisChatContext } from "@/contexts/AnalysisChatContext";

interface TaskHistoryModalProps {
  chipId: string;
  qid: string;
  taskName: string;
  isOpen: boolean;
  onClose: () => void;
}

type MobileTab = "history" | "details";

export function TaskHistoryModal({
  chipId,
  qid,
  taskName,
  isOpen,
  onClose,
}: TaskHistoryModalProps) {
  const modalRef = useRef<HTMLDialogElement>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [mobileTab, setMobileTab] = useState<MobileTab>("history");
  const { openAnalysisChat } = useAnalysisChatContext();

  const buildProvenanceUrl = (parameterName: string, qidValue: string) => {
    const p = encodeURIComponent(parameterName);
    const q = encodeURIComponent(qidValue);
    return `/provenance?tab=lineage&parameter=${p}&qid=${q}`;
  };

  useLayoutEffect(() => {
    const modal = modalRef.current;
    if (!modal) return;

    if (isOpen && !modal.open) {
      modal.showModal();
    } else if (!isOpen && modal.open) {
      modal.close();
    }
  }, [isOpen]);

  const { data, isLoading, isError } = useGetQubitTaskHistory(
    qid,
    { chip_id: chipId, task: taskName },
    {
      query: {
        enabled: isOpen && !!chipId && !!qid && !!taskName,
        staleTime: 30000,
        gcTime: 60000,
      },
    },
  );

  const historyArray = Object.entries(data?.data?.data || {})
    .map(([key, task]) => ({ key, task: task as Task }))
    .sort((a, b) => {
      const dateA = a.task.end_at ? new Date(a.task.end_at).getTime() : 0;
      const dateB = b.task.end_at ? new Date(b.task.end_at).getTime() : 0;
      return dateB - dateA;
    });

  const selectedItem = historyArray[selectedIndex];
  const selectedTask = selectedItem?.task;
  const figures = selectedTask
    ? Array.isArray(selectedTask.figure_path)
      ? selectedTask.figure_path
      : selectedTask.figure_path
        ? [selectedTask.figure_path]
        : []
    : [];

  const analysisContext: AnalysisContext | null = useMemo(() => {
    if (!selectedTask?.task_id) return null;
    return {
      taskName: selectedTask.name || taskName,
      chipId,
      qid,
      executionId: "",
      taskId: selectedTask.task_id,
    };
  }, [selectedTask, chipId, qid, taskName]);

  const handleSelectIndex = (idx: number) => {
    setSelectedIndex(idx);
    setMobileTab("details");
  };

  // Column 1: History List
  const renderHistoryList = () => (
    <div className="flex flex-col min-h-0 h-full">
      <div className="mb-3 shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <History className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-bold text-base-content">History</h3>
        </div>
        <p className="text-xs text-base-content/50">
          {historyArray.length} results
        </p>
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="flex flex-col gap-2">
          {historyArray.map((item, idx) => {
            const isSelected = idx === selectedIndex;
            return (
              <button
                key={item.key}
                onClick={() => handleSelectIndex(idx)}
                className={`w-full text-left p-3 rounded-lg transition-all border-2 ${
                  isSelected
                    ? "bg-primary text-primary-content border-primary"
                    : "bg-base-200 hover:bg-base-300 border-transparent hover:border-primary/30"
                }`}
              >
                <div className="flex justify-between items-start">
                  <div className="min-w-0 flex-1">
                    <div className="font-bold text-sm">
                      {item.task.status === "completed" ? (
                        <span className={isSelected ? "" : "text-success"}>
                          Completed
                        </span>
                      ) : item.task.status === "failed" ? (
                        <span className={isSelected ? "" : "text-error"}>
                          Failed
                        </span>
                      ) : (
                        <span className={isSelected ? "" : "text-warning"}>
                          {item.task.status}
                        </span>
                      )}
                    </div>
                    <div className="text-xs opacity-70 mt-1">
                      {item.task.end_at
                        ? formatDateTimeCompact(item.task.end_at)
                        : "N/A"}
                    </div>
                    {idx === 0 && (
                      <span
                        className={`badge badge-xs mt-1 ${
                          isSelected ? "badge-primary-content" : "badge-success"
                        }`}
                      >
                        Latest
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="text-xs opacity-60">#{idx + 1}</span>
                    <ChevronRight
                      className={`h-4 w-4 opacity-40 ${isSelected ? "opacity-80" : ""}`}
                    />
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );

  // Column 2: Task Details
  const renderTaskDetails = () => (
    <div className="flex flex-col">
      <div className="flex items-center justify-between mb-3 shrink-0">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-bold text-base-content">Task Details</h3>
        </div>
        {historyArray.length > 0 && (
          <div className="text-xs text-base-content/60">
            {selectedIndex + 1} / {historyArray.length}
          </div>
        )}
      </div>

      {/* Navigation Arrows */}
      {historyArray.length > 1 && (
        <div className="flex gap-2 mb-2 shrink-0">
          <button
            className="btn btn-xs btn-ghost"
            disabled={selectedIndex === 0}
            onClick={() => handleSelectIndex(Math.max(0, selectedIndex - 1))}
          >
            ← Newer
          </button>
          <button
            className="btn btn-xs btn-ghost"
            disabled={selectedIndex === historyArray.length - 1}
            onClick={() =>
              handleSelectIndex(
                Math.min(historyArray.length - 1, selectedIndex + 1),
              )
            }
          >
            Older →
          </button>
        </div>
      )}

      {/* Figure Display - Fixed height with horizontal scroll */}
      <div className="h-[280px] bg-base-200 rounded-lg p-3 overflow-x-auto overflow-y-hidden flex items-center justify-start gap-3">
        {!selectedTask ? (
          <div className="flex flex-col items-center justify-center w-full text-base-content/40">
            <FileText className="h-12 w-12 mb-3 opacity-30" />
            <p className="text-sm">Select a history item to view details</p>
          </div>
        ) : figures.length > 0 ? (
          figures.map((fig, i) => (
            <TaskFigure
              key={i}
              path={fig}
              qid={qid}
              className="h-full w-auto object-contain flex-shrink-0"
            />
          ))
        ) : selectedTask.task_id ? (
          <TaskFigure
            taskId={selectedTask.task_id}
            qid={qid}
            className="h-full w-auto object-contain"
          />
        ) : (
          <div className="flex flex-col items-center justify-center w-full text-base-content/40">
            <FileText className="h-12 w-12 mb-3 opacity-30" />
            <p className="text-sm">No figure available</p>
          </div>
        )}
      </div>

      {/* Task Metadata */}
      {selectedTask && (
        <div className="mt-2 text-xs text-base-content/60 space-y-1 bg-base-200 p-3 rounded-lg">
          {selectedTask.name && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Task Name:</span>
              <span className="font-mono">{selectedTask.name}</span>
            </div>
          )}
          {selectedTask.task_id && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Task ID:</span>
              <a
                href={`/task-results/${selectedTask.task_id}`}
                className="font-mono truncate link link-primary"
              >
                {selectedTask.task_id}
              </a>
            </div>
          )}
          {selectedTask.end_at && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Calibrated At:</span>
              <span>{formatDateTime(selectedTask.end_at)}</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <span className="font-semibold">Status:</span>
            <span
              className={`badge badge-xs ${
                selectedTask.status === "completed"
                  ? "badge-success"
                  : selectedTask.status === "failed"
                    ? "badge-error"
                    : "badge-warning"
              }`}
            >
              {selectedTask.status}
            </span>
          </div>
          {selectedTask.message && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Message:</span>
              <span>{selectedTask.message}</span>
            </div>
          )}
          {/* Provenance link and Ask AI */}
          <div className="pt-2 mt-2 border-t border-base-300 flex items-center gap-2">
            <Link
              href={(() => {
                const outputs = selectedTask.output_parameters
                  ? Object.entries(selectedTask.output_parameters)
                  : [];
                const inputs = selectedTask.input_parameters
                  ? Object.entries(selectedTask.input_parameters)
                  : [];
                const [key, paramValue] =
                  (outputs[0] as
                    | [string, Record<string, unknown>]
                    | undefined) ??
                  (inputs[0] as
                    | [string, Record<string, unknown>]
                    | undefined) ??
                  [];
                if (key && paramValue) {
                  const parameterName =
                    (paramValue?.parameter_name as string | undefined) || key;
                  return buildProvenanceUrl(parameterName, qid);
                }
                return "/provenance";
              })()}
              className="btn btn-xs btn-outline gap-1"
            >
              <GitBranch className="h-3 w-3" />
              View Provenance Lineage
            </Link>
            {analysisContext && (
              <button
                onClick={() => openAnalysisChat(analysisContext)}
                className="btn btn-xs btn-primary gap-1"
              >
                <Bot className="h-3 w-3" />
                Ask AI
              </button>
            )}
          </div>
        </div>
      )}

      {/* Parameters */}
      {selectedTask && (
        <div className="flex flex-col gap-2 mt-2">
          {selectedTask.input_parameters &&
            Object.keys(selectedTask.input_parameters).length > 0 && (
              <ParametersTable
                title="Input Parameters"
                parameters={
                  selectedTask.input_parameters as Record<string, unknown>
                }
              />
            )}
          {selectedTask.output_parameters &&
            Object.keys(selectedTask.output_parameters).length > 0 && (
              <ParametersTable
                title="Output Parameters"
                parameters={
                  selectedTask.output_parameters as Record<string, unknown>
                }
              />
            )}
          {selectedTask.run_parameters &&
            Object.keys(selectedTask.run_parameters).length > 0 && (
              <ParametersTable
                title="Run Parameters"
                parameters={
                  selectedTask.run_parameters as Record<string, unknown>
                }
              />
            )}
        </div>
      )}

      {/* Issues */}
      {selectedTask?.task_id && (
        <TaskResultIssues taskId={selectedTask.task_id} />
      )}
    </div>
  );

  return (
    <dialog
      ref={modalRef}
      className="modal modal-bottom sm:modal-middle"
      onClose={onClose}
    >
      <div className="modal-box w-full sm:w-11/12 max-w-5xl bg-base-100 p-3 sm:p-6">
        <div className="flex justify-between items-center mb-3 sm:mb-4">
          <h3 className="font-bold text-base sm:text-lg truncate pr-2">
            {taskName} - QID {qid}
          </h3>
          <button
            onClick={onClose}
            className="btn btn-sm btn-circle btn-ghost flex-shrink-0"
          >
            ✕
          </button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center h-48 sm:h-96">
            <span className="loading loading-spinner loading-lg"></span>
          </div>
        ) : isError || historyArray.length === 0 ? (
          <div className="alert alert-info text-sm">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              className="stroke-current shrink-0 w-5 h-5 sm:w-6 sm:h-6"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>No history available</span>
          </div>
        ) : (
          <div className="h-full min-h-0 flex flex-col max-h-[70vh] sm:max-h-[75vh]">
            {/* Mobile Tabs */}
            <div className="lg:hidden mb-3 shrink-0">
              <div className="tabs tabs-boxed bg-base-200">
                <button
                  className={`tab gap-1 ${mobileTab === "history" ? "tab-active" : ""}`}
                  onClick={() => setMobileTab("history")}
                >
                  <History className="h-3 w-3" />
                  History
                </button>
                <button
                  className={`tab gap-1 ${mobileTab === "details" ? "tab-active" : ""}`}
                  onClick={() => setMobileTab("details")}
                >
                  <FileText className="h-3 w-3" />
                  Details
                </button>
              </div>
            </div>

            {/* Mobile Content */}
            <div className="lg:hidden flex-1 min-h-0 overflow-y-auto">
              {mobileTab === "history" && renderHistoryList()}
              {mobileTab === "details" && renderTaskDetails()}
            </div>

            {/* Desktop Layout */}
            <div className="hidden lg:flex gap-4 h-full min-h-0">
              <div className="w-1/3 flex flex-col min-h-0 border-r border-base-300 pr-4">
                {renderHistoryList()}
              </div>
              <div className="w-2/3 overflow-y-auto min-h-0">
                {renderTaskDetails()}
              </div>
            </div>
          </div>
        )}
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}
