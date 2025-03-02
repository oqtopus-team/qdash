"use client";

import { ServerRoutersChipTask, MuxDetailResponseDetail } from "@/schemas";
import { TaskResultGrid } from "../TaskResultGrid";

interface MuxCardProps {
  muxId: string;
  muxDetail: {
    mux_id: number;
    detail: MuxDetailResponseDetail;
  };
  layoutMode: "list" | "grid";
  isExpanded: boolean;
  onToggleExpand: () => void;
}

export function MuxCard({
  muxId,
  muxDetail,
  layoutMode,
  isExpanded,
  onToggleExpand,
}: MuxCardProps) {
  // Get latest update time info from tasks
  const getLatestUpdateInfo = (
    detail: MuxDetailResponseDetail
  ): { time: Date; isRecent: boolean } => {
    let latestTime = new Date(0);

    Object.values(detail).forEach((tasksByName) => {
      Object.values(
        tasksByName as { [key: string]: ServerRoutersChipTask }
      ).forEach((task) => {
        if (task.end_at) {
          const taskEndTime = new Date(task.end_at);
          if (taskEndTime > latestTime) {
            latestTime = taskEndTime;
          }
        }
      });
    });

    const now = new Date();
    const isRecent = now.getTime() - latestTime.getTime() < 24 * 60 * 60 * 1000;

    return { time: latestTime, isRecent };
  };

  // Format relative time
  const formatRelativeTime = (date: Date): string => {
    const now = new Date();
    const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diffInSeconds < 60) return "just now";
    if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
    if (diffInSeconds < 86400)
      return `${Math.floor(diffInSeconds / 3600)}h ago`;
    return date.toLocaleString();
  };

  // Get all QIDs from mux detail
  const getQids = (detail: MuxDetailResponseDetail): string[] => {
    const qids = new Set<string>();
    Object.keys(detail).forEach((qid) => qids.add(qid));
    return Array.from(qids).sort((a, b) => Number(a) - Number(b));
  };

  // Group tasks by name for each mux
  const getTaskGroups = (detail: MuxDetailResponseDetail) => {
    const taskGroups: {
      [key: string]: { [key: string]: ServerRoutersChipTask };
    } = {};

    Object.entries(detail).forEach(([qid, tasksByName]) => {
      Object.entries(
        tasksByName as { [key: string]: ServerRoutersChipTask }
      ).forEach(([taskName, task]) => {
        if (task.status !== "completed" && task.status !== "failed") return;

        if (!taskGroups[taskName]) {
          taskGroups[taskName] = {};
        }
        taskGroups[taskName][qid] = task;
      });
    });

    return taskGroups;
  };

  const updateInfo = getLatestUpdateInfo(muxDetail.detail);
  const lastUpdateText =
    updateInfo.time.getTime() === 0
      ? "No updates"
      : formatRelativeTime(updateInfo.time);
  const qids = getQids(muxDetail.detail);
  const taskGroups = getTaskGroups(muxDetail.detail);

  return (
    <div
      className={`bg-base-100 shadow-lg rounded-xl overflow-hidden transition-all duration-200 ${
        updateInfo.isRecent
          ? "border-2 border-primary animate-pulse-light"
          : "bg-base-200"
      } ${layoutMode === "grid" ? "min-h-[3rem]" : ""}`}
      style={{
        gridColumn: isExpanded ? "1 / -1" : "auto",
      }}
    >
      <div
        className="p-4 cursor-pointer hover:bg-base-200/50 transition-colors"
        onClick={onToggleExpand}
      >
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="text-xl font-medium">
              MUX {String(muxDetail.mux_id)}
            </div>
            {updateInfo.isRecent && (
              <div className="badge badge-primary gap-2 rounded-lg">
                <div className="w-2 h-2 bg-primary-content rounded-full animate-ping" />
                New
              </div>
            )}
            <div className="badge badge-ghost gap-2 rounded-lg">
              {Object.keys(taskGroups).length} Tasks
            </div>
          </div>
          <div
            className={`text-sm ${
              updateInfo.isRecent
                ? "text-primary font-medium"
                : "text-base-content/60"
            }`}
          >
            Last updated: {lastUpdateText}
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="p-4 border-t">
          <TaskResultGrid taskGroups={taskGroups} qids={qids} muxId={muxId} />
        </div>
      )}
    </div>
  );
}
