"use client";

import { useState } from "react";

import { ExternalLink, RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  getGetChatGPTConnectionQueryKey,
  useAcknowledgeChatGPTWelcome,
  useCompleteChatGPTAuthorization,
  useDisconnectChatGPT,
  useGetChatGPTConnection,
  useRefreshChatGPTModels,
  useStartChatGPTAuthorization,
} from "@/client/copilot/copilot";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import type { ChatGPTConnectionStatus, StartChatGPTAuthorizationResponse } from "@/schemas";
import { CHATGPT_USAGE_URL } from "@/lib/copilotModels";
import { getApiErrorMessage } from "@/lib/utils/apiError";

const USAGE_LIMIT_CODES = new Set([
  "subscription_sharing_usage_limit_exceeded",
  "subscription_sharing_workplace_individual_usage_limit_exceeded",
]);

/** The status line of a connection: a dot and a short sentence. */
function connectionSummary(connection: ChatGPTConnectionStatus): {
  tone: "status-success" | "status-warning" | "status-neutral";
  text: string;
} {
  switch (connection.status) {
    case "connected":
      return {
        tone: "status-success",
        text: connection.email ? `Connected as ${connection.email}` : "Connected",
      };
    case "plan_disabled":
      return {
        tone: "status-warning",
        text: "Signed in, but ChatGPT plan usage is not enabled",
      };
    case "reauth_required":
      return { tone: "status-warning", text: "The ChatGPT session ended. Connect again." };
    case "signed_out":
      return {
        tone: "status-neutral",
        text: connection.email ? `Disconnected (${connection.email})` : "Disconnected",
      };
    default:
      return { tone: "status-neutral", text: "Not connected" };
  }
}

function ManageUsageLink({ url, className = "" }: { url: string; className?: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className={`link link-hover inline-flex items-center gap-1 ${className}`}
    >
      Manage usage
      <ExternalLink className="h-3 w-3" aria-hidden />
    </a>
  );
}

/**
 * The second half of signing in. ChatGPT sends the browser to a 127.0.0.1
 * address, which reaches the user's own computer rather than QDash, so the
 * user brings that address back here.
 */
function FinishSignIn({
  attempt,
  pending,
  onSubmit,
  onCancel,
}: {
  attempt: StartChatGPTAuthorizationResponse;
  pending: boolean;
  onSubmit: (callbackUrl: string) => void;
  onCancel: () => void;
}) {
  const [callbackUrl, setCallbackUrl] = useState("");
  const looksRight = callbackUrl.trim().startsWith(attempt.redirect_uri);

  return (
    <div className="flex flex-col gap-4 rounded-box bg-base-100 p-4">
      <ol className="flex list-decimal flex-col gap-2 pl-5 text-sm">
        <li>
          <a
            href={attempt.authorization_url}
            target="_blank"
            rel="noopener noreferrer"
            className="link inline-flex items-center gap-1"
          >
            Open the ChatGPT sign-in page
            <ExternalLink className="h-3 w-3" aria-hidden />
          </a>{" "}
          and approve QDash.
        </li>
        <li>
          ChatGPT then sends your browser to an address that starts with{" "}
          <code className="break-all font-mono text-xs">{attempt.redirect_uri}</code>. That page
          does not load, which is expected. Copy the whole address from the address bar.
        </li>
        <li>Paste it below. This sign-in expires in 10 minutes.</li>
      </ol>
      <form
        className="flex flex-col gap-2 sm:flex-row sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          if (looksRight) onSubmit(callbackUrl.trim());
        }}
      >
        <fieldset className="fieldset w-full">
          <legend id="chatgpt-callback-label" className="fieldset-legend">
            Address from the browser
          </legend>
          <input
            type="url"
            className={`input w-full font-mono text-xs ${
              callbackUrl && !looksRight ? "input-error" : ""
            }`}
            placeholder={`${attempt.redirect_uri}?code=…`}
            value={callbackUrl}
            onChange={(event) => setCallbackUrl(event.target.value)}
            autoComplete="off"
            spellCheck={false}
            disabled={pending}
            aria-labelledby="chatgpt-callback-label"
            aria-describedby="chatgpt-callback-help"
          />
          <p id="chatgpt-callback-help" className="label">
            {callbackUrl && !looksRight
              ? `The address must start with ${attempt.redirect_uri}`
              : "QDash checks it once and does not keep it."}
          </p>
        </fieldset>
        <div className="flex gap-2 sm:mb-6">
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={pending}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={!looksRight || pending}>
            {pending && <span className="loading loading-spinner loading-xs" />}
            Finish connecting
          </button>
        </div>
      </form>
    </div>
  );
}

