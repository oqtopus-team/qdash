"use client";

import Select from "react-select";

import type { SingleValue } from "react-select";

interface TaskOption {
  value: string;
  label: string;
}

// Generic task type that works with both TaskResponse and TaskInfo
interface TaskWithName {
  name: string;
}

interface TaskSelectorProps {
  tasks: TaskWithName[];
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
    <Select<TaskOption>
      options={options}
      value={options.find((option) => option.value === selectedTask)}
      onChange={handleChange}
      placeholder="Select a task"
      className="text-base-content w-full"
      isDisabled={disabled}
    />
  );
}
