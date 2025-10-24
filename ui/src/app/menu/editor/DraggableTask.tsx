import { BsPlusCircle } from "react-icons/bs";

import type { TaskResponse } from "@/schemas";

interface DraggableTaskProps {
  task: TaskResponse;
  onClick?: () => void;
}

export default function DraggableTask({ task, onClick }: DraggableTaskProps) {
  return (
    <div className="p-3 rounded-lg border border-base-300 hover:border-primary transition-colors group bg-base-100">
      <div className="flex items-center justify-between gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <h4 className="font-medium break-all">{task.name}</h4>
            <div className="badge badge-primary badge-outline shrink-0">
              {task.task_type}
            </div>
          </div>
          {task.description && (
            <p className="text-sm text-base-content/70 line-clamp-2">
              {task.description}
            </p>
          )}
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onClick?.();
          }}
          className="btn btn-primary btn-sm btn-circle transition-colors shrink-0"
          title="Add task"
        >
          <BsPlusCircle className="text-lg" />
        </button>
      </div>
    </div>
  );
}