/**
 * Connect, check and disconnect the user's own ChatGPT plan for Copilot chat.
 *
 * Tokens never reach the browser: QDash keeps them on the server and uses
 * them only for this user's chat turns with a ChatGPT model.
 */
export function ChatGPTConnectionSettings() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { data, isLoading, isError } = useGetChatGPTConnection({ query: { retry: false } });
  const connection = data?.data;
  const [attempt, setAttempt] = useState<StartChatGPTAuthorizationResponse | null>(null);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);

  const store = (next: ChatGPTConnectionStatus) =>
    queryClient.setQueryData(getGetChatGPTConnectionQueryKey(), (previous: unknown) =>
      previous && typeof previous === "object"
        ? { ...(previous as object), data: next }
        : { data: next, status: 200, headers: new Headers() },
    );
  const refetch = () =>
    queryClient.invalidateQueries({ queryKey: getGetChatGPTConnectionQueryKey() });

  const start = useStartChatGPTAuthorization({
    mutation: {
      onSuccess: (response) => setAttempt(response.data),
      onError: (error) => toast.error(getApiErrorMessage(error, "Could not start signing in")),
    },
  });
  const complete = useCompleteChatGPTAuthorization({
    mutation: {
      onSuccess: (response) => {
        setAttempt(null);
        store(response.data);
        toast.success("ChatGPT connected");
      },
      onError: (error) => toast.error(getApiErrorMessage(error, "Could not finish connecting")),
    },
  });
  const disconnect = useDisconnectChatGPT({
    mutation: {
      onSuccess: (response) => {
        setConfirmDisconnect(false);
        refetch();
        if (response.data.revocation_confirmed) {
          toast.success("ChatGPT disconnected");
        } else {
          toast.warning(
            "Disconnected in QDash, but ChatGPT did not confirm the sign-out. You can also remove QDash in ChatGPT settings.",
          );
        }
      },
      onError: (error) => toast.error(getApiErrorMessage(error, "Could not disconnect")),
    },
  });
  const reloadModels = useRefreshChatGPTModels({
    mutation: {
      onSuccess: (response) => store(response.data),
      onError: (error) => toast.error(getApiErrorMessage(error, "Could not load the models")),
    },
  });
  const acknowledge = useAcknowledgeChatGPTWelcome({
    mutation: { onSuccess: (response) => store(response.data) },
  });

  const begin = (options: { new_account?: boolean; enable_plan?: boolean } = {}) =>
    start.mutate({ data: { new_account: false, enable_plan: false, ...options } });

  if (isLoading) {
    return <div className="skeleton h-24 w-full" aria-label="Loading the ChatGPT connection" />;
  }
  if (isError || !connection) {
    return (
      <div role="alert" className="alert alert-warning alert-soft text-sm">
        <span>Could not load your ChatGPT connection.</span>
      </div>
    );
  }

  const summary = connectionSummary(connection);
  const usageUrl = connection.usage_url || CHATGPT_USAGE_URL;
  const models = (connection.models ?? []).filter((model) => model.supported !== false);
  const lastError = connection.last_error ?? null;
  const usageLimited = lastError ? USAGE_LIMIT_CODES.has(lastError.code) : false;

  return (
    <section className="flex flex-col gap-3" aria-labelledby="chatgpt-plan-heading">
      <div className="flex flex-col gap-1">
        <h3 id="chatgpt-plan-heading" className="text-sm font-medium">
          Use your ChatGPT plan
        </h3>
        <p className="text-sm text-base-content/60">
          Answer your Copilot chats with usage included in your own ChatGPT plan or credits. This is
          separate from the models this QDash server provides. Only chats you send with a ChatGPT
          model use it; AI evaluations, forum replies and other background work keep using the
          server&apos;s models.
        </p>
      </div>

      {!connection.available ? (
        <div role="status" className="alert alert-info alert-soft text-sm">
          <span>
            ChatGPT connections are not set up on this QDash server. Ask an operator to enable them.
          </span>
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-3 rounded-box bg-base-100 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-center gap-2 text-sm">
              <span className={`status ${summary.tone}`} aria-hidden />
              <span className="truncate">{summary.text}</span>
            </div>
            {!attempt && (
              <div className="flex flex-wrap gap-2">
                {connection.status === "connected" ? (
                  <>
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost"
                      onClick={() => reloadModels.mutate()}
                      disabled={reloadModels.isPending}
                    >
                      <RefreshCw
                        className={`h-3.5 w-3.5 ${reloadModels.isPending ? "animate-spin" : ""}`}
                      />
                      Reload models
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm btn-error btn-outline"
                      onClick={() => setConfirmDisconnect(true)}
                    >
                      Disconnect
                    </button>
                  </>
                ) : connection.status === "plan_disabled" ? (
                  <>
                    <button
                      type="button"
                      className="btn btn-sm btn-neutral"
                      onClick={() => begin({ enable_plan: true })}
                      disabled={start.isPending}
                    >
                      Enable ChatGPT plan usage
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost"
                      onClick={() => setConfirmDisconnect(true)}
                    >
                      Disconnect
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      className="btn btn-sm btn-neutral"
                      onClick={() => begin()}
                      disabled={start.isPending}
                    >
                      {start.isPending && <span className="loading loading-spinner loading-xs" />}
                      Continue with ChatGPT
                    </button>
                    {connection.can_reconnect && (
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost"
                        onClick={() => begin({ new_account: true })}
                        disabled={start.isPending}
                      >
                        Use a different account
                      </button>
                    )}
                  </>
                )}
              </div>
            )}
          </div>

          {attempt && (
            <FinishSignIn
              attempt={attempt}
              pending={complete.isPending}
              onSubmit={(callbackUrl) => complete.mutate({ data: { callback_url: callbackUrl } })}
              onCancel={() => setAttempt(null)}
            />
          )}

          {lastError && (
            <div role="status" className="alert alert-warning alert-soft text-sm">
              <div className="flex flex-col gap-1">
                <span>{usageLimited ? "Usage limit reached" : lastError.message}</span>
                {usageLimited && (
                  <span className="text-base-content/70">
                    The limit may apply to your ChatGPT plan or to QDash. Review it in ChatGPT
                    settings.
                  </span>
                )}
              </div>
              {usageLimited && <ManageUsageLink url={usageUrl} className="font-medium" />}
            </div>
          )}

          {connection.status === "connected" && (
            <div className="flex flex-col gap-1 text-sm text-base-content/60">
              <span>
                {models.length > 0
                  ? `Models for your chats: ${models.map((model) => model.display_name).join(", ")}. Choose one below or in the chat.`
                  : "Your ChatGPT account offers no model QDash can run yet. Try Reload models later."}
              </span>
              <ManageUsageLink url={usageUrl} className="w-fit" />
            </div>
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmDisconnect}
        title="Disconnect ChatGPT?"
        description="QDash stops using your ChatGPT plan, signs out of the session and deletes its copy of your tokens. Chats set to a ChatGPT model stop working until you connect again."
        confirmLabel="Disconnect"
        destructive
        pending={disconnect.isPending}
        onConfirm={() => disconnect.mutate()}
        onOpenChange={setConfirmDisconnect}
      />

      <Dialog
        open={connection.welcome_pending}
        onOpenChange={(open) => {
          if (!open && !acknowledge.isPending) acknowledge.mutate();
        }}
      >
        <DialogContent className="max-w-md">
          <DialogTitle>You&apos;re using your ChatGPT plan</DialogTitle>
          <DialogDescription className="mt-2 text-sm text-base-content/70">
            Copilot chats you send with a ChatGPT model now use your ChatGPT plan. You can review
            and manage this usage in ChatGPT settings.
          </DialogDescription>
          <div className="modal-action items-center">
            <ManageUsageLink url={usageUrl} className="mr-auto text-sm" />
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => acknowledge.mutate()}
              disabled={acknowledge.isPending}
            >
              Got it
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}
