"use client";

import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useQueryClient } from "@tanstack/react-query";

import {
  getListCooldownWiringEventsQueryKey,
  useCreateCooldownWiringCheckpoint,
  useListCooldownWiringEvents,
} from "@/client/cooldown-wiring/cooldown-wiring";
import { formatDateTime, formatRelativeTime } from "@/lib/utils/datetime";
import type { CooldownWiringEventResponse } from "@/schemas";

interface CooldownWiringHistoryProps {
  cooldownId: string;
}

export function CooldownWiringHistory({
  cooldownId,
}: CooldownWiringHistoryProps) {
  const queryClient = useQueryClient();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data, isLoading } = useListCooldownWiringEvents(cooldownId);
  const events: CooldownWiringEventResponse[] = data?.data?.events ?? [];

  const createCheckpoint = useCreateCooldownWiringCheckpoint({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getListCooldownWiringEventsQueryKey(cooldownId),
        });
      },
    },
  });

  const openModal = () => {
    setComment("");
    setError(null);
    dialogRef.current?.showModal();
  };

  const submit = async () => {
    const trimmed = comment.trim();
    if (!trimmed) {
      setError("Please describe what changed.");
      return;
    }
    try {
      await createCheckpoint.mutateAsync({
        cooldownId,
        data: { comment: trimmed },
      });
      dialogRef.current?.close();
    } catch {
      setError("Failed to save checkpoint. Please try again.");
    }
  };

  return (
    <div className="text-xs">
      <div className="flex items-center justify-between mb-1">
        <span className="text-base-content/60 font-semibold uppercase tracking-wide">
          Wiring history
        </span>
        <button
          type="button"
          className="btn btn-xs btn-primary"
          onClick={openModal}
        >
          Save checkpoint
        </button>
      </div>

      {isLoading ? (
        <div className="text-base-content/50 italic">Loading…</div>
      ) : events.length === 0 ? (
        <div className="text-base-content/50 italic">
          No checkpoints yet. Click <em>Save checkpoint</em> after a wiring
          change to record it here.
        </div>
      ) : (
        <ul className="space-y-1">
          {events.map((ev) => (
            <CheckpointRow
              key={ev.id}
              event={ev}
              expanded={expandedId === ev.id}
              onToggle={() =>
                setExpandedId((cur) => (cur === ev.id ? null : ev.id))
              }
            />
          ))}
        </ul>
      )}

      <dialog ref={dialogRef} className="modal">
        <div className="modal-box max-w-md">
          <h3 className="font-semibold text-sm mb-2">Save wiring checkpoint</h3>
          <p className="text-xs text-base-content/60 mb-3">
            Capture the current wiring as a snapshot. Briefly describe what
            changed (required).
          </p>
          <textarea
            className="textarea textarea-bordered w-full text-sm"
            rows={3}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="e.g. Swapped MUX line on Q3 readout after warm-up"
            maxLength={2000}
            autoFocus
          />
          {error && (
            <div className="text-error text-xs mt-1" role="alert">
              {error}
            </div>
          )}
          <div className="modal-action">
            <form method="dialog">
              <button type="submit" className="btn btn-sm btn-ghost">
                Cancel
              </button>
            </form>
            <button
              type="button"
              className="btn btn-sm btn-primary"
              disabled={createCheckpoint.isPending}
              onClick={submit}
            >
              {createCheckpoint.isPending ? "Saving…" : "Save checkpoint"}
            </button>
          </div>
        </div>
        <form method="dialog" className="modal-backdrop">
          <button type="submit">close</button>
        </form>
      </dialog>
    </div>
  );
}

function CheckpointRow({
  event,
  expanded,
  onToggle,
}: {
  event: CooldownWiringEventResponse;
  expanded: boolean;
  onToggle: () => void;
}) {
  const hasSnapshot = event.wiring_info_snapshot.trim().length > 0;
  return (
    <li className="border border-base-300 rounded px-2 py-1.5">
      <button
        type="button"
        className="flex w-full items-start gap-2 text-left"
        onClick={onToggle}
      >
        <span className="text-base-content/50 shrink-0 w-4">
          {expanded ? "▾" : "▸"}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span
              className="font-mono text-base-content/70"
              title={formatDateTime(event.created_at)}
            >
              {formatDateTime(event.created_at, "yyyy-MM-dd HH:mm")}
            </span>
            <span className="text-base-content/50">
              · {formatRelativeTime(event.created_at)}
            </span>
            <span className="text-base-content/60">· {event.actor}</span>
          </div>
          <div className="text-base-content/90 break-words">
            {event.comment}
          </div>
        </div>
      </button>
      {expanded && (
        <div className="mt-1.5 ml-6 border-l-2 border-base-300 pl-2">
          {hasSnapshot ? (
            <div className="prose prose-xs max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {event.wiring_info_snapshot}
              </ReactMarkdown>
            </div>
          ) : (
            <div className="text-base-content/50 italic">
              (Wiring was empty at this checkpoint.)
            </div>
          )}
          <div className="text-[10px] text-base-content/40 mt-1">
            {event.block_count} block{event.block_count === 1 ? "" : "s"}
            {event.image_count > 0
              ? ` · ${event.image_count} image${event.image_count === 1 ? "" : "s"} (not shown in snapshot)`
              : ""}
          </div>
        </div>
      )}
    </li>
  );
}
