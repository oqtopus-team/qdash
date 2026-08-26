"use client";

import { AVAILABLE_THEMES } from "@/constants/themes";
import { useTheme } from "@/contexts/ThemeContext";

const paletteItems = [
  ["Primary", "bg-primary"],
  ["Secondary", "bg-secondary"],
  ["Accent", "bg-accent"],
  ["Neutral", "bg-neutral"],
  ["Info", "bg-info"],
  ["Success", "bg-success"],
  ["Warning", "bg-warning"],
  ["Error", "bg-error"],
] as const;

function themeLabel(theme: string) {
  return theme
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function AppearanceSettingsPanel() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="card bg-base-200 shadow-lg" key="appearance">
      <div className="card-body">
        <h2 className="card-title text-xl mb-4">Theme Settings</h2>
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <label className="text-sm font-medium">Select Theme</label>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
              {AVAILABLE_THEMES.map((themeName) => (
                <button
                  key={themeName}
                  className={`btn btn-sm w-full ${theme === themeName ? "btn-primary" : "btn-ghost"}`}
                  onClick={() => setTheme(themeName)}
                >
                  {themeLabel(themeName)}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <h3 className="text-sm font-medium">Color Palette</h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {paletteItems.map(([label, swatchClass]) => (
                <div key={label} className="flex items-center gap-2 rounded-lg bg-base-100 p-2">
                  <div className={`h-8 w-8 rounded-md ${swatchClass}`} />
                  <span className="text-sm font-medium">{label}</span>
                </div>
              ))}
            </div>

            <div className="flex flex-col gap-3">
              <h3 className="text-sm font-medium">Preview Components</h3>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <button className="btn btn-primary btn-sm w-full">Primary</button>
                <button className="btn btn-secondary btn-sm w-full">Secondary</button>
                <button className="btn btn-accent btn-sm w-full">Accent</button>
                <button className="btn btn-neutral btn-sm w-full">Neutral</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
