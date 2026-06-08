"use client";

import { useEffect, useState } from "react";
import { Check, Copy, Eye, EyeOff, Info, Loader2, Play } from "lucide-react";

import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";

type CurlMode = "standard" | "cloudflare";

type TestResult = {
  status: "success" | "error";
  message: string;
  responseBody: string;
};

const TEST_PATH = "/auth/me";

function getConfiguredApiUrl() {
  return process.env.NEXT_PUBLIC_API_URL || "/api";
}

function resolveApiUrl() {
  const normalizedApiUrl = getConfiguredApiUrl().replace(/\/$/, "");

  if (/^https?:\/\//.test(normalizedApiUrl)) {
    return normalizedApiUrl;
  }

  if (typeof window !== "undefined") {
    return `${window.location.origin}${normalizedApiUrl.startsWith("/") ? "" : "/"}${normalizedApiUrl}`;
  }

  return normalizedApiUrl || "http://127.0.0.1:5715";
}

function maskSecret(value: string) {
  if (!value) return "<cloudflare-client-secret>";
  if (value.length <= 8) return "********";
  return `${value.slice(0, 4)}...${value.slice(-4)}`;
}

function formatResponseBody(responseText: string, contentType: string) {
  if (!responseText) {
    return { parsedBody: null, responseBody: "<empty response>" };
  }

  if (!contentType.includes("application/json")) {
    return { parsedBody: null, responseBody: responseText };
  }

  try {
    const parsedBody = JSON.parse(responseText);
    return { parsedBody, responseBody: JSON.stringify(parsedBody, null, 2) };
  } catch {
    return { parsedBody: null, responseBody: responseText };
  }
}

