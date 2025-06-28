import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { BsGripVertical, BsTrash, BsCheck } from "react-icons/bs";
import { useState, useCallback, useEffect } from "react";

interface TaskDetailListProps {
  tasks: Record<string, any>;
  selectedTask: string | null;
  onTaskSelect: (taskName: string, content: any) => void;
  onDragEnd: (result: any) => void;
  onDeleteTask?: (taskName: string) => void;
  onBulkDeleteTasks?: (taskNames: string[]) => void;
}

function SortableItem({
  id,
  content,
  isSelected,
  isChecked,
  onSelect,
  onDelete,
  onCheckboxChange,
}: {
  id: string;
  content: any;
  isSelected: boolean;
  isChecked: boolean;
  onSelect: () => void;
  onDelete?: (e: React.MouseEvent) => void;
  onCheckboxChange: (checked: boolean) => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`group flex items-center gap-2 p-2 rounded cursor-pointer transition-colors ${
        isSelected ? "bg-primary/10" : "hover:bg-base-300/50"
      } ${isDragging ? "shadow-lg bg-base-300/50" : ""}`}
    >
      <div
        className="flex items-center justify-center w-5 h-5 rounded border border-base-content/20 hover:border-primary transition-colors cursor-pointer shrink-0"
        onClick={(e) => {
          e.stopPropagation();
          onCheckboxChange(!isChecked);
        }}
      >
        {isChecked && <BsCheck className="text-primary text-base" />}
      </div>
      <div
        {...attributes}
        {...listeners}
        className="text-base-content/50 hover:text-base-content/70 transition-colors"
      >
        <BsGripVertical className="text-lg" />
      </div>
      <span
        className="font-medium text-sm truncate cursor-pointer"
        onClick={onSelect}
      >
        {id}
      </span>
      {onDelete && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete(e);
          }}
          className="ml-auto btn btn-ghost btn-xs btn-square hover:text-error opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <BsTrash className="text-sm" />
        </button>
      )}
    </div>
  );
}

export default function TaskDetailList({
  tasks,
  selectedTask,
  onTaskSelect,
  onDragEnd,
  onDeleteTask,
  onBulkDeleteTasks,
}: TaskDetailListProps) {
  const taskNames = Object.keys(tasks);
  const [selectedTasks, setSelectedTasks] = useState<Set<string>>(new Set());

  // Clear selection when tasks change
  useEffect(() => {
    setSelectedTasks(new Set());
  }, [tasks]);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      onDragEnd({
        source: { index: taskNames.indexOf(active.id.toString()) },
        destination: { index: taskNames.indexOf(over.id.toString()) },
      });
    }
  };

  const handleCheckboxChange = useCallback(
    (taskName: string, checked: boolean) => {
      setSelectedTasks((prev) => {
        const next = new Set(prev);
        if (checked) {
          next.add(taskName);
        } else {
          next.delete(taskName);
        }
        return next;
      });
    },
    []
  );

  const handleSelectAll = useCallback(() => {
    setSelectedTasks((prev) => {
      if (prev.size === taskNames.length) {
        return new Set();
      }
      return new Set(taskNames);
    });
  }, [taskNames]);

  return (
    <div className="h-full flex flex-col">
      {selectedTasks.size > 0 && (
        <div className="px-4 py-2 border-b border-base-300 bg-base-200/90 flex items-center gap-4">
          <div className="text-sm font-medium">
            {selectedTasks.size} selected
          </div>
          <div className="flex-1" />
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setSelectedTasks(new Set())}
          >
            Clear
          </button>
          {onBulkDeleteTasks && (
            <button
              className="btn btn-error btn-sm"
              onClick={() => onBulkDeleteTasks(Array.from(selectedTasks))}
            >
              Delete
            </button>
          )}
        </div>
      )}
      <div className="flex-1 overflow-y-auto">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={taskNames}
            strategy={verticalListSortingStrategy}
          >
            <div className="p-2 space-y-1">
              {taskNames.map((taskName) => (
                <SortableItem
                  key={taskName}
                  id={taskName}
                  content={tasks[taskName]}
                  isSelected={selectedTask === taskName}
                  isChecked={selectedTasks.has(taskName)}
                  onSelect={() => onTaskSelect(taskName, tasks[taskName])}
                  onDelete={
                    onDeleteTask
                      ? (e) => {
                          e.stopPropagation();
                          onDeleteTask(taskName);
                        }
                      : undefined
                  }
                  onCheckboxChange={(checked) =>
                    handleCheckboxChange(taskName, checked)
                  }
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      </div>
    </div>
  );
}
