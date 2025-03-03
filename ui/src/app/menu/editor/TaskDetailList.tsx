"use client";

import { GetMenuResponseTaskDetails } from "@/schemas";
import {
  DragDropContext,
  Droppable,
  Draggable,
  DropResult,
  DroppableProvided,
  DraggableProvided,
  DraggableStateSnapshot,
  DroppableProps,
} from "react-beautiful-dnd";
import { BsFileEarmarkText } from "react-icons/bs";
import { useEffect, useState } from "react";

interface TaskDetailListProps {
  tasks: GetMenuResponseTaskDetails;
  selectedTask: string | null;
  onTaskSelect: (taskName: string, content: any) => void;
  onDragEnd: (result: DropResult) => void;
}

// StrictModeに対応したDnDコンポーネント
function StrictModeDroppable({ children, ...props }: DroppableProps) {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    const animation = requestAnimationFrame(() => setEnabled(true));
    return () => {
      cancelAnimationFrame(animation);
      setEnabled(false);
    };
  }, []);
  if (!enabled) {
    return null;
  }
  return <Droppable {...props}>{children}</Droppable>;
}

export default function TaskDetailList({
  tasks,
  selectedTask,
  onTaskSelect,
  onDragEnd,
}: TaskDetailListProps) {
  return (
    <DragDropContext onDragEnd={onDragEnd}>
      <StrictModeDroppable droppableId="task-details">
        {(provided: DroppableProvided) => (
          <div
            ref={provided.innerRef}
            {...provided.droppableProps}
            className="overflow-y-auto flex-1 p-2"
          >
            <div className="space-y-1">
              {Object.entries(tasks || {}).map(([taskName, content], index) => (
                <Draggable key={taskName} draggableId={taskName} index={index}>
                  {(
                    provided: DraggableProvided,
                    snapshot: DraggableStateSnapshot
                  ) => (
                    <div
                      ref={provided.innerRef}
                      {...provided.draggableProps}
                      {...provided.dragHandleProps}
                      className={`p-2 rounded cursor-pointer hover:bg-base-300 flex items-center gap-2 ${
                        selectedTask === taskName ? "bg-base-300" : ""
                      } ${snapshot.isDragging ? "bg-base-300/50" : ""}`}
                      onClick={() => onTaskSelect(taskName, content)}
                    >
                      <BsFileEarmarkText className="text-base-content/70" />
                      <span className="font-medium">{taskName}</span>
                    </div>
                  )}
                </Draggable>
              ))}
              {provided.placeholder}
            </div>
          </div>
        )}
      </StrictModeDroppable>
    </DragDropContext>
  );
}
