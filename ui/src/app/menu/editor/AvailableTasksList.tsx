import { TaskResponse } from "@/schemas";
import DraggableTask from "./DraggableTask";

interface AvailableTasksListProps {
  tasks: TaskResponse[];
  onTaskSelect: (task: TaskResponse) => void;
}

export default function AvailableTasksList({
  tasks,
  onTaskSelect,
}: AvailableTasksListProps) {
  // Group tasks by type
  const groupedTasks = tasks.reduce(
    (acc: { [key: string]: TaskResponse[] }, task: TaskResponse) => {
      const type = task.task_type || "other";
      if (!acc[type]) {
        acc[type] = [];
      }
      acc[type].push(task);
      return acc;
    },
    {}
  );

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="px-4 py-3 border-b border-base-300 flex justify-between items-center shrink-0 bg-base-200/90">
        <h2 className="font-bold text-sm uppercase tracking-wide">
          Available Tasks
        </h2>
      </div>
      <div className="overflow-y-auto flex-1 p-4">
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
