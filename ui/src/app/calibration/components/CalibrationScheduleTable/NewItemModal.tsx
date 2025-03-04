"use client";

import {
  format,
  addMinutes,
  addHours,
  addDays,
  addWeeks,
  addMonths,
} from "date-fns";
import { ja } from "date-fns/locale/ja";
import DatePicker from "react-datepicker";
import { registerLocale } from "react-datepicker";
import { useState } from "react";
import "react-datepicker/dist/react-datepicker.css";

import { mapScheduleCalibResponsetoCalibSchedule } from "../../model";
import type { Menu, CalibSchedule } from "../../model";
import type { UseQueryResult } from "@tanstack/react-query";
import { useScheduleCalib } from "@/client/calibration/calibration";

registerLocale("ja", ja);

export function NewItemModal({
  selectedMenuName,
  setSelectedMenuName,
  menu,
  selectedDate,
  setSelectedDate,
  setCalibSchedules,
  refetchCalibSchedule,
}: {
  selectedMenuName: string;
  setSelectedMenuName: (selectedItem: string) => void;
  menu: Menu[];
  selectedDate: Date | null;
  setSelectedDate: (date: Date | null) => void;
  setCalibSchedules: (calibSchedules: CalibSchedule[]) => void;
  refetchCalibSchedule: () => Promise<UseQueryResult<any, any>>;
}) {
  const scheduleMutation = useScheduleCalib();
  const [repeatType, setRepeatType] = useState<string>("none");
  const [repeatEndDate, setRepeatEndDate] = useState<Date | null>(null);
  const [repeatInterval, setRepeatInterval] = useState<number>(1);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedDate) {
      console.error("date is not set");
      return;
    }

    const scheduleDates = [selectedDate];
    let currentDate = selectedDate;

    while (
      repeatType !== "none" &&
      repeatEndDate &&
      currentDate < repeatEndDate
    ) {
      if (repeatType === "minutely") {
        currentDate = addMinutes(currentDate, repeatInterval);
      } else if (repeatType === "hourly") {
        currentDate = addHours(currentDate, repeatInterval);
      } else if (repeatType === "daily") {
        currentDate = addDays(currentDate, repeatInterval);
      } else if (repeatType === "weekly") {
        currentDate = addWeeks(currentDate, repeatInterval);
      } else if (repeatType === "monthly") {
        currentDate = addMonths(currentDate, repeatInterval);
      }

      if (currentDate <= repeatEndDate) {
        scheduleDates.push(currentDate);
      }
    }

    try {
      for (const date of scheduleDates) {
        await scheduleMutation.mutateAsync({
          data: {
            menu_name: selectedMenuName,
            scheduled: format(date, "yyyy-MM-dd'T'HH:mm:ssXXX"),
          },
        });
      }

      const updatedData = await refetchCalibSchedule();
      if (updatedData.data) {
        setCalibSchedules(
          mapScheduleCalibResponsetoCalibSchedule(updatedData.data.data)
        );
      }
      document.getElementById("newItem")?.closest("dialog")?.close();
    } catch (error) {
      console.error("Error scheduling calibration:", error);
    }
  };

  return (
    <dialog id="newItem" className="modal">
      <form
        method="dialog"
        className="modal-backdrop bg-base-100/30 backdrop-blur-sm"
      >
        <button>close</button>
      </form>
      <div className="modal-box w-[90vw] max-w-[1200px] h-3/5 overflow-auto">
        <h3 className="text-2xl font-bold mb-8">Schedule Calibration</h3>
        <form onSubmit={handleSubmit} className="space-y-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="space-y-8">
              <div className="form-control w-full">
                <label className="label">
                  <span className="label-text font-medium">Menu</span>
                </label>
                <select
                  value={selectedMenuName}
                  className="select select-bordered w-full text-base"
                  onChange={(e) => setSelectedMenuName(e.target.value)}
                >
                  <option disabled value="">
                    Select menu
                  </option>
                  {menu.map((menu) => (
                    <option key={menu.name} value={menu.name}>
                      {menu.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-control w-full">
                <label className="label">
                  <span className="label-text font-medium">Scheduled Time</span>
                </label>
                <DatePicker
                  dateFormat="yyyy/MM/dd HH:mm"
                  locale="ja"
                  selected={selectedDate}
                  onChange={(date) => setSelectedDate(date)}
                  showTimeSelect
                  timeIntervals={30}
                  className="input input-bordered w-full text-base"
                  placeholderText="Select date and time"
                />
              </div>

              <div className="form-control w-full">
                <label className="label">
                  <span className="label-text font-medium">Repeat</span>
                </label>
                <select
                  value={repeatType}
                  className="select select-bordered w-full text-base"
                  onChange={(e) => setRepeatType(e.target.value)}
                >
                  <option value="none">None</option>
                  <option value="minutely">Every Minute</option>
                  <option value="hourly">Every Hour</option>
                  <option value="daily">Every Day</option>
                  <option value="weekly">Every Week</option>
                  <option value="monthly">Every Month</option>
                </select>
              </div>
            </div>

            {repeatType !== "none" && (
              <div className="space-y-8">
                <div className="form-control w-full">
                  <label className="label">
                    <span className="label-text font-medium">
                      Repeat Interval
                    </span>
                  </label>
                  <input
                    type="number"
                    value={repeatInterval}
                    onChange={(e) => setRepeatInterval(Number(e.target.value))}
                    className="input input-bordered w-full text-base"
                    min="1"
                    placeholder="Enter interval"
                  />
                </div>

                <div className="form-control w-full">
                  <label className="label">
                    <span className="label-text font-medium">End Date</span>
                  </label>
                  <DatePicker
                    dateFormat="yyyy/MM/dd HH:mm"
                    locale="ja"
                    selected={repeatEndDate}
                    onChange={(date) => setRepeatEndDate(date)}
                    showTimeSelect
                    timeIntervals={30}
                    className="input input-bordered w-full text-base"
                    placeholderText="Select end date and time"
                  />
                </div>
              </div>
            )}
          </div>

          <div className="modal-action pt-4">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                document.getElementById("newItem")?.closest("dialog")?.close();
              }}
            >
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Schedule
            </button>
          </div>
        </form>
      </div>
    </dialog>
  );
}
