"use client";

import { useState } from "react";
import { toast } from "react-toastify";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  scheduleFlow,
  listFlowSchedules,
  deleteFlowSchedule,
  updateFlowSchedule,
} from "@/client/flow/flow";
import type { ScheduleFlowRequest, FlowScheduleSummary } from "@/schemas";

interface FlowSchedulePanelProps {
  flowName: string;
}

export function FlowSchedulePanel({ flowName }: FlowSchedulePanelProps) {
  const queryClient = useQueryClient();
  const [cronExpression, setCronExpression] = useState("");
  const [scheduledTime, setScheduledTime] = useState("");
  const [scheduleType, setScheduleType] = useState<"cron" | "one-time">("cron");
  const [isActive, setIsActive] = useState(true);

  // Fetch schedules for this flow
  const { data: schedulesData, isLoading } = useQuery({
    queryKey: ["flow-schedules", flowName],
    queryFn: () => listFlowSchedules(flowName),
    refetchInterval: 10000, // Refresh every 10 seconds
  });

  const schedules =
    (schedulesData?.data &&
      "schedules" in schedulesData.data &&
      schedulesData.data.schedules) ||
    [];

  // Create schedule mutation
  const createScheduleMutation = useMutation({
    mutationFn: ({ data }: { data: ScheduleFlowRequest }) =>
      scheduleFlow(flowName, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flow-schedules", flowName] });
      queryClient.invalidateQueries({ queryKey: ["flow-schedules"] });
      toast.success("Schedule created successfully!");
      setCronExpression("");
      setScheduledTime("");
    },
    onError: (error: any) => {
      toast.error(`Failed to create schedule: ${error.message}`);
    },
  });

  // Delete schedule mutation
  const deleteScheduleMutation = useMutation({
    mutationFn: ({ scheduleId }: { scheduleId: string }) =>
      deleteFlowSchedule(scheduleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flow-schedules", flowName] });
      queryClient.invalidateQueries({ queryKey: ["flow-schedules"] });
      toast.success("Schedule deleted successfully!");
    },
    onError: (error: any) => {
      toast.error(`Failed to delete schedule: ${error.message}`);
    },
  });

  // Update schedule mutation (toggle active)
  const updateScheduleMutation = useMutation({
    mutationFn: ({
      scheduleId,
      data,
    }: {
      scheduleId: string;
      data: { active: boolean };
    }) => updateFlowSchedule(scheduleId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flow-schedules", flowName] });
      queryClient.invalidateQueries({ queryKey: ["flow-schedules"] });
      toast.success("Schedule updated successfully!");
    },
    onError: (error: any) => {
      toast.error(`Failed to update schedule: ${error.message}`);
    },
  });

  const handleCreateSchedule = () => {
    if (scheduleType === "cron") {
      if (!cronExpression.trim()) {
        toast.error("Please enter a cron expression");
        return;
      }
      createScheduleMutation.mutate({
        data: {
          cron: cronExpression.trim(),
          active: isActive,
          parameters: {},
        },
      });
    } else {
      if (!scheduledTime.trim()) {
        toast.error("Please select a scheduled time");
        return;
      }
      createScheduleMutation.mutate({
        data: {
          scheduled_time: scheduledTime.trim(),
          parameters: {},
        },
      });
    }
  };

  const handleToggleActive = (schedule: FlowScheduleSummary) => {
    if (schedule.schedule_type === "cron") {
      updateScheduleMutation.mutate({
        scheduleId: schedule.schedule_id,
        data: {
          active: !schedule.active,
        },
      });
    }
  };

  const handleDeleteSchedule = (scheduleId: string) => {
    if (confirm("Are you sure you want to delete this schedule?")) {
      deleteScheduleMutation.mutate({ scheduleId });
    }
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-white">SCHEDULE</h3>

      {/* Schedule Type Toggle */}
      <div className="flex gap-2">
        <button
          onClick={() => setScheduleType("cron")}
          className={`flex-1 px-2 py-1 text-xs rounded transition-colors ${
            scheduleType === "cron"
              ? "bg-[#0e639c] text-white"
              : "bg-[#3c3c3c] text-gray-400"
          }`}
        >
          Cron
        </button>
        <button
          onClick={() => setScheduleType("one-time")}
          className={`flex-1 px-2 py-1 text-xs rounded transition-colors ${
            scheduleType === "one-time"
              ? "bg-[#0e639c] text-white"
              : "bg-[#3c3c3c] text-gray-400"
          }`}
        >
          One-time
        </button>
      </div>

      {/* Cron Schedule Form */}
      {scheduleType === "cron" && (
        <div className="space-y-3">
          <div className="form-control">
            <label className="label">
              <span className="label-text text-xs text-gray-400">
                Cron Expression
              </span>
            </label>
            <input
              type="text"
              placeholder="0 2 * * * (daily at 2:00 JST)"
              className="input input-bordered input-sm bg-[#3c3c3c] border-[#3e3e3e] text-white font-mono text-xs"
              value={cronExpression}
              onChange={(e) => setCronExpression(e.target.value)}
            />
            <label className="label">
              <span className="label-text-alt text-xs text-gray-500">
                Timezone: Asia/Tokyo (JST)
              </span>
            </label>
          </div>

          <div className="form-control">
            <label className="cursor-pointer label justify-start gap-2">
              <input
                type="checkbox"
                className="checkbox checkbox-sm checkbox-primary"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
              />
              <span className="label-text text-xs text-gray-400">
                Enable schedule immediately
              </span>
            </label>
            <label className="label">
              <span className="label-text-alt text-xs text-gray-500">
                If unchecked, the schedule will be created but paused
              </span>
            </label>
          </div>
        </div>
      )}

      {/* One-time Schedule Form */}
      {scheduleType === "one-time" && (
        <div className="space-y-3">
          <div className="form-control">
            <label className="label">
              <span className="label-text text-xs text-gray-400">
                Date (JST)
              </span>
            </label>
            <input
              type="date"
              className="input input-bordered input-sm bg-[#3c3c3c] border-[#3e3e3e] text-white text-xs [color-scheme:dark]"
              value={scheduledTime.split("T")[0] || ""}
              onChange={(e) => {
                const timePart = scheduledTime.split("T")[1] || "00:00";
                setScheduledTime(`${e.target.value}T${timePart}`);
              }}
            />
          </div>
          <div className="form-control">
            <label className="label">
              <span className="label-text text-xs text-gray-400">
                Time (JST)
              </span>
            </label>
            <div className="flex gap-2">
              <select
                className="select select-bordered select-sm bg-[#3c3c3c] border-[#3e3e3e] text-white text-xs flex-1"
                value={scheduledTime.split("T")[1]?.split(":")[0] || "00"}
                onChange={(e) => {
                  const date =
                    scheduledTime.split("T")[0] ||
                    new Date().toISOString().split("T")[0];
                  const currentMinute =
                    scheduledTime.split("T")[1]?.split(":")[1] || "00";
                  setScheduledTime(
                    `${date}T${e.target.value}:${currentMinute}`,
                  );
                }}
              >
                {Array.from({ length: 24 }, (_, i) => {
                  const hour = i.toString().padStart(2, "0");
                  return (
                    <option key={hour} value={hour}>
                      {hour}
                    </option>
                  );
                })}
              </select>
              <span className="text-white text-lg">:</span>
              <select
                className="select select-bordered select-sm bg-[#3c3c3c] border-[#3e3e3e] text-white text-xs flex-1"
                value={scheduledTime.split("T")[1]?.split(":")[1] || "00"}
                onChange={(e) => {
                  const date =
                    scheduledTime.split("T")[0] ||
                    new Date().toISOString().split("T")[0];
                  const currentHour =
                    scheduledTime.split("T")[1]?.split(":")[0] || "00";
                  setScheduledTime(`${date}T${currentHour}:${e.target.value}`);
                }}
              >
                {Array.from({ length: 12 }, (_, i) => {
                  const minute = (i * 5).toString().padStart(2, "0");
                  return (
                    <option key={minute} value={minute}>
                      {minute}
                    </option>
                  );
                })}
              </select>
            </div>
          </div>
          <label className="label py-0">
            <span className="label-text-alt text-xs text-gray-500">
              Timezone: Asia/Tokyo (JST)
            </span>
          </label>
        </div>
      )}

      {/* Create Button */}
      <button
        onClick={handleCreateSchedule}
        className="btn btn-sm btn-primary w-full"
        disabled={createScheduleMutation.isPending}
      >
        {createScheduleMutation.isPending ? (
          <span className="loading loading-spinner loading-xs"></span>
        ) : (
          `Create ${scheduleType === "cron" ? "Cron" : "One-time"} Schedule`
        )}
      </button>

      {/* Existing Schedules List */}
      <div className="divider my-2"></div>

      <h4 className="text-xs font-semibold text-gray-400 uppercase">
        Active Schedules
      </h4>

      {isLoading ? (
        <div className="flex justify-center py-4">
          <span className="loading loading-spinner loading-sm"></span>
        </div>
      ) : schedules.length === 0 ? (
        <p className="text-xs text-gray-500 text-center py-4">
          No schedules configured
        </p>
      ) : (
        <div className="space-y-2">
          {schedules.map((schedule) => (
            <div
              key={schedule.schedule_id}
              className={`rounded p-3 space-y-2 ${
                schedule.active ? "bg-[#3c3c3c]" : "bg-[#2a2a2a] opacity-60"
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={`badge badge-xs ${
                        schedule.schedule_type === "cron"
                          ? "badge-primary"
                          : "badge-secondary"
                      }`}
                    >
                      {schedule.schedule_type}
                    </span>
                    {!schedule.active && (
                      <span className="badge badge-xs badge-ghost">Paused</span>
                    )}
                  </div>
                  {schedule.cron && (
                    <p
                      className={`text-xs font-mono mt-1 ${
                        schedule.active ? "text-white" : "text-gray-500"
                      }`}
                    >
                      {schedule.cron}
                    </p>
                  )}
                  {schedule.next_run && schedule.active && (
                    <p className="text-xs text-gray-500 mt-1">
                      Next: {new Date(schedule.next_run).toLocaleString()}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {schedule.schedule_type === "cron" && (
                    <label className="flex items-center gap-1 cursor-pointer">
                      <input
                        type="checkbox"
                        className="toggle toggle-success toggle-xs"
                        checked={schedule.active}
                        onChange={() => handleToggleActive(schedule)}
                        disabled={updateScheduleMutation.isPending}
                      />
                    </label>
                  )}
                  <button
                    onClick={() => handleDeleteSchedule(schedule.schedule_id)}
                    className="btn btn-xs btn-ghost text-error"
                    disabled={deleteScheduleMutation.isPending}
                    title="Delete"
                  >
                    🗑
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Cron Expression Helper */}
      {scheduleType === "cron" && (
        <div className="bg-[#3c3c3c] rounded p-3 mt-4">
          <h5 className="text-xs font-semibold text-gray-400 mb-2">
            Cron Examples
          </h5>
          <div className="space-y-1 text-xs text-gray-500">
            <p>
              <code className="text-white">0 2 * * *</code> - Daily at 2:00 AM
            </p>
            <p>
              <code className="text-white">0 */6 * * *</code> - Every 6 hours
            </p>
            <p>
              <code className="text-white">0 0 * * 1</code> - Every Monday at
              midnight
            </p>
            <p>
              <code className="text-white">30 14 1 * *</code> - 1st of month at
              2:30 PM
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
