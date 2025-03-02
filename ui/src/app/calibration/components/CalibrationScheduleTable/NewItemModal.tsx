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
    <dialog
      id="newItem"
      className="modal"
      style={{ width: "80%", height: "80%" }}
    >
      <div className="modal-box" style={{ width: "100%", height: "80%" }}>
        <h3 className="font-bold text-lg my-4">Schedule Calibration</h3>
        <form onSubmit={handleSubmit}>
          <div className="flex flex-col items-start">
            <label className="form-control w-full max-w-xs">
              <div className="label">
                <span className="label-text">Pick the menu</span>
              </div>
              <select
                value={selectedMenuName}
                className="select select-bordered"
                onChange={(e) => setSelectedMenuName(e.target.value)}
              >
                <option disabled value="">
                  Pick one
                </option>
                {menu.map((menu) => (
                  <option key={menu.name} value={menu.name}>
                    {menu.name}
                  </option>
                ))}
              </select>
            </label>
            <p className="mx-5 mt-4">Scheduled Time</p>
            <DatePicker
              dateFormat="yyyy-MM-dd'T'HH:mm:ssXXX"
              locale="ja"
              selected={selectedDate}
              onChange={(date) => setSelectedDate(date)}
              showTimeSelect
              timeIntervals={30}
              className="react-datepicker input-sm input-bordered w-72 my-5"
            />
            <p className="mx-5 mt-4">Repeat</p>
            <select
              value={repeatType}
              className="select select-bordered"
              onChange={(e) => setRepeatType(e.target.value)}
            >
              <option value="none">None</option>
              <option value="minutely">Minutely</option>
              <option value="hourly">Hourly</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
            {repeatType !== "none" && (
              <>
                <p className="mx-5 mt-4">Repeat Interval</p>
                <input
                  type="number"
                  value={repeatInterval}
                  onChange={(e) => setRepeatInterval(Number(e.target.value))}
                  className="input input-bordered w-24"
                  min="1"
                />
                <p className="mx-5 mt-4">Repeat End Date</p>
                <DatePicker
                  dateFormat="yyyy-MM-dd'T'HH:mm:ssXXX"
                  locale="ja"
                  selected={repeatEndDate}
                  onChange={(date) => setRepeatEndDate(date)}
                  showTimeSelect
                  timeIntervals={30}
                  className="react-datepicker input-sm input-bordered w-72 my-5"
                />
              </>
            )}
          </div>
          <div className="modal-action">
            <button type="submit" className="btn">
              Submit
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => {
                const newItemElement = document.getElementById("newItem");
                if (newItemElement) {
                  newItemElement.closest("dialog")?.close();
                }
              }}
            >
              Close
            </button>
          </div>
        </form>
      </div>
    </dialog>
  );
}
