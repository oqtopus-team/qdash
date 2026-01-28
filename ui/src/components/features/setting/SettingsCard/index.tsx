"use client";

import { useEffect, useState, useCallback } from "react";

import { Toast } from "../Toast";

import { useGetSettings } from "@/client/settings/settings";
import { Settings } from "@/schemas/settings";

export function SettingsCard() {
  const [setting, setSetting] = useState<Settings | null>(null);
  const [showToast, setShowToast] = useState(false);
  const { data, isError, isLoading } = useGetSettings();

  const handleCopy = useCallback((value: string) => {
    navigator.clipboard.writeText(value);
    setShowToast(true);
  }, []);

  useEffect(() => {
    if (data) {
      setSetting(data.data);
    }
  }, [data]);

  if (isLoading) {
    return <div>Loading...</div>;
  }
  if (isError) {
    return <div>Error</div>;
  }

  return (
    <div className="card bg-base-200 shadow-lg">
      <div className="card-body">
        <h2 className="card-title text-xl mb-4">System Settings</h2>
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <span className="loading loading-spinner loading-md"></span>
          </div>
        ) : isError ? (
          <div className="alert alert-error">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="stroke-current shrink-0 h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>Failed to load settings</span>
          </div>
        ) : (
          <div className="grid gap-4">
            {Object.entries(setting || {}).map(([key, value]) => (
              <div key={key} className="bg-base-100 p-4 rounded-lg">
                <div className="flex justify-between items-center mb-2">
                  <label className="text-sm font-medium">
                    {key.toUpperCase().replace(/_/g, " ")}
                  </label>
                  <button
                    className="btn btn-ghost btn-xs"
                    onClick={() => handleCopy(String(value))}
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-4 w-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                      />
                    </svg>
                  </button>
                </div>
                <div className="font-mono text-sm bg-base-200 p-2 rounded break-all">
                  {value}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {showToast && (
        <Toast
          message="Copied to clipboard!"
          onClose={() => setShowToast(false)}
        />
      )}
    </div>
  );
}
