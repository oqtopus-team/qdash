"use client";

import { useEffect, useState } from "react";
import { useFetchConfig } from "@/client/settings/settings";

interface Settings {
  env: string;
  prefect_api_url: string;
  client_url: string;
  slack_bot_token: string;
}

export function SettingsCard() {
  const [setting, setSetting] = useState<Settings | null>(null);
  const { data, isError, isLoading } = useFetchConfig();

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
    <div className="card bg-base-200 my-5 shadow">
      <h5 className="card-title">Settings</h5>
      <div className="card-body my-3 code-block bg-base-100">
        <p className="card-text">ENV: {setting?.env}</p>
        <p className="card-text">PREFECT_API_URL: {setting?.prefect_api_url}</p>
        <p className="card-text">CLIENT_URL: {setting?.client_url}</p>
        <p className="card-text">SLACK_BOT_TOKEN: {setting?.slack_bot_token}</p>
      </div>
    </div>
  );
}
