"use client";

import { ZoomIn } from "lucide-react";

interface RegionZoomToggleProps {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

export function RegionZoomToggle({ enabled, onToggle }: RegionZoomToggleProps) {
  return (
    <label
      className={`flex items-center gap-3 p-3 rounded-lg border-2 transition-all duration-200 cursor-pointer select-none ${
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
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm">Region Zoom</span>
          {enabled && <span className="badge badge-primary badge-xs">Active</span>}
        </div>
        <p className="text-xs text-base-content/60">
          {enabled
            ? "Click any region on the grid to zoom in"
            : "Enable to zoom into specific regions"}
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
