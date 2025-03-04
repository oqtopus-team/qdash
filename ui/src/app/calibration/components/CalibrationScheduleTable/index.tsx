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

  const handleNewItem = () => {
    const editModal = document.getElementById(
      "newItem"
    ) as HTMLDialogElement | null;
    if (editModal) {
      editModal.showModal();
    }
  };

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

  if (isScheduleLoading || isMenuLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="loading loading-spinner loading-lg text-primary"></div>
      </div>
    );
  }

  if (isScheduleError || isMenuError) {
    return (
      <div className="alert alert-error">
        <span>Failed to load calibration schedules</span>
      </div>
    );
  }

  return (
    <div className="bg-base-100 rounded-box shadow-lg">
      <div className="flex justify-between items-center border-b border-base-300 px-6 py-4">
        <h2 className="text-2xl font-bold">Calibration Schedule</h2>
        <button className="btn btn-primary btn-sm" onClick={handleNewItem}>
          <FaRegSquarePlus className="text-lg" />
          New Schedule
        </button>
      </div>
      <div className="p-6">
        <Table
          data={calibSchedules}
          columns={getColumns(handleDeleteClick)}
          filter={"menu_name"}
        />
      </div>
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
