interface TaskDetailListProps {
  tasks: Record<string, any>;
  taskOrder: string[];
  selectedTask: string | null;
  onTaskSelect: (taskName: string, content: any) => void;
}

function TaskItem({
  id,
  isSelected,
  onSelect,
}: {
  id: string;
  content: any;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <div
      className={`group flex items-center gap-2 p-2 rounded cursor-pointer transition-colors ${
        isSelected ? "bg-primary/10" : "hover:bg-base-300/50"
      }`}
      onClick={onSelect}
    >
      <span className="font-medium text-sm truncate">{id}</span>
    </div>
  );
}

export default function TaskDetailList({
  tasks,
  taskOrder,
  selectedTask,
  onTaskSelect,
}: TaskDetailListProps) {
  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="space-y-1">
          {taskOrder.map((taskName) => (
            <TaskItem
              key={taskName}
              id={taskName}
              content={tasks[taskName]}
              isSelected={selectedTask === taskName}
              onSelect={() => onTaskSelect(taskName, tasks[taskName])}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
