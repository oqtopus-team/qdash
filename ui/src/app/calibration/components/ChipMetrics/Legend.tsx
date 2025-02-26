"use client";

import { ColorLegend } from "@/app/lib/ColorLegend";

interface LegendProps {
  selectedMetric: string;
}

export function Legend({ selectedMetric }: LegendProps) {
  const colorScales = {
    status: ["#ff0000", "#0000ff", "#00ff00"],
    qubit_freq_cw: [
      "#2a4858",
      "#106e7c",
      "#00968e",
      "#4abd8c",
      "#9cdf7c",
      "#fafa6e",
    ],
  };

  const labels = {
    status: ["Failed", "Running", "Success"],
    qubit_freq_cw: ["7750", "8020", "8290", "8560", "8830", "9100"],
  };

  const titles = {
    status: "Status",
    qubit_freq_cw: "Qubit Frequency (MHz)",
  };

  return (
    <ColorLegend
      colorScale={colorScales[selectedMetric as keyof typeof colorScales]}
      labels={labels[selectedMetric as keyof typeof labels]}
      title={titles[selectedMetric as keyof typeof titles]}
    />
  );
}
