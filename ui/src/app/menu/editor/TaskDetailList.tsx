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
import { BsGripVertical } from "react-icons/bs";

interface TaskDetailListProps {
  tasks: Record<string, any>;
  selectedTask: string | null;
  onTaskSelect: (taskName: string, content: any) => void;
  onDragEnd: (result: any) => void;
}

function SortableItem({
  id,
  isSelected,
  onSelect,
}: {
  id: string;
  content: any;
  isSelected: boolean;
  onSelect: () => void;
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
      className={`flex items-center gap-2 p-2 rounded cursor-pointer transition-colors ${
        isSelected ? "bg-primary/10" : "hover:bg-base-300/50"
      } ${isDragging ? "shadow-lg bg-base-300/50" : ""}`}
      onClick={onSelect}
    >
      <div
        {...attributes}
        {...listeners}
        className="text-base-content/50 hover:text-base-content/70 transition-colors"
      >
        <BsGripVertical className="text-lg" />
      </div>
      <span className="font-medium text-sm truncate">{id}</span>
    </div>
  );
}

export default function TaskDetailList({
  tasks,
  selectedTask,
  onTaskSelect,
  onDragEnd,
}: TaskDetailListProps) {
  const taskNames = Object.keys(tasks);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
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

  return (
    <div className="h-full overflow-y-auto">
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
                onSelect={() => onTaskSelect(taskName, tasks[taskName])}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  );
}
