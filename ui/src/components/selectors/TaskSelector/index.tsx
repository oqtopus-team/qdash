"use client";

import Select from "react-select";

import type { SingleValue } from "react-select";

import { useSelectStyles } from "@/hooks/useSelectStyles";

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

const PLACEHOLDER = "Select a task";

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

  const { styles } = useSelectStyles<TaskOption>({
    labels: options.map((opt) => opt.label),
    placeholder: PLACEHOLDER,
  });

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
      placeholder={PLACEHOLDER}
      className="text-base-content"
      isDisabled={disabled}
      styles={styles}
    />
  );
}
