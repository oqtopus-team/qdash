"use client";

import { FileArchive, Upload, X } from "lucide-react";
import { useRef, useState } from "react";

import { useCreateKnowledgeDraft } from "@/client/evaluation/evaluation";
import type { KnowledgeDraftResponse } from "@/schemas";
import { getApiErrorMessage } from "@/lib/utils/apiError";

interface KnowledgeDraftPickerProps {
  /** The task the evaluation is for; a draft of another task is refused. */
  taskName: string;
  draft: KnowledgeDraftResponse | null;
  onChange: (draft: KnowledgeDraftResponse | null) => void;
  disabled: boolean;
}

/**
 * Drop a zipped task directory (`index.md` and `examples/`) to use it instead
 * of the shared knowledge, for an evaluation run or a prompt preview. The API
 * stores it as a draft of the project; nothing in Knowledge changes, and only
 * what names the draft reads it.
 */
export function KnowledgeDraftPicker({
  taskName,
  draft,
  onChange,
  disabled,
}: KnowledgeDraftPickerProps) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const upload = useCreateKnowledgeDraft();
  const busy = disabled || upload.isPending;

  const choose = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    try {
      const response = await upload.mutateAsync({ data: { file } });
      const uploaded = response.data;
      if (uploaded.task_name !== taskName) {
        setError(`${file.name} describes ${uploaded.task_name}, not ${taskName}.`);
        return;
      }
      onChange(uploaded);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "The zip could not be read as task knowledge."));
    }
  };

  if (draft) {
    const statuses = Object.keys(draft.reference.statuses ?? {});
    const parameters = Object.keys(draft.reference.parameters ?? {});
    const warnings = draft.warnings ?? [];
    return (
      <div className="space-y-1" data-testid="knowledge-draft">
        <span className="label-text font-medium">Knowledge</span>
        <div className="rounded-md border border-primary/40 px-3 py-2 text-xs">
          <div className="flex items-center gap-2">
            <FileArchive className="h-4 w-4 shrink-0 text-primary" />
            <span className="font-mono">{draft.filename || draft.draft_id.slice(0, 12)}</span>
            <span className="text-base-content/60">
              {draft.example_count} example{draft.example_count === 1 ? "" : "s"}
            </span>
            <button
              type="button"
              className="btn btn-ghost btn-xs btn-circle ml-auto"
              onClick={() => onChange(null)}
              disabled={disabled}
              aria-label="Use the shared knowledge"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
          <dl className="mt-1 space-y-0.5 text-base-content/70">
            <div>
              <dt className="inline">Statuses: </dt>
              <dd className="inline font-mono">{statuses.join(", ") || "-"}</dd>
            </div>
            <div>
              <dt className="inline">Parameters: </dt>
              <dd className="inline font-mono">{parameters.join(", ") || "-"}</dd>
            </div>
          </dl>
          {warnings.length > 0 && (
            <ul className="mt-1 list-disc pl-4 text-warning" aria-label="Generator warnings">
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <span className="label-text font-medium">
        Knowledge <span className="font-normal text-base-content/60">(optional draft)</span>
      </span>
      <button
        type="button"
        className={`flex w-full items-center gap-2 rounded-md border border-dashed px-3 py-2 text-left text-xs ${
          dragging ? "border-primary bg-primary/5" : "border-base-300"
        }`}
        onClick={() => input.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (!busy) void choose(event.dataTransfer.files[0]);
        }}
        disabled={busy}
      >
        {upload.isPending ? (
          <span className="loading loading-spinner loading-xs" />
        ) : (
          <Upload className="h-4 w-4 shrink-0" />
        )}
        <span className="text-base-content/70">
          The shared knowledge of {taskName} is used. Drop a zipped task directory (index.md,
          examples/) to use that draft instead; Knowledge does not change.
        </span>
      </button>
      <input
        ref={input}
        type="file"
        accept=".zip,application/zip"
        className="hidden"
        data-testid="knowledge-draft-input"
        onChange={(event) => {
          void choose(event.target.files?.[0]);
          event.target.value = "";
        }}
        disabled={busy}
      />
      {error && <p className="text-xs text-error">{error}</p>}
    </div>
  );
}
