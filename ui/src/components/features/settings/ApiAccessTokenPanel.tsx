"use client";

import { useState } from "react";
import { Check, Copy, Eye, EyeOff, Info } from "lucide-react";

import { useAuth } from "@/contexts/AuthContext";

export function ApiAccessTokenPanel() {
  const { accessToken } = useAuth();
  const [copied, setCopied] = useState(false);
  const [copiedCurl, setCopiedCurl] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:5715";

  const handleCopyToken = async () => {
    if (!accessToken) return;
    await navigator.clipboard.writeText(accessToken);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCopyCurl = async () => {
    const token = accessToken || "<your-token>";
    const curlCommand = `curl -H "Authorization: Bearer ${token}" ${apiUrl}/auth/me`;
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
              Use this token to authenticate API requests. Include it in the Authorization header:
            </p>
            <code className="rounded-lg bg-base-300 p-3 text-sm">
              Authorization: Bearer {"<your-token>"}
            </code>
          </div>

          <div className="flex flex-col gap-3">
            <label className="text-sm font-medium">Your Access Token</label>
            <div className="flex flex-col gap-2">
              <input
                type={showToken ? "text" : "password"}
                value={accessToken || ""}
                readOnly
                className="input input-bordered w-full font-mono text-sm"
              />
              <div className="flex gap-2">
                <button className="btn btn-sm flex-1" onClick={() => setShowToken(!showToken)}>
                  {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  <span className="hidden sm:inline">{showToken ? "Hide" : "Show"}</span>
                </button>
                <button
                  className={`btn btn-sm flex-1 ${copied ? "btn-success" : "btn-primary"}`}
                  onClick={handleCopyToken}
                >
                  {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  <span className="hidden sm:inline">{copied ? "Copied!" : "Copy"}</span>
                </button>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <label className="text-sm font-medium">Example Usage (curl)</label>
            <div className="relative">
              <div className="mockup-code overflow-x-auto text-xs sm:text-sm">
                <pre className="whitespace-pre-wrap break-all sm:whitespace-pre sm:break-normal">
                  <code>
                    curl -H "Authorization: Bearer{" "}
                    {showToken && accessToken ? accessToken : "<your-token>"}" \
                  </code>
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
                This token provides full access to your account. Do not share it publicly.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
