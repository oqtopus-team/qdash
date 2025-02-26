"use client";
import { useState } from "react";
import { FaRedo } from "react-icons/fa";
import { FridgeChart } from "./components/FridgeChart";

function FridgePage() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedHours, setSelectedHours] = useState(12);
  const [customHours, setCustomHours] = useState("");

  const handleTransitionClick = () => {
    // 再描画トリガー
    setRefreshKey((prevKey) => prevKey + 1);
  };

  const handleCustomHoursChange = (e) => {
    setCustomHours(e.target.value);
  };

  const applyCustomHours = () => {
    const hours = parseFloat(customHours);
    if (!isNaN(hours) && hours > 0) {
      setSelectedHours(hours);
    }
  };

  return (
    <div className="w-full px-4" style={{ width: "calc(100vw - 20rem)" }}>
      <div className="text-lg breadcrumbs">
        <ul>
          <li>Fridges</li>
          <li>XLD</li>
        </ul>
      </div>
      <h2 className="text-left text-4xl font-bold px-1 pb-3">
        XLD Temperature
        <div className="badge badge-accent mx-4">normal</div>
      </h2>
      <div className="flex justify-end mx-4">
        <div className="join mx-2">
          <input
            className="join-item btn"
            type="radio"
            name="options"
            aria-label="6h"
            onClick={() => setSelectedHours(6)}
            checked={selectedHours === 6}
          />
          <input
            className="join-item btn"
            type="radio"
            name="options"
            aria-label="12h"
            onClick={() => setSelectedHours(12)}
            checked={selectedHours === 12}
          />
          <input
            className="join-item btn"
            type="radio"
            name="options"
            aria-label="24h"
            onClick={() => setSelectedHours(24)}
            checked={selectedHours === 24}
          />
        </div>
        <div className="flex items-center mx-2">
          <input
            type="number"
            placeholder="hours"
            className="input input-bordered w-24 mr-2"
            value={customHours}
            onChange={handleCustomHoursChange}
          />
          <span className="mr-2">h</span>
          <button className="btn bg-primary shadow" onClick={applyCustomHours}>
            Apply
          </button>
        </div>
        <div className="flex items-center">
          <button
            className="btn mx-1 bg-primary shadow"
            onClick={handleTransitionClick}
          >
            <FaRedo />
            <div>Refresh</div>
          </button>
        </div>
      </div>
      <div className="w-full gap-6 px-2">
        <div className="w-full h-full">
          <div
            className="grid grid-cols-2 grid-rows-2 gap-2"
            style={{
              gridTemplateRows: "1fr 1fr",
              gridTemplateColumns: "1fr 1fr",
            }}
          >
            <div className="col-span-1 row-span-1">
              <FridgeChart
                key={refreshKey + "-1"}
                name={"50K-FLANGE"}
                channel={1}
                hours={selectedHours}
              />
            </div>
            <div className="col-span-1 row-span-1">
              <FridgeChart
                key={refreshKey + "-2"}
                name={"4K-FLANGE"}
                channel={2}
                hours={selectedHours}
              />
            </div>
            <div className="col-span-1 row-span-1">
              <FridgeChart
                key={refreshKey + "-5"}
                name={"STILL-FLANGE"}
                channel={5}
                hours={selectedHours}
              />
            </div>
            <div className="col-span-1 row-span-1">
              <FridgeChart
                key={refreshKey + "-6"}
                name={"MXC-FLANGE"}
                channel={6}
                hours={selectedHours}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default FridgePage;
