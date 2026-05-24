"use client";

import { useState } from "react";
import { Check, Copy, Info } from "lucide-react";

export function ApiAccessTokenPanel() {
  const [copiedCurl, setCopiedCurl] = useState(false);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:5715";

  const handleCopyCurl = async () => {
    const curlCommand = `curl -H "Authorization: Bearer <your-api-token>" ${apiUrl}/auth/me`;
    await navigator.clipboard.writeText(curlCommand);
    setCopiedCurl(true);
    setTimeout(() => setCopiedCurl(false), 2000);
  };

  return (
    <div className="card bg-base-200 shadow-lg" key="api">
      <div className="card-body">
        <h2 className="card-title text-xl mb-4">API Access Token</h2>
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <p className="text-sm text-base-content/70">
              Browser sessions are stored in an HttpOnly cookie and are not exposed here. For
              external API access, use a dedicated API token and include it in the Authorization
              header:
            </p>
            <code className="rounded-lg bg-base-300 p-3 text-sm">
              Authorization: Bearer {"<your-api-token>"}
            </code>
          </div>

          <div className="flex flex-col gap-3">
            <label className="text-sm font-medium">Example Usage (curl)</label>
            <div className="relative">
              <div className="mockup-code overflow-x-auto text-xs sm:text-sm">
                <pre className="whitespace-pre-wrap break-all sm:whitespace-pre sm:break-normal">
                  <code>curl -H "Authorization: Bearer {"<your-api-token>"}" \</code>
                </pre>
                <pre>
                  <code> {apiUrl}/auth/me</code>
                </pre>
              </div>
              <button
                className={`btn btn-xs absolute right-2 top-2 sm:btn-sm ${
                  copiedCurl ? "btn-success" : "btn-ghost"
                }`}
                onClick={handleCopyCurl}
              >
                {copiedCurl ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                <span className="hidden sm:inline">{copiedCurl ? "Copied!" : "Copy"}</span>
              </button>
            </div>
          </div>

          <div className="alert alert-info">
            <Info className="h-6 w-6 shrink-0" />
            <div>
              <p className="font-medium">Keep your token secure</p>
              <p className="text-sm">
                API tokens provide account access. Do not store them in browser localStorage or
                commit them to source control.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
