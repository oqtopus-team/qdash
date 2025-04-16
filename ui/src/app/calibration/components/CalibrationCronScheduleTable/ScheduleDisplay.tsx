"use client";

import type { CreateMenuRequestSchedule } from "@/schemas/createMenuRequestSchedule";

interface ScheduleDisplayProps {
  schedule: CreateMenuRequestSchedule;
}

export function ScheduleDisplay({ schedule }: ScheduleDisplayProps) {
  if ("serial" in schedule) {
    return (
      <div className="pl-4 border-l-2 border-base-300">
        <p className="text-base-content/80 font-medium mb-2">
          Serial Execution
        </p>
        <div className="space-y-2">
          {schedule.serial.map((node, index) => (
            <div key={index}>
              {typeof node === "string" ? (
                <p className="text-base-content/80">{node}</p>
              ) : (
                <ScheduleDisplay schedule={node} />
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if ("parallel" in schedule) {
    return (
      <div className="pl-4 border-l-2 border-primary">
        <p className="text-base-content/80 font-medium mb-2">
          Parallel Execution
        </p>
        <div className="space-y-2">
          {schedule.parallel.map((node, index) => (
            <ScheduleDisplay key={index} schedule={node} />
          ))}
        </div>
      </div>
    );
  }

  if ("batch" in schedule) {
    return (
      <div className="pl-4 border-l-2 border-secondary">
        <p className="text-base-content/80 font-medium mb-2">Batch Execution</p>
        <div className="space-y-1">
          {schedule.batch.map((task, index) => (
            <p key={index} className="text-base-content/80">
              {task}
            </p>
          ))}
        </div>
      </div>
    );
  }

  return null;
}
