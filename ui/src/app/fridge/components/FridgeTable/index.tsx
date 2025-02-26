import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getColumns } from "./TableColumns";
import { TableDetailModal } from "./TableDetailModal";

import type { OneQubitCalibSummary } from "@/schemas";

import { useFetchOneQubitCalibSummaryByDate } from "@/client/calibration/calibration";
import { Table } from "@/app/components/Table";
const INITIAL_SELECTED_ITEM: OneQubitCalibSummary = {
  label: "label",
  one_qubit_calib_data: {
    resonator_frequency: { value: 0, unit: "Hz", type: "number" },
    qubit_frequency: { value: 0, unit: "Hz", type: "number" },
    t1: { value: 0, unit: "s", type: "number" },
    t2_star: { value: 0, unit: "s", type: "number" },
    t2_echo: { value: 0, unit: "s", type: "number" },
    average_gate_fidelity: { value: 0, unit: "", type: "number" },
  },
};

type OneQubitHistoryTableProps = {
  date: string;
};

export function OneQubitHistoryTable({ date }: OneQubitHistoryTableProps) {
  const [tableData, setTableData] = useState([] as OneQubitCalibSummary[]);
  const [selectedItem, setSelectedItem] = useState<OneQubitCalibSummary>(
    INITIAL_SELECTED_ITEM
  );
  const { data, isError, isLoading } = useFetchOneQubitCalibSummaryByDate(date);
  useEffect(() => {
    if (data) {
      setTableData(data.data.summary);
    }
  }, [data]);

  const handleDetailClick = (item: OneQubitCalibSummary) => {
    setSelectedItem(item);
    const detailModal = document.getElementById(
      "tableDetail"
    ) as HTMLDialogElement | null;
    if (detailModal) {
      detailModal.showModal();
    }
  };
  const router = useRouter();
  const handleFigureClick = (item: OneQubitCalibSummary) => {
    setSelectedItem(item);
    router.push(`/result/history/one_qubit/${date}/${item.label}`);
  };
  const handleHistoryClick = (item: OneQubitCalibSummary) => {
    setSelectedItem(item);
    router.push(`/result/latest/one_qubit/${item.label}`);
  };
  if (isLoading) {
    return <div>Loading...</div>;
  }
  if (isError) {
    return <div>Error</div>;
  }
  const columns = getColumns(
    handleDetailClick,
    handleFigureClick,
    handleHistoryClick
  );
  return (
    <div>
      <Table data={tableData} columns={columns} filter={"label"} />
      <TableDetailModal selectedItem={selectedItem} />
    </div>
  );
}
