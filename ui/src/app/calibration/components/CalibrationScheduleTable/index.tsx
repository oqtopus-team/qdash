"use client";

import { useEffect, useState } from "react";

import { ja } from "date-fns/locale/ja";
import { registerLocale } from "react-datepicker";
import { FaRegSquarePlus } from "react-icons/fa6";
import "react-datepicker/dist/react-datepicker.css";

import {
  mapListMenuResponseToListMenu,
  mapScheduleCalibResponsetoCalibSchedule,
} from "../../model";

import { getColumns } from "./Columns";
import { NewItemModal } from "./NewItemModal";

import type { Menu, CalibSchedule } from "../../model";

import {
  useFetchAllCalibSchedule,
  useDeleteCalibSchedule,
} from "@/client/calibration/calibration";
import { useListMenu } from "@/client/menu/menu";
import { LoadingSpinner } from "@/app/components/LoadingSpinner";
import { Table } from "@/app/components/Table";

registerLocale("ja", ja);

export function CalibrationScheduleTable() {
  const [calibSchedules, setCalibSchedules] = useState<CalibSchedule[]>([]);
  const [menu, setMenu] = useState<Menu[]>([]);
  const [selectedMenuName, setSelectedMenuName] = useState("");
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);

  const {
    data: scheduleData,
    isError: isScheduleError,
    isLoading: isScheduleLoading,
    refetch: refetchCalibSchedule,
  } = useFetchAllCalibSchedule();
  const {
    data: menuData,
    isError: isMenuError,
    isLoading: isMenuLoading,
  } = useListMenu();
  const deleteMutation = useDeleteCalibSchedule();

  useEffect(() => {
    if (scheduleData) {
      setCalibSchedules(
        mapScheduleCalibResponsetoCalibSchedule(scheduleData.data)
      );
    }
    if (menuData) {
      setMenu(mapListMenuResponseToListMenu(menuData.data));
    }
  }, [scheduleData, menuData]);

  const handleDeleteClick = (item: CalibSchedule) => {
    deleteMutation.mutate(
      { flowRunId: item.flow_run_id },
      {
        onSuccess: async () => {
          const updatedData = await refetchCalibSchedule();
          if (updatedData.data) {
            setCalibSchedules(
              mapScheduleCalibResponsetoCalibSchedule(updatedData.data.data)
            );
          }
        },
        onError: (error) => {
          console.error("Error delete schedule calibration:", error);
        },
      }
    );
  };

  const columns = getColumns(handleDeleteClick);

  const handleNewItem = () => {
    const editModal = document.getElementById(
      "newItem"
    ) as HTMLDialogElement | null;
    if (editModal) {
      editModal.showModal();
    }
  };

  if (isScheduleLoading || isMenuLoading) {
    return <LoadingSpinner />;
  }

  if (isScheduleError || isMenuError) {
    return <div>Error</div>;
  }

  return (
    <div>
      <div className="flex justify-between">
        <h2 className="text-left text-2xl font-bold px-4 pb-4 py-4">
          Calibration Schedule
        </h2>
        <div className="flex justify-end py-4">
          <div className="flex items-center">
            <button className="btn mx-4 bg-neutral" onClick={handleNewItem}>
              <FaRegSquarePlus className="text-neutral-content" />
              <div className="text-neutral-content">New Schedule</div>
            </button>
          </div>
        </div>
      </div>
      <Table data={calibSchedules} columns={columns} filter={"menu_name"} />
      <NewItemModal
        selectedMenuName={selectedMenuName}
        setSelectedMenuName={setSelectedMenuName}
        menu={menu}
        selectedDate={selectedDate}
        setSelectedDate={setSelectedDate}
        setCalibSchedules={setCalibSchedules}
        refetchCalibSchedule={refetchCalibSchedule}
      />
    </div>
  );
}