export function ApiAccessTokenPanel() {
  const { accessToken } = useAuth();
  const { projectId } = useProject();
  const [copied, setCopied] = useState(false);
  const [copiedCurl, setCopiedCurl] = useState(false);
  const [copiedResponse, setCopiedResponse] = useState(false);
  const [curlMode, setCurlMode] = useState<CurlMode>("standard");
  const [showToken, setShowToken] = useState(false);
  const [showCfSecret, setShowCfSecret] = useState(false);
  const [apiUrl, setApiUrl] = useState(() => getConfiguredApiUrl().replace(/\/$/, ""));
  const [cfAccessClientId, setCfAccessClientId] = useState("");
  const [cfAccessClientSecret, setCfAccessClientSecret] = useState("");
  const [requestProjectId, setRequestProjectId] = useState("");
  const [isTestingCurl, setIsTestingCurl] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);

  useEffect(() => {
    setApiUrl(resolveApiUrl());
  }, []);

  useEffect(() => {
    setRequestProjectId((currentProjectId) => currentProjectId || projectId || "");
  }, [projectId]);

  const tokenForDisplay = showToken && accessToken ? accessToken : "<your-token>";
  const tokenForCopy = accessToken || "<your-token>";
  const projectIdForCopy = requestProjectId || "<project-id>";
  const cfClientIdForCopy = cfAccessClientId || "<cloudflare-client-id>";
  const cfClientSecretForCopy = cfAccessClientSecret || "<cloudflare-client-secret>";
  const cfClientIdForDisplay = cfAccessClientId || "<cloudflare-client-id>";
  const cfClientSecretForDisplay = showCfSecret
    ? cfClientSecretForCopy
    : maskSecret(cfAccessClientSecret);
  const curlHeaders =
    curlMode === "cloudflare"
      ? [
          `-H "CF-Access-Client-Id: ${cfClientIdForCopy}"`,
          `-H "CF-Access-Client-Secret: ${cfClientSecretForCopy}"`,
          `-H "Authorization: Bearer ${tokenForCopy}"`,
          `-H "X-Project-Id: ${projectIdForCopy}"`,
        ]
      : [`-H "Authorization: Bearer ${tokenForCopy}"`, `-H "X-Project-Id: ${projectIdForCopy}"`];
  const curlDisplayHeaders =
    curlMode === "cloudflare"
      ? [
          `-H "CF-Access-Client-Id: ${cfClientIdForDisplay}"`,
          `-H "CF-Access-Client-Secret: ${cfClientSecretForDisplay}"`,
          `-H "Authorization: Bearer ${tokenForDisplay}"`,
          `-H "X-Project-Id: ${projectIdForCopy}"`,
        ]
      : [`-H "Authorization: Bearer ${tokenForDisplay}"`, `-H "X-Project-Id: ${projectIdForCopy}"`];
  const curlLineBreak = " \\" + "\n  ";
  const curlCommand = ["curl", ...curlHeaders, `${apiUrl}${TEST_PATH}`].join(curlLineBreak);

  const handleCopyToken = async () => {
    if (!accessToken) return;
    await navigator.clipboard.writeText(accessToken);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCopyCurl = async () => {
    await navigator.clipboard.writeText(curlCommand);
    setCopiedCurl(true);
    setTimeout(() => setCopiedCurl(false), 2000);
  };

  const handleCopyResponse = async () => {
    if (!testResult) return;
    await navigator.clipboard.writeText(testResult.responseBody);
    setCopiedResponse(true);
    setTimeout(() => setCopiedResponse(false), 2000);
  };

  const handleRunCurl = async () => {
    setIsTestingCurl(true);
    setCopiedResponse(false);
    setTestResult(null);

    try {
      const headers = new Headers();
      headers.set("Authorization", `Bearer ${tokenForCopy}`);
      headers.set("X-Project-Id", projectIdForCopy);

      if (curlMode === "cloudflare") {
        headers.set("CF-Access-Client-Id", cfClientIdForCopy);
        headers.set("CF-Access-Client-Secret", cfClientSecretForCopy);
      }

      const response = await fetch(`${apiUrl}${TEST_PATH}`, { headers });
      const contentType = response.headers.get("content-type") || "";
      const responseText = await response.text();
      const { parsedBody, responseBody } = formatResponseBody(responseText, contentType);
      const username = typeof parsedBody?.username === "string" ? ` (${parsedBody.username})` : "";

      setTestResult({
        status: response.ok ? "success" : "error",
        message: `${response.status} ${response.statusText || "Response"}${username}`,
        responseBody: responseBody || "<empty response>",
      });
    } catch (error) {
      setTestResult({
        status: "error",
        message: error instanceof Error ? error.message : "Request failed",
        responseBody: error instanceof Error ? error.stack || error.message : "Request failed",
      });
    } finally {
      setIsTestingCurl(false);
    }
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
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <label className="text-sm font-medium">Example Usage (curl)</label>
              <div className="tabs tabs-boxed w-fit">
                <button
                  className={`tab tab-sm ${curlMode === "standard" ? "tab-active" : ""}`}
                  onClick={() => setCurlMode("standard")}
                  type="button"
                >
                  Standard
                </button>
                <button
                  className={`tab tab-sm ${curlMode === "cloudflare" ? "tab-active" : ""}`}
                  onClick={() => setCurlMode("cloudflare")}
                  type="button"
                >
                  Cloudflare
                </button>
              </div>
            </div>

            <label className="flex flex-col gap-1 text-sm font-medium">
              Project ID
              <input
                className="input input-bordered font-mono text-sm"
                onChange={(event) => setRequestProjectId(event.target.value)}
                placeholder="project-id"
                type="text"
                value={requestProjectId}
              />
            </label>

            {curlMode === "cloudflare" && (
              <div className="grid gap-3 md:grid-cols-2">
                <label className="flex flex-col gap-1 text-sm font-medium">
                  Client ID
                  <input
                    autoComplete="off"
                    className="input input-bordered font-mono text-sm"
                    name="qdash-cloudflare-access-client-id"
                    onChange={(event) => setCfAccessClientId(event.target.value)}
                    placeholder="cloudflare-client-id"
                    spellCheck={false}
                    type="text"
                    value={cfAccessClientId}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm font-medium">
                  Client Secret
                  <div className="flex gap-2">
                    <input
                      autoComplete="new-password"
                      className="input input-bordered w-full font-mono text-sm"
                      name="qdash-cloudflare-access-client-secret"
                      onChange={(event) => setCfAccessClientSecret(event.target.value)}
                      placeholder="cloudflare-client-secret"
                      spellCheck={false}
                      type={showCfSecret ? "text" : "password"}
                      value={cfAccessClientSecret}
                    />
                    <button
                      className="btn btn-square btn-ghost"
                      onClick={() => setShowCfSecret(!showCfSecret)}
                      type="button"
                    >
                      {showCfSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </label>
              </div>
            )}

            <div className="relative">
              <div className="mockup-code overflow-x-auto pr-28 text-xs sm:text-sm">
                <pre className="whitespace-pre-wrap break-all sm:whitespace-pre sm:break-normal">
                  <code>curl \</code>
                </pre>
                {curlDisplayHeaders.map((header) => (
                  <pre
                    className="whitespace-pre-wrap break-all sm:whitespace-pre sm:break-normal"
                    key={header}
                  >
                    <code> {header} \</code>
                  </pre>
                ))}
                <pre className="whitespace-pre-wrap break-all sm:whitespace-pre sm:break-normal">
                  <code>
                    {" "}
                    {apiUrl}
                    {TEST_PATH}
                  </code>
                </pre>
              </div>
              <div className="absolute right-2 top-2 flex gap-2">
                <button
                  className={`btn btn-xs sm:btn-sm ${testResult?.status === "success" ? "btn-success" : "btn-ghost"}`}
                  disabled={isTestingCurl}
                  onClick={handleRunCurl}
                  type="button"
                >
                  {isTestingCurl ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  <span className="hidden sm:inline">Run</span>
                </button>
                <button
                  className={`btn btn-xs sm:btn-sm ${copiedCurl ? "btn-success" : "btn-ghost"}`}
                  onClick={handleCopyCurl}
                  type="button"
                >
                  {copiedCurl ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  <span className="hidden sm:inline">{copiedCurl ? "Copied!" : "Copy"}</span>
                </button>
              </div>
            </div>
            {testResult && (
              <div className="flex flex-col gap-2">
                <div
                  className={`alert py-2 text-sm ${
                    testResult.status === "success" ? "alert-success" : "alert-error"
                  }`}
                >
                  <span>{testResult.message}</span>
                </div>
                <div className="relative">
                  <div className="mockup-code max-h-72 overflow-auto pr-24 text-xs sm:text-sm">
                    <pre className="whitespace-pre-wrap break-all sm:break-normal">
                      <code>{testResult.responseBody}</code>
                    </pre>
                  </div>
                  <button
                    className={`btn btn-xs absolute right-2 top-2 sm:btn-sm ${
                      copiedResponse ? "btn-success" : "btn-ghost"
                    }`}
                    onClick={handleCopyResponse}
                    type="button"
                  >
                    {copiedResponse ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    <span className="hidden sm:inline">{copiedResponse ? "Copied!" : "Copy"}</span>
                  </button>
                </div>
              </div>
            )}
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
