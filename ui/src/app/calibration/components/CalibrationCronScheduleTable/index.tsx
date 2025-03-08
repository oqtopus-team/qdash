"use client";

import { useEffect, useState } from "react";
import { FaRegSquarePlus } from "react-icons/fa6";

import { getColumns } from "./Columns";
import type { MenuModel, ScheduleCronCalibResponse } from "@/schemas";
import {
  useListCronSchedules,
  useScheduleCronCalib,
} from "@/client/calibration/calibration";
import { useListMenu } from "@/client/menu/menu";
import { Table } from "@/app/components/Table";

export function CalibrationCronScheduleTable() {
  const [cronSchedules, setCronSchedules] = useState<
    ScheduleCronCalibResponse[]
  >([]);
  const [menu, setMenu] = useState<MenuModel[]>([]);

  const {
    data: scheduleData,
    isError: isScheduleError,
    isLoading: isScheduleLoading,
    refetch: refetchCronSchedule,
  } = useListCronSchedules();

  const {
    data: menuData,
    isError: isMenuError,
    isLoading: isMenuLoading,
  } = useListMenu();

  const scheduleMutation = useScheduleCronCalib();

  useEffect(() => {
    if (scheduleData?.data) {
      setCronSchedules(scheduleData.data.schedules);
    }
    if (menuData?.data?.menus) {
      setMenu(menuData.data.menus);
    }
  }, [scheduleData, menuData]);

  const handleNewItem = () => {
    // TODO: Implement new cron schedule modal
    console.log("New cron schedule");
  };

  const handleToggle = (item: ScheduleCronCalibResponse, active: boolean) => {
    scheduleMutation.mutate(
      {
        data: {
          scheduler_name: item.scheduler_name,
          menu_name: item.menu_name,
          cron: item.cron,
          active: active,
        },
      },
      {
        onSuccess: async () => {
          const updatedData = await refetchCronSchedule();
          if (updatedData.data) {
            setCronSchedules(updatedData.data.data.schedules);
          }
        },
        onError: (error: Error) => {
          console.error("Error updating cron schedule:", error);
        },
      },
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
        <span>Failed to load cron schedules</span>
      </div>
    );
  }

  return (
    <div className="bg-base-100 rounded-box shadow-lg">
      <div className="flex justify-between items-center border-b border-base-300 px-6 py-4">
        <h2 className="text-2xl font-bold">Cron Schedule</h2>
        <button className="btn btn-primary btn-sm" onClick={handleNewItem}>
          <FaRegSquarePlus className="text-lg" />
          New Cron Schedule
        </button>
      </div>
      <div className="p-6">
        <Table
          data={cronSchedules}
          columns={getColumns(handleToggle)}
          filter={"menu_name"}
        />
      </div>
    </div>
  );
}
