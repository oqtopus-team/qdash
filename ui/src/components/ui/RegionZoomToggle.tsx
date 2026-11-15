"use client";

import { ZoomIn } from "lucide-react";

interface RegionZoomToggleProps {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

export function RegionZoomToggle({ enabled, onToggle }: RegionZoomToggleProps) {
  return (
    <label
      className={`flex items-center gap-3 p-3 rounded-lg border-2 transition-colors duration-200 cursor-pointer select-none ${
        enabled
          ? "bg-primary/10 border-primary"
          : "bg-base-200/50 border-base-300 hover:border-primary/50"
      }`}
    >
      <div
        className={`p-2 rounded-lg ${enabled ? "bg-primary text-primary-content" : "bg-base-300"}`}
      >
        <ZoomIn size={20} aria-hidden="true" />
      </div>
      {/* Both states stay mounted so the card keeps the width of the wider one */}
      <div className="flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-sm">Region Zoom</span>
          <span
            className={`badge badge-primary badge-xs ${enabled ? "" : "invisible"}`}
            aria-hidden={enabled ? undefined : true}
          >
            Active
          </span>
        </div>
        <p className="grid text-xs text-base-content/60">
          <span
            className={`col-start-1 row-start-1 ${enabled ? "invisible" : ""}`}
            aria-hidden={enabled ? true : undefined}
          >
            Enable to zoom into specific regions
          </span>
          <span
            className={`col-start-1 row-start-1 ${enabled ? "" : "invisible"}`}
            aria-hidden={enabled ? undefined : true}
          >
            Click any region on the grid to zoom in
          </span>
        </p>
      </div>
      <input
        type="checkbox"
        checked={enabled}
        onChange={(event) => onToggle(event.target.checked)}
        className="toggle toggle-primary"
      />
    </label>
  );
}
