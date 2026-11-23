"use client";

import { Archive } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useCloseCalibrationSession } from "@/client/calibration-session/calibration-session";
import { projectRequest } from "@/components/features/agent-session/useLinkedProject";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { getApiErrorMessage } from "@/lib/utils/apiError";

/**
 * Close a calibration session: no new pipeline run or agent session can start in it. Closing
 * stops nothing and records no verdict on the objective, and QDash refuses it while a run or
 * agent session in it still runs, waits, or is being started. A pipeline run, or an agent session
 * start, whose outcome is unknown is closed over only after the person confirms they checked it.
 * Such a pipeline run was already admitted: it may be running or may still start after the close,
 * which does not cancel it. Such an agent session was never admitted and can never operate.
 */
export function CloseCalibrationSessionButton({
  calibrationSessionId,
  projectId,
  blockers,
  unknownRuns,
  unknownAgentStarts = [],
  onClosed,
}: {
  calibrationSessionId: string;
  projectId: string;
  blockers: string[];
  unknownRuns: string[];
  /** Agent sessions whose start was reserved long ago and never recorded. */
  unknownAgentStarts?: string[];
  onClosed: () => void;
}) {
  const close = useCloseCalibrationSession({ request: projectRequest(projectId) });
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const blocked = blockers.length > 0;
  const hasUnknown = unknownRuns.length > 0 || unknownAgentStarts.length > 0;
  const needsAcknowledgment = hasUnknown && !acknowledged;

  const submit = () => {
    close.mutate(
      {
        calibrationSessionId,
        data: { closing_note: note.trim(), acknowledge_unknown_runs: acknowledged },
      },
      {
        onSuccess: () => {
          setOpen(false);
          toast.success("Calibration session closed");
          onClosed();
        },
        onError: (error) => {
          toast.error(getApiErrorMessage(error, "The calibration session was not closed"));
          onClosed();
        },
      },
    );
  };

  return (
    <>
      <button type="button" className="btn btn-sm" onClick={() => setOpen(true)}>
        <Archive data-icon="inline-start" aria-hidden="true" />
        Close session
      </button>
      <Dialog open={open} onOpenChange={(next) => !next && !close.isPending && setOpen(false)}>
        <DialogContent>
          <DialogTitle className="mb-2">Close this calibration session?</DialogTitle>
          <DialogDescription className="mb-3 text-sm text-base-content/70">
            It accepts no new pipeline run or agent session. Closing cancels nothing already
            admitted and does not record whether the objective was met.
          </DialogDescription>
          {blocked ? (
            <div role="alert" className="alert alert-warning alert-soft mb-3 text-sm">
              <div>
                <p>It cannot be closed while work in it still runs, waits, or is being started:</p>
                <ul className="mt-1 list-disc pl-4">
                  {blockers.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : null}
          {!blocked && hasUnknown ? (
            <label className="choice-field mb-3 gap-2 text-sm">
              <input
                type="checkbox"
                className="checkbox checkbox-sm"
                checked={acknowledged}
                onChange={(event) => setAcknowledged(event.target.checked)}
              />
              <span>
                {unknownRuns.length > 0
                  ? `I checked the Execution list: pipeline runs ${unknownRuns.join(", ")} were admitted and QDash cannot tell whether they started. They may be running, or may still start after I close; closing does not cancel them. `
                  : ""}
                {unknownAgentStarts.length > 0
                  ? `I checked the agent sessions: agent sessions ${unknownAgentStarts.join(", ")} were being started when their request stopped. They were never admitted: if one is recorded later, QDash rejects it and it never operates.`
                  : ""}
              </span>
            </label>
          ) : null}
          <fieldset className="fieldset">
            <legend className="fieldset-legend">Note</legend>
            <textarea
              className="textarea w-full"
              rows={3}
              maxLength={2000}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="What to record with the closure"
            />
          </fieldset>
          <div className="modal-action">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setOpen(false)}
              disabled={close.isPending}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn"
              onClick={submit}
              disabled={close.isPending || blocked || needsAcknowledgment}
            >
              {close.isPending ? (
                <span data-icon="inline-start" className="loading loading-spinner loading-xs" />
              ) : (
                <Archive data-icon="inline-start" aria-hidden="true" />
              )}
              Close session
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
