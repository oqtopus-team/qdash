import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { TaskResponse } from "@/schemas";
import { BsArrowRight } from "react-icons/bs";

interface DraggableTaskProps {
  task: TaskResponse;
  onClick?: () => void;
}

export default function DraggableTask({ task, onClick }: DraggableTaskProps) {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({
    id: task.name,
    data: task,
  });

  const style = transform
    ? {
        transform: CSS.Translate.toString(transform),
      }
    : undefined;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className="p-3 rounded-lg border border-base-300 hover:border-primary cursor-pointer transition-colors group touch-none"
      onClick={onClick}
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
        <div className="opacity-0 group-hover:opacity-100 transition-opacity">
          <BsArrowRight className="text-xl text-primary" />
        </div>
      </div>
    </div>
  );
}
