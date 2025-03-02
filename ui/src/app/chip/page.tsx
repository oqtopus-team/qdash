"use client";

import { useState } from "react";
import { useListMuxes } from "@/client/chip/chip";
import { BsGrid, BsListUl } from "react-icons/bs";
import { ChipSelector } from "./components/ChipSelector";
import { MuxCard } from "./components/MuxCard";

type LayoutMode = "list" | "grid";

export default function ChipPage() {
  const [selectedChip, setSelectedChip] = useState<string>("SAMPLE");
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("list");
  const [expandedMuxes, setExpandedMuxes] = useState<{
    [key: string]: boolean;
  }>({});

  const {
    data: muxData,
    isLoading,
    isError,
  } = useListMuxes(selectedChip || "");

  const toggleMuxExpansion = (muxId: string) => {
    setExpandedMuxes((prev) => ({
      ...prev,
      [muxId]: !prev[muxId],
    }));
  };

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
                  layoutMode === "list" ? "btn-active" : ""
                }`}
                onClick={() => setLayoutMode("list")}
              >
                <BsListUl className="text-lg" />
              </button>
              <button
                className={`join-item btn btn-sm ${
                  layoutMode === "grid" ? "btn-active" : ""
                }`}
                onClick={() => setLayoutMode("grid")}
              >
                <BsGrid className="text-lg" />
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
              <span>Select a chip to view MUX data</span>
            </div>
          ) : (
            <div
              className={
                layoutMode === "grid" ? "grid grid-cols-4 gap-4" : "space-y-4"
              }
            >
              {Object.entries(muxData.data.muxes).map(([muxId, muxDetail]) => (
                <MuxCard
                  key={muxId}
                  muxId={muxId}
                  muxDetail={muxDetail}
                  layoutMode={layoutMode}
                  isExpanded={expandedMuxes[muxId] || false}
                  onToggleExpand={() => toggleMuxExpansion(muxId)}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
