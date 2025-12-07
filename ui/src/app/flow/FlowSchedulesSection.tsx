"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import { listAllFlowSchedules } from "@/client/flow/flow";

export function FlowSchedulesSection() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["flow-schedules"],
    queryFn: () => listAllFlowSchedules(),
    refetchInterval: 10000, // Refresh every 10 seconds
  });

  const schedules = data?.data?.schedules || [];

  if (isLoading) {
    return (
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <h2 className="card-title">Scheduled Flows</h2>
          <div className="flex justify-center py-4">
            <span className="loading loading-spinner loading-md"></span>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <h2 className="card-title">Scheduled Flows</h2>
          <div className="alert alert-error">
            <span>Failed to load schedules: {error.message}</span>
          </div>
        </div>
      </div>
    );
  }

  if (schedules.length === 0) {
    return (
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <h2 className="card-title">Scheduled Flows</h2>
          <p className="text-sm opacity-70">
            No scheduled flows. Create a schedule from the Flow editor to
            automate executions.
          </p>
        </div>
      </div>
    );
  }

  // Group schedules by type
  const cronSchedules = schedules.filter((s) => s.schedule_type === "cron");
  const oneTimeSchedules = schedules
    .filter((s) => s.schedule_type === "one-time")
    .sort((a, b) => {
      // Sort by next_run time (earliest first)
      if (!a.next_run) return 1;
      if (!b.next_run) return -1;
      return new Date(a.next_run).getTime() - new Date(b.next_run).getTime();
    })
    .slice(0, 10); // Show only the next 10 upcoming one-time schedules

  return (
    <div className="card bg-base-100 shadow-xl">
      <div className="card-body">
        <h2 className="card-title">Scheduled Flows</h2>

        {/* Cron Schedules */}
        {cronSchedules.length > 0 && (
          <div className="mb-4">
            <h3 className="text-sm font-semibold opacity-70 mb-2">
              Recurring (Cron)
            </h3>
            <div className="space-y-2">
              {cronSchedules.map((schedule) => (
                <Link
                  key={schedule.schedule_id}
                  href={`/flow/${schedule.flow_name}`}
                  className={`block p-3 rounded hover:bg-base-300 transition-colors ${
                    schedule.active ? "bg-base-200" : "bg-base-300 opacity-60"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">
                          {schedule.flow_name}
                        </span>
                        <span
                          className={`badge badge-sm ${
                            schedule.active ? "badge-success" : "badge-ghost"
                          }`}
                        >
                          {schedule.active ? "Active" : "Inactive"}
                        </span>
                      </div>
                      {schedule.cron && (
                        <p className="text-xs font-mono opacity-70 mt-1">
                          {schedule.cron}
                        </p>
                      )}
                      <p className="text-xs opacity-60 mt-1">
                        Created:{" "}
                        {new Date(schedule.created_at).toLocaleString()}
                      </p>
                    </div>
                    <div className="text-xs opacity-60">→</div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* One-time Schedules */}
        {oneTimeSchedules.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold opacity-70 mb-2">
              One-time Executions
            </h3>
            <div className="space-y-2">
              {oneTimeSchedules.map((schedule) => (
                <Link
                  key={schedule.schedule_id}
                  href={`/flow/${schedule.flow_name}`}
                  className={`block p-3 rounded hover:bg-base-300 transition-colors ${
                    schedule.active ? "bg-base-200" : "bg-base-300 opacity-60"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">
                          {schedule.flow_name}
                        </span>
                        <span className="badge badge-sm badge-secondary">
                          One-time
                        </span>
                      </div>
                      {schedule.next_run && (
                        <p className="text-xs opacity-70 mt-1">
                          Scheduled:{" "}
                          {new Date(schedule.next_run).toLocaleString()}
                        </p>
                      )}
                    </div>
                    <div className="text-xs opacity-60">→</div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
