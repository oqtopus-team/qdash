"use client";

interface RegionZoomToggleProps {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

export function RegionZoomToggle({ enabled, onToggle }: RegionZoomToggleProps) {
  return (
    <div
      className={`flex items-center gap-3 p-3 rounded-lg border-2 transition-all duration-200 cursor-pointer select-none ${
        enabled
          ? "bg-primary/10 border-primary"
          : "bg-base-200/50 border-base-300 hover:border-primary/50"
      }`}
      onClick={() => onToggle(!enabled)}
    >
      <div
        className={`p-2 rounded-lg ${
          enabled ? "bg-primary text-primary-content" : "bg-base-300"
        }`}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.3-4.3" />
          <path d="M11 8v6" />
          <path d="M8 11h6" />
        </svg>
      </div>
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm">Region Zoom</span>
          {enabled && (
            <span className="badge badge-primary badge-xs">Active</span>
          )}
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
        onChange={(e) => {
          e.stopPropagation();
          onToggle(e.target.checked);
        }}
        className="toggle toggle-primary"
      />
    </div>
  );
}
