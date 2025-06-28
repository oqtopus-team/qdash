import { useDroppable } from "@dnd-kit/core";

interface DroppableTaskListProps {
  id: string;
  children: React.ReactNode;
}

export default function DroppableTaskList({
  id,
  children,
}: DroppableTaskListProps) {
  const { setNodeRef, isOver } = useDroppable({
    id,
  });

  return (
    <div
      ref={setNodeRef}
      className={`p-2 space-y-1 min-h-[100px] rounded-lg transition-colors ${
        isOver
          ? "bg-primary/10 border-2 border-primary border-dashed"
          : "border-2 border-base-300 border-dashed hover:border-primary/50"
      }`}
    >
      {children}
    </div>
  );
}
