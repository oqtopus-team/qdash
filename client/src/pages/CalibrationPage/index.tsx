import React from "react";
import { useState } from "react";
import "react-toastify/dist/ReactToastify.css";

import { ToastContainer } from "react-toastify";

import { CalibrationMenuTable } from "./components/CalibrationMenuTable";
import { CalibrationScheduleTable } from "./components/CalibrationScheduleTable";
import { ChipMetrics } from "./components/ChipMetrics";

function Calibration() {
  const [activeTab, setActiveTab] = useState("Calibration Menu");
  const MemoizedCalibrationMenuTable = React.memo(CalibrationMenuTable);
  const MemoizedCalibrationScheduleTable = React.memo(CalibrationScheduleTable);
  const envValue = import.meta.env.VITE_ENV;
  console.log("envValue", envValue);
  const getComponent = (tabName: string) => {
    switch (tabName) {
      case "Calibration Menu":
        return <MemoizedCalibrationMenuTable />;
      case "Calibration Schedule":
        return <MemoizedCalibrationScheduleTable />;
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
                  className={
                    activeTab === "Calibration Menu" ? "tab tab-active" : "tab"
                  }
                  onClick={() => setActiveTab("Calibration Menu")}
                >
                  Calibration Menu
                </a>
                <a
                  role="tab"
                  className={
                    activeTab === "Calibration Schedule"
                      ? "tab tab-active"
                      : "tab"
                  }
                  onClick={() => setActiveTab("Calibration Schedule")}
                >
                  Calibration Schedule
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
export default Calibration;
