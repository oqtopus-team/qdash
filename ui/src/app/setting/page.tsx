"use client";

import { useTheme } from "@/app/providers/theme-provider";
import { SettingsCard } from "./components/SettingsCard";

const themes = [
  "light",
  "dark",
  "cupcake",
  "bumblebee",
  "emerald",
  "corporate",
  "synthwave",
  "retro",
  "cyberpunk",
  "valentine",
  "halloween",
  "garden",
  "forest",
  "aqua",
  "lofi",
  "pastel",
  "fantasy",
  "wireframe",
  "black",
  "luxury",
  "dracula",
  "cmyk",
  "autumn",
  "business",
  "acid",
  "lemonade",
  "night",
  "coffee",
  "winter",
];

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="w-full px-4" style={{ width: "calc(100vw - 20rem)" }}>
      <h1 className="text-left text-3xl font-bold px-1 pb-3">Settings</h1>
      <div className="w-full gap-6 px-2">
        <div className="w-full h-full">
          <div className="card bg-base-200 shadow">
            <div className="card-title">Theme</div>
            <div className="card-body">
              <div className="flex flex-col gap-2">
                <p className="text-sm opacity-80">Current theme: {theme}</p>
                <div className="flex flex-col gap-4">
                  <select
                    className="select select-bordered w-full max-w-xs"
                    value={theme}
                    onChange={(e) => {
                      setTheme(e.target.value);
                    }}
                  >
                    {themes.map((t) => (
                      <option key={t} value={t}>
                        {t.charAt(0).toUpperCase() + t.slice(1)}
                      </option>
                    ))}
                  </select>

                  {/* Color palette */}
                  <div className="flex flex-col gap-2">
                    <h3 className="text-sm font-semibold">Color Palette</h3>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded bg-primary"></div>
                        <span className="text-sm">Primary</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded bg-secondary"></div>
                        <span className="text-sm">Secondary</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded bg-accent"></div>
                        <span className="text-sm">Accent</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded bg-neutral"></div>
                        <span className="text-sm">Neutral</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded bg-info"></div>
                        <span className="text-sm">Info</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded bg-success"></div>
                        <span className="text-sm">Success</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded bg-warning"></div>
                        <span className="text-sm">Warning</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded bg-error"></div>
                        <span className="text-sm">Error</span>
                      </div>
                    </div>
                  </div>

                  {/* Example components */}
                  <div className="flex flex-col gap-2">
                    <h3 className="text-sm font-semibold">
                      Example Components
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      <button className="btn btn-primary">Primary</button>
                      <button className="btn btn-secondary">Secondary</button>
                      <button className="btn btn-accent">Accent</button>
                      <button className="btn btn-neutral">Neutral</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <SettingsCard />
        </div>
      </div>
    </div>
  );
}
