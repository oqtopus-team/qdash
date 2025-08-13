import DraggableTask from "./DraggableTask";

import type { TaskResponse } from "@/schemas";

interface AvailableTasksListProps {
  tasks: TaskResponse[];
  onTaskSelect: (task: TaskResponse) => void;
}

export default function AvailableTasksList({
  tasks,
  onTaskSelect,
}: AvailableTasksListProps) {
  // Group tasks by type while maintaining original order
  const groupedTasks = tasks.reduce(
    (acc: { [key: string]: TaskResponse[] }, task: TaskResponse) => {
      const type = task.task_type || "other";
      if (!acc[type]) {
        acc[type] = [];
      }
      // Add task to the group while maintaining the original order
      const insertIndex = acc[type].findIndex(
        (t) => tasks.indexOf(t) > tasks.indexOf(task),
      );
      if (insertIndex === -1) {
        acc[type].push(task);
      } else {
        acc[type].splice(insertIndex, 0, task);
      }
      return acc;
    },
    {},
  );

  return (
    <div className="h-full flex flex-col">
      <h2 className="font-bold text-lg mb-4">Available Tasks</h2>
      <div className="overflow-y-auto overflow-x-hidden flex-1">
        {Object.entries(groupedTasks).map(([type, tasks]) => (
          <div key={type} className="mb-6 last:mb-0">
            <h3 className="text-lg font-semibold mb-3 capitalize">{type}</h3>
            <div className="space-y-2">
              {tasks.map((task) => (
                <DraggableTask
                  key={task.name}
                  task={task}
                  onClick={() => onTaskSelect(task)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
