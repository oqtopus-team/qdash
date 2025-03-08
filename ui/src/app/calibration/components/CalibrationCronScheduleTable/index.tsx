"use client";

import { useEffect, useState } from "react";

import { getColumns } from "./Columns";
import { EditScheduleModal } from "./EditScheduleModal";
import { MenuPreviewModal } from "./MenuPreviewModal";
import type {
  MenuModel,
  ScheduleCronCalibResponse,
  GetMenuResponse,
} from "@/schemas";
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
  const [selectedSchedule, setSelectedSchedule] =
    useState<ScheduleCronCalibResponse | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [selectedMenuForPreview, setSelectedMenuForPreview] =
    useState<GetMenuResponse | null>(null);
  const [showMenuPreview, setShowMenuPreview] = useState(false);

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
    refetch: refetchMenu,
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

  const handleEdit = (schedule: ScheduleCronCalibResponse) => {
    setSelectedSchedule(schedule);
    setIsEditModalOpen(true);
  };

  const handleMenuClick = async (menuName: string) => {
    setShowMenuPreview(true);
    const menuData = await refetchMenu();
    if (menuData.data) {
      const menuWithDetails = menuData.data.data.menus.find(
        (menu: GetMenuResponse) => menu.name === menuName
      );
      if (menuWithDetails) {
        setSelectedMenuForPreview(menuWithDetails);
      }
    }
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
        <span>Failed to load cron schedules</span>
      </div>
    );
  }

  return (
    <div className="bg-base-100 rounded-box shadow-lg">
      {showMenuPreview && selectedMenuForPreview && (
        <MenuPreviewModal
          selectedItem={selectedMenuForPreview}
          onClose={() => {
            setShowMenuPreview(false);
            setSelectedMenuForPreview(null);
          }}
        />
      )}
      {selectedSchedule && (
        <EditScheduleModal
          isOpen={isEditModalOpen}
          onClose={() => {
            setIsEditModalOpen(false);
            setSelectedSchedule(null);
          }}
          schedule={selectedSchedule}
          menus={menu}
          onSuccess={async () => {
            const updatedData = await refetchCronSchedule();
            if (updatedData.data) {
              setCronSchedules(updatedData.data.data.schedules);
            }
          }}
        />
      )}
      <div className="border-b border-base-300 px-6 py-4">
        <h2 className="text-2xl font-bold">Cron Schedule</h2>
      </div>
      <div className="p-6">
        <Table
          data={cronSchedules}
          columns={getColumns(handleToggle, handleEdit, handleMenuClick, menu)}
          filter={"menu_name"}
        />
      </div>
    </div>
  );
}
