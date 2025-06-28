import { DndContext, DragEndEvent } from "@dnd-kit/core";
import { useFetchAllTasks } from "@/client/task/task";
import {
  SortableContext,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import SortableTaskItem from "./SortableTaskItem";
import { TaskResponse } from "@/schemas";
import { useState, useEffect } from "react";
import { BsPlus } from "react-icons/bs";
import AvailableTasksList from "./AvailableTasksList";
import DroppableTaskList from "./DroppableTaskList";

interface TaskSelectModalProps {
  onClose: () => void;
  onSelect: (tasks: TaskResponse[]) => void;
  selectedTaskNames?: string[];
}

const TaskSelectModal: React.FC<TaskSelectModalProps> = ({
  onClose,
  onSelect,
  selectedTaskNames = [],
}) => {
  const { data: tasksData } = useFetchAllTasks();
  const [selectedTasks, setSelectedTasks] = useState<TaskResponse[]>([]);

  // 選択されていないタスクのみをフィルタリング
  const availableTasks =
    tasksData?.data?.tasks?.filter(
      (task: TaskResponse) => !selectedTasks.some((t) => t.name === task.name)
    ) ?? [];

  // 初期化時に既存のタスクを選択状態にする
  useEffect(() => {
    if (tasksData?.data?.tasks) {
      // Set selected tasks with a new array reference
      const existingTasks = [...tasksData.data.tasks].filter(
        (task: TaskResponse) => selectedTaskNames.includes(task.name)
      );
      setSelectedTasks(existingTasks);
    }
  }, [tasksData, selectedTaskNames]);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || !active.data.current) return;

    // If dragging from available tasks to task list
    if (over.id === "task-list" && "task_type" in active.data.current) {
      const task = active.data.current as TaskResponse;
      if (!selectedTasks.find((t) => t.name === task.name)) {
        setSelectedTasks([...selectedTasks, task]);
      }
    }
    // If reordering within selected tasks
    else if (active.id !== over.id) {
      const oldIndex = selectedTasks.findIndex((t) => t.name === active.id);
      const newIndex = selectedTasks.findIndex((t) => t.name === over.id);

      if (oldIndex !== -1 && newIndex !== -1) {
        const newTasks = [...selectedTasks];
        const [movedTask] = newTasks.splice(oldIndex, 1);
        newTasks.splice(newIndex, 0, movedTask);
        setSelectedTasks(newTasks);
      }
    }
  };

  const handleTaskClick = (task: TaskResponse) => {
    if (!selectedTasks.find((t) => t.name === task.name)) {
      setSelectedTasks([...selectedTasks, task]);
    }
  };

  const handleRemoveTask = (taskName: string) => {
    setSelectedTasks(selectedTasks.filter((t) => t.name !== taskName));
  };

  return (
    <DndContext onDragEnd={handleDragEnd}>
      <div
        className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm p-4"
        onClick={onClose}
      >
        <div
          className="bg-base-100 rounded-xl w-full max-w-5xl max-h-[85vh] overflow-hidden flex flex-col shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="px-6 py-4 border-b border-base-300 flex items-center justify-between bg-base-100/80 backdrop-blur supports-[backdrop-filter]:bg-base-100/60">
            <h2 className="text-2xl font-bold">Edit Tasks</h2>
            <div className="flex items-center gap-2">
              <button
                className="btn btn-primary btn-sm"
                onClick={() => {
                  onSelect(selectedTasks);
                  onClose();
                }}
                disabled={selectedTasks.length === 0}
              >
                Save
              </button>
              <button
                onClick={onClose}
                className="btn btn-ghost btn-sm btn-square hover:rotate-90 transition-transform"
              >
                <BsPlus className="text-xl rotate-45" />
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-hidden flex gap-4 p-4">
            {/* Left side: Available tasks */}
            <div className="w-1/2">
              {availableTasks.length > 0 && (
                <AvailableTasksList
                  tasks={availableTasks}
                  onTaskSelect={handleTaskClick}
                />
              )}
            </div>

            {/* Right side: Selected tasks */}
            <div className="w-1/2 flex flex-col overflow-hidden">
              <div className="flex items-center justify-between mb-4 shrink-0">
                <h3 className="text-lg font-semibold">Selected Tasks</h3>
                <span className="text-sm text-base-content/70">
                  {selectedTasks.length} tasks
                </span>
              </div>
              <DroppableTaskList
                id="task-list"
                className="flex-1 overflow-y-auto"
              >
                <div className="space-y-2">
                  <SortableContext
                    items={selectedTasks.map((task) => task.name)}
                    strategy={verticalListSortingStrategy}
                  >
                    {selectedTasks.map((task) => (
                      <SortableTaskItem
                        key={task.name}
                        task={task}
                        onRemove={handleRemoveTask}
                      />
                    ))}
                  </SortableContext>
                </div>
                {selectedTasks.length === 0 && (
                  <div className="text-base-content/50 text-center py-8">
                    <svg
                      className="mx-auto h-12 w-12 text-base-content/30"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      aria-hidden="true"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                      />
                    </svg>
                    <h3 className="mt-2 text-sm font-medium">
                      No tasks selected
                    </h3>
                    <p className="mt-1 text-sm text-base-content/70">
                      Drag tasks from the left or click to add them
                    </p>
                  </div>
                )}
              </DroppableTaskList>
            </div>
          </div>
        </div>
      </div>
    </DndContext>
  );
};

export default TaskSelectModal;
