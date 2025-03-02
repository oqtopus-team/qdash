"use client";

import { useState } from "react";
import { useListMuxes } from "@/client/chip/chip";
import { BsGrid, BsListUl } from "react-icons/bs";
import { ChipSelector } from "./components/ChipSelector";
import { MuxCard } from "./components/MuxCard";
import { TaskResultGrid } from "./components/TaskResultGrid";

type ViewMode = "chip" | "mux";

export default function ChipPage() {
  const [selectedChip, setSelectedChip] = useState<string>("SAMPLE");
  const [viewMode, setViewMode] = useState<ViewMode>("chip");

  const {
    data: muxData,
    isLoading,
    isError,
  } = useListMuxes(selectedChip || "");

  return (
    <div className="w-full px-6 py-6" style={{ width: "calc(100vw - 20rem)" }}>
      <div className="space-y-6">
        {/* Header Section */}
        <div className="flex flex-col gap-6">
          <div className="flex justify-between items-center">
            <h1 className="text-2xl font-bold">Chip Experiments</h1>
            <div className="join rounded-lg overflow-hidden">
              <button
                className={`join-item btn btn-sm ${
                  viewMode === "chip" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("chip")}
              >
                <BsGrid className="text-lg" />
                <span className="ml-2">Chip View</span>
              </button>
              <button
                className={`join-item btn btn-sm ${
                  viewMode === "mux" ? "btn-active" : ""
                }`}
                onClick={() => setViewMode("mux")}
              >
                <BsListUl className="text-lg" />
                <span className="ml-2">MUX View</span>
              </button>
            </div>
          </div>

          <ChipSelector
            selectedChip={selectedChip}
            onChipSelect={setSelectedChip}
          />
        </div>

        {/* Content Section */}
        <div className="pt-4">
          {isLoading ? (
            <div className="w-full flex justify-center py-12">
              <span className="loading loading-spinner loading-lg"></span>
            </div>
          ) : isError ? (
            <div className="alert alert-error">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="stroke-current shrink-0 h-6 w-6"
                fill="none"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span>Failed to load MUX data</span>
            </div>
          ) : !muxData?.data ? (
            <div className="alert alert-info">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                className="stroke-current shrink-0 w-6 h-6"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span>Select a chip to view data</span>
            </div>
          ) : viewMode === "chip" ? (
            <TaskResultGrid chipId={selectedChip} />
          ) : (
            <div className="space-y-4">
              {Object.entries(muxData.data.muxes).map(([muxId, muxDetail]) => (
                <MuxCard
                  key={muxId}
                  muxId={muxId}
                  muxDetail={muxDetail}
                  layoutMode="list"
                  isExpanded={false}
                  onToggleExpand={() => {}}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
