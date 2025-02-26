import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getColumns } from "./TableColumns";
import { TableDetailModal } from "./TableDetailModal";

import type { OneQubitCalibSummary } from "@/schemas";

import { useFetchOneQubitCalibSummaryByDate } from "@/client/calibration/calibration";
import { Table } from "@/components/Table";
const INITIAL_SELECTED_ITEM: OneQubitCalibSummary = {
  label: "label",
  one_qubit_calib_data: [],
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
  const navigate = useNavigate();
  const handleFigureClick = (item: OneQubitCalibSummary) => {
    setSelectedItem(item);
    navigate(`/result/history/one_qubit/${date}/${item.label}`);
  };
  const handleHistoryClick = (item: OneQubitCalibSummary) => {
    setSelectedItem(item);
    navigate(`/result/latest/one_qubit/${item.label}`);
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
