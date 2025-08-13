"use client";

import Select from "react-select";

import type { TaskResponse } from "@/schemas";
import type { SingleValue } from "react-select";

interface TaskOption {
  value: string;
  label: string;
}

interface TaskSelectorProps {
  tasks: TaskResponse[];
  selectedTask: string;
  onTaskSelect: (taskId: string) => void;
  disabled?: boolean;
}

export function TaskSelector({
  tasks,
  selectedTask,
  onTaskSelect,
  disabled = false,
}: TaskSelectorProps) {
  const options: TaskOption[] = tasks.map((task) => ({
    value: task.name,
    label: task.name,
  }));

  const handleChange = (option: SingleValue<TaskOption>) => {
    if (option) {
      onTaskSelect(option.value);
    }
  };

  return (
    <div className="w-full max-w-xs">
      <label className="label">
        <span className="label-text font-medium">Select Task</span>
      </label>
      <Select<TaskOption>
        options={options}
        value={options.find((option) => option.value === selectedTask)}
        onChange={handleChange}
        placeholder="Select a task"
        className="text-base-content"
        isDisabled={disabled}
      />
    </div>
  );
}
