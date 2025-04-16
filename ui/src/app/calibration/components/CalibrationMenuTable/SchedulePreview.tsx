"use client";

import type { CreateMenuRequestSchedule } from "@/schemas/createMenuRequestSchedule";

interface SchedulePreviewProps {
  schedule: CreateMenuRequestSchedule;
}

export function SchedulePreview({ schedule }: SchedulePreviewProps) {
  if ("serial" in schedule) {
    return (
      <div className="text-sm text-base-content/70">
        Serial: {schedule.serial.length} tasks
      </div>
    );
  }

  if ("parallel" in schedule) {
    return (
      <div className="text-sm text-base-content/70">
        Parallel: {schedule.parallel.length} tasks
      </div>
    );
  }

  if ("batch" in schedule) {
    return (
      <div className="text-sm text-base-content/70">
        Batch: {schedule.batch.length} tasks
      </div>
    );
  }

  return null;
}
