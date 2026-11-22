"use client";

import { CircleStop } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useStopAgentSession } from "@/client/agent-session/agent-session";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import type { StopAgentSessionResponse } from "@/schemas";
import { getApiErrorMessage } from "@/lib/utils/apiError";

import { projectRequest } from "./useLinkedProject";

/** What the stop left running, in words; QDash does not cancel any of it. */
export function stopOutcomeMessage(result: StopAgentSessionResponse): string {
  const running = result.in_flight ?? [];
  const head =
    result.outcome === "already_ended"
      ? `The session had already ended (${result.session.status})`
      : "Session stopped";
  if (result.outcome === "already_ended" || running.length === 0) return head;
  return `${head}. Still running and not cancelled: ${running
    .map((op) => `${op.kind.replace(/_/g, " ")} ${op.id} (${op.status})`)
    .join(", ")}`;
}

/**
 * Stop an active or paused agent session: QDash refuses every new step, commit, apply, and
 * resume in it. A measurement already sent keeps running; the result says which.
 */
export function StopAgentSessionButton({
  sessionId,
  projectId,
  onStopped,
}: {
  sessionId: string;
  projectId: string;
  onStopped: () => void;
}) {
  const stop = useStopAgentSession({ request: projectRequest(projectId) });
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());

  const submit = () => {
    stop.mutate(
      { sessionId, data: { idempotency_key: idempotencyKey, reason: reason.trim() } },
      {
        onSuccess: (response) => {
          setOpen(false);
          toast.success(stopOutcomeMessage(response.data));
          onStopped();
        },
        onError: (error) => {
          setIdempotencyKey(crypto.randomUUID());
          toast.error(getApiErrorMessage(error, "The session was not stopped"));
          onStopped();
        },
      },
    );
  };

  return (
    <>
      <button
        type="button"
        className="btn btn-sm btn-error btn-outline"
        onClick={() => setOpen(true)}
      >
        <CircleStop data-icon="inline-start" aria-hidden="true" />
        Stop session
      </button>
      <Dialog open={open} onOpenChange={(next) => !next && !stop.isPending && setOpen(false)}>
        <DialogContent>
          <DialogTitle className="mb-2">Stop this agent session?</DialogTitle>
          <DialogDescription className="mb-3 text-sm text-base-content/70">
            The agent can no longer run, commit, apply, or resume anything in this session, and it
            cannot be restarted. A measurement already sent to the hardware is not cancelled; its
            result is still recorded.
          </DialogDescription>
          <fieldset className="fieldset">
            <legend className="fieldset-legend">Reason</legend>
            <textarea
              className="textarea w-full"
              rows={3}
              maxLength={2000}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Why the session is stopped, for the audit"
            />
          </fieldset>
          <div className="modal-action">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setOpen(false)}
              disabled={stop.isPending}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-error"
              onClick={submit}
              disabled={stop.isPending || reason.trim() === ""}
            >
              {stop.isPending ? (
                <span data-icon="inline-start" className="loading loading-spinner loading-xs" />
              ) : (
                <CircleStop data-icon="inline-start" aria-hidden="true" />
              )}
              Stop session
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
