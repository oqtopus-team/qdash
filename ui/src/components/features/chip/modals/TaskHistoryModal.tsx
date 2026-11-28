"use client";

import { useGetQubitTaskHistory } from "@/client/task-result/task-result";
import { TargetTaskHistoryModal } from "@/components/features/chip/modals/TargetTaskHistoryModal";

interface TaskHistoryModalProps {
  chipId: string;
  qid: string;
  taskName: string;
  isOpen: boolean;
  onClose: () => void;
  selectedDate?: string;
}

/** Task execution history of a qubit, with the selected result's details. */
export function TaskHistoryModal({
  chipId,
  qid,
  taskName,
  isOpen,
  onClose,
  selectedDate,
}: TaskHistoryModalProps) {
  const { data, isLoading, isError } = useGetQubitTaskHistory(
    qid,
    { chip_id: chipId, task: taskName },
    {
      query: {
        enabled: isOpen && !!chipId && !!qid && !!taskName,
        staleTime: 30000,
        gcTime: 60000,
      },
    },
  );

  return (
    <TargetTaskHistoryModal
      chipId={chipId}
      targetId={qid}
      targetKind="qubit"
      taskName={taskName}
      isOpen={isOpen}
      onClose={onClose}
      selectedDate={selectedDate}
      history={{ data: data?.data, isLoading, isError }}
    />
  );
}
