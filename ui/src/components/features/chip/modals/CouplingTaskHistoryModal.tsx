"use client";

import { useGetCouplingTaskHistory } from "@/client/task-result/task-result";
import { TargetTaskHistoryModal } from "@/components/features/chip/modals/TargetTaskHistoryModal";

interface CouplingTaskHistoryModalProps {
  chipId: string;
  couplingId: string;
  taskName: string;
  isOpen: boolean;
  onClose: () => void;
  selectedDate?: string;
}

/** Task execution history of a coupling, with the selected result's details. */
export function CouplingTaskHistoryModal({
  chipId,
  couplingId,
  taskName,
  isOpen,
  onClose,
  selectedDate,
}: CouplingTaskHistoryModalProps) {
  const { data, isLoading, isError } = useGetCouplingTaskHistory(
    couplingId,
    { chip_id: chipId, task: taskName },
    {
      query: {
        enabled: isOpen && !!chipId && !!couplingId && !!taskName,
        staleTime: 30000,
        gcTime: 60000,
      },
    },
  );

  return (
    <TargetTaskHistoryModal
      chipId={chipId}
      targetId={couplingId}
      targetKind="coupling"
      taskName={taskName}
      isOpen={isOpen}
      onClose={onClose}
      selectedDate={selectedDate}
      history={{ data: data?.data, isLoading, isError }}
    />
  );
}
