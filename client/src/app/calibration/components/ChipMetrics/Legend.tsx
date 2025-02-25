"use client";


import { ColorLegendComponent } from "@/lib/ColorLegend";

const lowerLimit = 7750;
const upperLimit = 9250;
const colors = [
  "#2a4858",
  "#106e7c",
  "#00968e",
  "#4abd8c",
  "#9cdf7c",
  "#fafa6e",
];

export const StatusPalette = () => {
  return (
    <div style={{ textAlign: "left" }}>
      <div className="badge bg-orange-500 mr-4">scheduled</div>
      <div className="badge bg-blue-500 mr-4">running</div>
      <div className="badge bg-green-500 mr-4">success</div>
      <div className="badge bg-red-500">failed</div>
    </div>
  );
};

export const Legend = ({ selectedMetric }: { selectedMetric: string }) => {
  return selectedMetric === "status" ? (
    <StatusPalette />
  ) : (
    <ColorLegendComponent
      titleText="Qubit Frequency (MHz)"
      domain={[lowerLimit, upperLimit]}
      range={colors}
      tickFormat="0.0f"
    />
  );
};
