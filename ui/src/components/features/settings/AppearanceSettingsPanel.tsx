"use client";

import { AlertTriangle } from "lucide-react";

import { AVAILABLE_THEMES, DEV_THEMES } from "@/constants/themes";
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
  return theme.charAt(0).toUpperCase() + theme.slice(1);
}

export function AppearanceSettingsPanel() {
  const { theme, setTheme, isDevEnv } = useTheme();
  const themes = isDevEnv ? DEV_THEMES : AVAILABLE_THEMES;

  return (
    <div className="card bg-base-200 shadow-lg" key="appearance">
      <div className="card-body">
        <h2 className="card-title text-xl mb-4">Theme Settings</h2>
        {isDevEnv && (
          <div className="alert alert-warning mb-4">
            <AlertTriangle className="h-6 w-6 shrink-0" />
            <span>Dev environment: Using purple theme for visual distinction</span>
          </div>
        )}
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <label className="text-sm font-medium">Select Theme</label>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
              {themes.slice(0, 8).map((themeName) => (
                <button
                  key={themeName}
                  className={`btn btn-sm w-full ${theme === themeName ? "btn-primary" : "btn-ghost"}`}
                  onClick={() => setTheme(themeName)}
                >
                  {themeLabel(themeName)}
                </button>
              ))}
            </div>
            {!isDevEnv && themes.length > 8 && (
              <details className="collapse collapse-arrow bg-base-100">
                <summary className="collapse-title text-sm font-medium">More themes</summary>
                <div className="collapse-content">
                  <div className="grid grid-cols-2 gap-3 pt-2 sm:grid-cols-3 md:grid-cols-4">
                    {themes.slice(8).map((themeName) => (
                      <button
                        key={themeName}
                        className={`btn btn-sm w-full ${
                          theme === themeName ? "btn-primary" : "btn-ghost"
                        }`}
                        onClick={() => setTheme(themeName)}
                      >
                        {themeLabel(themeName)}
                      </button>
                    ))}
                  </div>
                </div>
              </details>
            )}
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
