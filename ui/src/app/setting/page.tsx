"use client";

import { useState } from "react";

import { SettingsCard } from "./components/SettingsCard";

import { useAuth } from "@/app/contexts/AuthContext";
import { useTheme } from "@/app/providers/theme-provider";

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

type Tab = "appearance" | "api" | "system";

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const { accessToken } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>("appearance");
  const [copied, setCopied] = useState(false);
  const [showToken, setShowToken] = useState(false);

  const handleCopyToken = async () => {
    if (accessToken) {
      await navigator.clipboard.writeText(accessToken);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="w-full px-6">
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
            className={`tab ${activeTab === "api" ? "tab-active" : ""}`}
            onClick={() => setActiveTab("api")}
          >
            API Token
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
          ) : activeTab === "api" ? (
            <div className="card bg-base-200 shadow-lg" key="api">
              <div className="card-body">
                <h2 className="card-title text-xl mb-4">API Access Token</h2>
                <div className="flex flex-col gap-6">
                  <div className="flex flex-col gap-3">
                    <p className="text-sm text-base-content/70">
                      Use this token to authenticate API requests. Include it in
                      the Authorization header:
                    </p>
                    <code className="bg-base-300 p-3 rounded-lg text-sm">
                      Authorization: Bearer {"<your-token>"}
                    </code>
                  </div>

                  <div className="flex flex-col gap-3">
                    <label className="text-sm font-medium">
                      Your Access Token
                    </label>
                    <div className="flex flex-col gap-2">
                      <div className="join w-full">
                        <input
                          type={showToken ? "text" : "password"}
                          value={accessToken || ""}
                          readOnly
                          className="input input-bordered join-item flex-1 font-mono text-sm"
                        />
                        <button
                          className="btn join-item"
                          onClick={() => setShowToken(!showToken)}
                        >
                          {showToken ? (
                            <svg
                              xmlns="http://www.w3.org/2000/svg"
                              fill="none"
                              viewBox="0 0 24 24"
                              strokeWidth={1.5}
                              stroke="currentColor"
                              className="w-5 h-5"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88"
                              />
                            </svg>
                          ) : (
                            <svg
                              xmlns="http://www.w3.org/2000/svg"
                              fill="none"
                              viewBox="0 0 24 24"
                              strokeWidth={1.5}
                              stroke="currentColor"
                              className="w-5 h-5"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z"
                              />
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                              />
                            </svg>
                          )}
                        </button>
                        <button
                          className={`btn join-item ${copied ? "btn-success" : "btn-primary"}`}
                          onClick={handleCopyToken}
                        >
                          {copied ? (
                            <>
                              <svg
                                xmlns="http://www.w3.org/2000/svg"
                                fill="none"
                                viewBox="0 0 24 24"
                                strokeWidth={1.5}
                                stroke="currentColor"
                                className="w-5 h-5"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  d="M4.5 12.75l6 6 9-13.5"
                                />
                              </svg>
                              Copied!
                            </>
                          ) : (
                            <>
                              <svg
                                xmlns="http://www.w3.org/2000/svg"
                                fill="none"
                                viewBox="0 0 24 24"
                                strokeWidth={1.5}
                                stroke="currentColor"
                                className="w-5 h-5"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9.75a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184"
                                />
                              </svg>
                              Copy
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-col gap-3">
                    <label className="text-sm font-medium">
                      Example Usage (curl)
                    </label>
                    <div className="mockup-code text-sm">
                      <pre>
                        <code>
                          curl -H "Authorization: Bearer{" "}
                          {showToken && accessToken
                            ? accessToken
                            : "<your-token>"}
                          " \
                        </code>
                      </pre>
                      <pre>
                        <code> http://localhost:5715/api/auth/me</code>
                      </pre>
                    </div>
                  </div>

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
                      ></path>
                    </svg>
                    <div>
                      <p className="font-medium">Keep your token secure</p>
                      <p className="text-sm">
                        This token provides full access to your account. Do not
                        share it publicly.
                      </p>
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
