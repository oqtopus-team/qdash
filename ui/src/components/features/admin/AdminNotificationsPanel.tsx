"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Bell, Loader2 } from "lucide-react";

import {
  getGetAdminSystemSettingsQueryKey,
  useGetAdminSystemSettings,
  useUpdateAdminSystemSettings,
} from "@/client/admin/admin";

export function AdminNotificationsPanel() {
  const queryClient = useQueryClient();
  const { data, isError, isLoading } = useGetAdminSystemSettings();
  const mutation = useUpdateAdminSystemSettings({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getGetAdminSystemSettingsQueryKey() });
      },
    },
  });

  const settings = data?.data;
  const isEnabled = settings?.slack_forum_notifications_enabled ?? false;
  const webhookConfigured = settings?.slack_webhook_configured ?? false;
  const isSaving = mutation.isPending;
  const toggleDisabled = isLoading || isSaving || !webhookConfigured;

  return (
    <div className="card bg-base-200 shadow-lg">
      <div className="card-body">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-base-100 p-2 text-primary">
              <Bell size={20} aria-hidden="true" />
            </div>
            <div>
              <h2 className="card-title text-xl">Notifications</h2>
              <p className="text-sm text-base-content/70">
                Send Slack webhook notifications when forum threads are created.
              </p>
            </div>
          </div>
          <label className="flex items-center gap-3">
            {isSaving && <Loader2 size={16} className="animate-spin text-base-content/60" />}
            <input
              type="checkbox"
              className="toggle toggle-primary"
              checked={isEnabled && webhookConfigured}
              disabled={toggleDisabled}
              onChange={(event) => {
                mutation.mutate({
                  data: { slack_forum_notifications_enabled: event.target.checked },
                });
              }}
              aria-label="Enable Slack forum notifications"
            />
          </label>
        </div>

        {isLoading && (
          <div className="flex h-16 items-center">
            <span className="loading loading-spinner loading-md" />
          </div>
        )}
        {isError && (
          <div className="alert alert-error">
            <span>Failed to load notification settings.</span>
          </div>
        )}
        {mutation.isError && (
          <div className="alert alert-error">
            <span>Failed to update notification settings.</span>
          </div>
        )}
        {!isLoading && !webhookConfigured && (
          <div className="alert alert-warning">
            <span>Set SLACK_WEBHOOK_URL in .env to enable Slack forum notifications.</span>
          </div>
        )}
      </div>
    </div>
  );
}
