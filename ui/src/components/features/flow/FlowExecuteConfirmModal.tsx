"use client";

import { useId, useState } from "react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import type { FlowTargetOverride } from "@/schemas";

interface FlowExecuteConfirmModalProps {
  flowName: string;
  username: string;
  chipId: string;
  description: string;
  tags: string;
  targetDefaults?: FlowTargetOverride | null;
  disabledReason: string | null;
  onConfirm: (override?: FlowTargetOverride) => void;
  onClose: () => void;
}

export function FlowExecuteConfirmModal({
  flowName,
  username,
  chipId,
  description,
  tags,
  targetDefaults,
  disabledReason,
  onConfirm,
  onClose,
}: FlowExecuteConfirmModalProps) {
  const disabledReasonId = useId();
  const errorId = useId();
  const [mode, setMode] = useState<"mux" | "qubit">(targetDefaults?.qids ? "qubit" : "mux");
  const [ids, setIds] = useState(
    (targetDefaults?.mux_ids ?? targetDefaults?.qids ?? []).join(", "),
  );
  const [excluded, setExcluded] = useState((targetDefaults?.exclude_qids ?? []).join(", "));
  const [changed, setChanged] = useState(false);
  const tagList = tags
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
  const parseIds = (value: string) => (value.trim() ? value.trim().split(/[\s,]+/) : []);
  const selected = parseIds(ids);
  const exclusions = mode === "mux" ? parseIds(excluded) : [];
  const invalid =
    [...selected, ...exclusions].some((id) => !/^\d+$/.test(id)) ||
    (mode === "mux" && selected.some((id) => !Number.isSafeInteger(Number(id))));
  const duplicate =
    new Set<string | number>(mode === "mux" ? selected.map(Number) : selected).size !==
      selected.length || new Set(exclusions).size !== exclusions.length;
  const error = !changed
    ? null
    : !selected.length
      ? "Enter at least one target ID."
      : invalid
        ? "Use non-negative integer IDs separated by commas or spaces."
        : duplicate
          ? "Remove duplicate target IDs."
          : null;

  function resetTargets() {
    setMode(targetDefaults?.qids ? "qubit" : "mux");
    setIds((targetDefaults?.mux_ids ?? targetDefaults?.qids ?? []).join(", "));
    setExcluded((targetDefaults?.exclude_qids ?? []).join(", "));
    setChanged(false);
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="max-w-2xl rounded-xl">
        <DialogTitle>Execute Flow</DialogTitle>
        <DialogDescription className="mt-1 text-sm text-base-content/70">
          Review the settings for this execution
        </DialogDescription>
        <div className="space-y-4 py-6">
          <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-xs text-base-content/60">Flow name</dt>
              <dd className="font-mono">{flowName}.py</dd>
            </div>
            <div>
              <dt className="text-xs text-base-content/60">Username</dt>
              <dd>{username}</dd>
            </div>
            <div>
              <dt className="text-xs text-base-content/60">Chip ID</dt>
              <dd>{chipId}</dd>
            </div>
          </dl>
          <p className="text-sm text-base-content/70">
            This workflow reserves the entire chip for all its steps. Other runs on this chip must
            wait until the workflow finishes.
          </p>
          {description && <p>{description}</p>}
          {tagList.length > 0 && (
            <p className="text-xs text-base-content/60">Tags: {tagList.join(", ")}</p>
          )}
          <fieldset className="fieldset gap-3 border-t border-base-300 pt-4">
            <legend className="fieldset-legend">Calibration targets</legend>
            <p className="label whitespace-normal">
              {changed
                ? "These targets replace the initial targets of each CalibService in this flow run. Later filtering steps still apply."
                : targetDefaults
                  ? "Defaults from the saved workflow. Edit to override for this execution only."
                  : "Targets are dynamic, unset, or differ within the saved workflow. Leave unchanged to use the code, or enter targets to override this execution."}
            </p>
            <label className="block space-y-1">
              <span className="text-sm">Target type</span>
              <select
                className="select w-full"
                value={mode}
                onChange={(event) => {
                  setMode(event.target.value as "mux" | "qubit");
                  setIds("");
                  setChanged(true);
                }}
              >
                <option value="mux">MUX IDs</option>
                <option value="qubit">Qubit IDs</option>
              </select>
            </label>
            <label className="block space-y-1">
              <span className="text-sm">{mode === "mux" ? "MUX IDs" : "Qubit IDs"}</span>
              <input
                className="input w-full font-mono"
                value={ids}
                placeholder="0, 1, 2"
                aria-invalid={Boolean(error)}
                aria-describedby={error ? errorId : undefined}
                onChange={(event) => {
                  setIds(event.target.value);
                  setChanged(true);
                }}
              />
            </label>
            {mode === "mux" && (
              <label className="block space-y-1">
                <span className="text-sm">Excluded qubit IDs</span>
                <input
                  className="input w-full font-mono"
                  value={excluded}
                  placeholder="Optional"
                  aria-invalid={Boolean(error)}
                  aria-describedby={error ? errorId : undefined}
                  onChange={(event) => {
                    setExcluded(event.target.value);
                    setChanged(true);
                  }}
                />
              </label>
            )}
            {error && (
              <p id={errorId} className="text-sm text-error" role="alert">
                {error}
              </p>
            )}
            {changed && (
              <button
                type="button"
                className="btn btn-ghost btn-sm self-start"
                onClick={resetTargets}
              >
                Use code defaults
              </button>
            )}
          </fieldset>
        </div>
        {disabledReason && (
          <div id={disabledReasonId} className="alert alert-info mb-4" role="status">
            {disabledReason}
          </div>
        )}
        <div className="flex justify-end gap-2 border-t border-base-300 pt-4">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={Boolean(disabledReason || error)}
            aria-describedby={disabledReason ? disabledReasonId : error ? errorId : undefined}
            onClick={() => {
              if (disabledReason || error) return;
              onConfirm(
                changed
                  ? mode === "mux"
                    ? {
                        mux_ids: selected.map(Number),
                        exclude_qids: exclusions,
                      }
                    : { qids: selected }
                  : undefined,
              );
            }}
          >
            Execute
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
