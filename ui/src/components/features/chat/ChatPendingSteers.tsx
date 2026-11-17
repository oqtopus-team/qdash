"use client";

import { Clock, CornerDownRight, X } from "lucide-react";
import {
  canCheckSteer,
  canResendSteer,
  isListedSteer,
  isOpenSteer,
  steerStatusText,
  type PendingSteer,
} from "@/lib/copilotSteer";

/**
 * Messages sent while the answer was streaming that it has not read yet, or
 * that never reached it. A message the answer read moves into the thread at
 * the place it landed and leaves this list.
 */
export function ChatPendingSteers({
  steers,
  isStreaming,
  onResend,
  onCheck,
  onDismiss,
}: {
  steers: PendingSteer[];
  isStreaming: boolean;
  /** Send it again: to the answer streaming now, or as a new message. Only once it was not delivered. */
  onResend: (requestId: string) => void;
  /** Ask again whether the answer read an unconfirmed one; never sends it. */
  onCheck?: (requestId: string) => void;
  onDismiss: (requestId: string) => void;
}) {
  // One placed in the conversation shows there, not here, while it is saved.
  const listed = steers.filter(isListedSteer);
  if (listed.length === 0) return null;
  return (
    <ul className="flex flex-col items-end gap-2" aria-label="Messages waiting for the answer">
      {listed.map((steer) => {
        const open = isOpenSteer(steer);
        return (
          <li
            key={steer.requestId}
            className="flex flex-col items-end gap-1 max-w-[85%] animate-fade-in-up"
          >
            <div
              className={`chat-bubble-user-soft rounded-3xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words ${
                open ? "opacity-70" : "opacity-50"
              }`}
            >
              {steer.text}
            </div>
            <div className="flex flex-wrap items-center justify-end gap-1 text-xs text-base-content/55">
              {open ? (
                <Clock className="w-3 h-3" aria-hidden="true" />
              ) : (
                <CornerDownRight className="w-3 h-3" aria-hidden="true" />
              )}
              <span role="status">{steerStatusText(steer)}</span>
              {onCheck && canCheckSteer(steer) && (
                <button
                  type="button"
                  onClick={() => onCheck(steer.requestId)}
                  className="btn btn-ghost btn-xs rounded-full"
                >
                  Check again
                </button>
              )}
              {canResendSteer(steer) && (
                <button
                  type="button"
                  onClick={() => onResend(steer.requestId)}
                  className="btn btn-ghost btn-xs rounded-full"
                >
                  {isStreaming ? "Send again" : "Send as new message"}
                </button>
              )}
              {!open && (
                <button
                  type="button"
                  onClick={() => onDismiss(steer.requestId)}
                  className="btn btn-ghost btn-xs btn-square"
                  aria-label="Dismiss"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** One line about the chat that is not a message, such as a continue with nothing to do. */
export function ChatNotice({ text, onDismiss }: { text: string; onDismiss: () => void }) {
  return (
    <div role="status" className="alert alert-soft text-sm py-2">
      <span className="break-words min-w-0">{text}</span>
      <button
        type="button"
        onClick={onDismiss}
        className="btn btn-ghost btn-xs btn-square"
        aria-label="Dismiss"
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}
