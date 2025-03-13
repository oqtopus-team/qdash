"use client";

import { useState } from "react";
import { useTheme } from "@/app/providers/theme-provider";
import { SettingsCard } from "./components/SettingsCard";

const themes = [
  "oqtopus",
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

type Tab = "appearance" | "system";

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const [activeTab, setActiveTab] = useState<Tab>("appearance");

  return (
    <div className="w-full px-6" style={{ width: "calc(100vw - 20rem)" }}>
      <h1 className="text-left text-3xl font-bold pb-6">Settings</h1>
      <div className="w-full gap-8">
        <div className="tabs tabs-boxed mb-6">
          <a
            className={`tab ${activeTab === "appearance" ? "tab-active" : ""}`}
            onClick={() => setActiveTab("appearance")}
          >
            Appearance
          </a>
          <a
            className={`tab ${activeTab === "system" ? "tab-active" : ""}`}
            onClick={() => setActiveTab("system")}
          >
            System
          </a>
        </div>
        <div className="w-full h-full space-y-6">
          {activeTab === "appearance" ? (
            <div className="card bg-base-200 shadow-lg" key="appearance">
              <div className="card-body">
                <h2 className="card-title text-xl mb-4">Theme Settings</h2>
                <div className="flex flex-col gap-6">
                  <div className="flex flex-col gap-3">
                    <label className="text-sm font-medium">Select Theme</label>
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                      {themes.slice(0, 8).map((t) => (
                        <button
                          key={t}
                          className={`btn btn-sm w-full ${
                            theme === t ? "btn-primary" : "btn-ghost"
                          }`}
                          onClick={() => setTheme(t)}
                        >
                          {t.charAt(0).toUpperCase() + t.slice(1)}
                        </button>
                      ))}
                    </div>
                    <details className="collapse collapse-arrow bg-base-100">
                      <summary className="collapse-title text-sm font-medium">
                        More themes
                      </summary>
                      <div className="collapse-content">
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 pt-2">
                          {themes.slice(8).map((t) => (
                            <button
                              key={t}
                              className={`btn btn-sm w-full ${
                                theme === t ? "btn-primary" : "btn-ghost"
                              }`}
                              onClick={() => setTheme(t)}
                            >
                              {t.charAt(0).toUpperCase() + t.slice(1)}
                            </button>
                          ))}
                        </div>
                      </div>
                    </details>
                  </div>

                  {/* Color palette */}
                  <div className="flex flex-col gap-3">
                    <h3 className="text-sm font-medium">Color Palette</h3>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-primary"></div>
                        <span className="text-sm font-medium">Primary</span>
                      </div>
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-secondary"></div>
                        <span className="text-sm font-medium">Secondary</span>
                      </div>
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-accent"></div>
                        <span className="text-sm font-medium">Accent</span>
                      </div>
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-neutral"></div>
                        <span className="text-sm font-medium">Neutral</span>
                      </div>
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-info"></div>
                        <span className="text-sm font-medium">Info</span>
                      </div>
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-success"></div>
                        <span className="text-sm font-medium">Success</span>
                      </div>
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-warning"></div>
                        <span className="text-sm font-medium">Warning</span>
                      </div>
                      <div className="flex items-center gap-2 p-2 bg-base-100 rounded-lg">
                        <div className="w-8 h-8 rounded-md bg-error"></div>
                        <span className="text-sm font-medium">Error</span>
                      </div>
                    </div>

                    {/* Example components */}
                    <div className="flex flex-col gap-3">
                      <h3 className="text-sm font-medium">
                        Preview Components
                      </h3>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <button className="btn btn-primary btn-sm w-full">
                          Primary
                        </button>
                        <button className="btn btn-secondary btn-sm w-full">
                          Secondary
                        </button>
                        <button className="btn btn-accent btn-sm w-full">
                          Accent
                        </button>
                        <button className="btn btn-neutral btn-sm w-full">
                          Neutral
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <SettingsCard key="system" />
          )}
        </div>
      </div>
    </div>
  );
}
