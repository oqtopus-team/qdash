import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { BsTrash } from "react-icons/bs";

import type { TaskResponse } from "@/schemas";

interface SortableTaskItemProps {
  task: TaskResponse;
  onRemove: (taskName: string) => void;
}

export default function SortableTaskItem({
  task,
  onRemove,
}: SortableTaskItemProps) {
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({
      id: task.name,
    });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className="p-3 rounded-lg bg-base-100 border border-base-300 hover:border-primary group shadow-sm touch-none"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <h4 className="font-medium">{task.name}</h4>
            <div className="badge badge-primary badge-outline">
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
            onRemove(task.name);
          }}
          className="btn btn-ghost btn-sm btn-square hover:bg-error/10 hover:text-error opacity-0 group-hover:opacity-100 transition-opacity"
          aria-label={`Remove ${task.name}`}
          onPointerDown={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
          onTouchStart={(e) => e.stopPropagation()}
        >
          <BsTrash className="text-base" />
        </button>
      </div>
    </div>
  );
}
