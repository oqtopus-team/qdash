"use client";

import React, { useState } from "react";
import "react-toastify/dist/ReactToastify.css";
import { ToastContainer } from "react-toastify";

import { CalibrationMenuTable } from "./components/CalibrationMenuTable";
import { CalibrationScheduleTable } from "./components/CalibrationScheduleTable";
import { CalibrationCronScheduleTable } from "./components/CalibrationCronScheduleTable";
import dynamic from "next/dynamic";

const ChipMetrics = dynamic(() => import("./components/ChipMetrics"), {
  ssr: false,
});

export default function CalibrationPage() {
  const [activeTab, setActiveTab] = useState("Menu");
  const MemoizedCalibrationMenuTable = React.memo(CalibrationMenuTable);
  const MemoizedCalibrationScheduleTable = React.memo(CalibrationScheduleTable);
  const MemoizedCalibrationCronScheduleTable = React.memo(
    CalibrationCronScheduleTable
  );

  const getComponent = (tabName: string) => {
    switch (tabName) {
      case "Menu":
        return <MemoizedCalibrationMenuTable />;
      case "Schedule":
        return <MemoizedCalibrationScheduleTable />;
      case "Cron Schedule":
        return <MemoizedCalibrationCronScheduleTable />;
      default:
        return null;
    }
  };

  return (
    <div className="w-full px-4" style={{ width: "calc(100vw - 20rem)" }}>
      <h1 className="text-left text-3xl font-bold px-1 pb-3">Calibration</h1>
      <div className="w-full gap-6 px-2">
        <div className="w-full h-full">
          <div
            className="grid grid-cols-14 grid-rows-10 gap-4"
            style={{ gridTemplateRows: "450px auto auto auto auto auto" }}
          >
            <div className="col-span-12 row-span-6 col-start-1">
              <ChipMetrics />
            </div>
            <div className="col-span-12 row-span-3 col-start-1 row-start-7">
              <div role="tablist" className="tabs tabs-bordered tabs-lg mt-20">
                <a
                  role="tab"
                  className={activeTab === "Menu" ? "tab tab-active" : "tab"}
                  onClick={() => setActiveTab("Menu")}
                >
                  Menu
                </a>
                <a
                  role="tab"
                  className={
                    activeTab === "Cron Schedule" ? "tab tab-active" : "tab"
                  }
                  onClick={() => setActiveTab("Cron Schedule")}
                >
                  Cron Schedule
                </a>
                <a
                  role="tab"
                  className={
                    activeTab === "Schedule" ? "tab tab-active" : "tab"
                  }
                  onClick={() => setActiveTab("Schedule")}
                >
                  Date time Schedule
                </a>
              </div>
              {getComponent(activeTab)}
            </div>
          </div>
        </div>
      </div>
      <ToastContainer />
    </div>
  );
}
