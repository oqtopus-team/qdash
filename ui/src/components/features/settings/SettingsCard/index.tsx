"use client";

import { useCallback } from "react";

import { useGetSettings } from "@/client/settings/settings";
import { useToast } from "@/components/ui/Toast";

export function SettingsCard() {
  const toast = useToast();
  const { data, isError, isLoading } = useGetSettings();

  const handleCopy = useCallback(
    (value: string) => {
      navigator.clipboard.writeText(value);
      toast.success("Copied to clipboard!");
    },
    [toast],
  );

  return (
    <section className="card card-border bg-base-100">
      <div className="card-body gap-5 p-5 sm:p-6">
        <div>
          <h2 className="card-title text-lg">System settings</h2>
          <p className="mt-1 text-sm text-base-content/60">
            Runtime configuration reported by the QDash API.
          </p>
        </div>

        {isLoading ? (
          <div className="flex h-28 items-center justify-center">
            <span className="loading loading-spinner loading-md" />
          </div>
        ) : isError ? (
          <div role="alert" className="alert alert-error alert-soft">
            <span>Failed to load settings</span>
          </div>
        ) : (
          <div className="divide-y divide-base-300 overflow-hidden rounded-box border border-base-300">
            {Object.entries(data?.data ?? {}).map(([key, value]) => (
              <div
                key={key}
                className="grid gap-2 p-4 sm:grid-cols-[minmax(10rem,0.35fr)_1fr_auto] sm:items-center"
              >
                <div className="text-sm font-medium">{key.toUpperCase().replace(/_/g, " ")}</div>
                <code className="break-all text-sm text-base-content/70">{String(value)}</code>
                <div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs"
                    onClick={() => handleCopy(String(value))}
                  >
                    Copy
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
