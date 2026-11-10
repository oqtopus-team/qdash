"use client";

import { useId, useState } from "react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import type { FlowTargetOverride, GetFlowResponseTargetModesItem } from "@/schemas";

type TargetMode = "mux" | "qubit" | "pairs";

const MODE_FROM_API: Record<GetFlowResponseTargetModesItem, TargetMode> = {
  mux_ids: "mux",
  qids: "qubit",
  coupling_pairs: "pairs",
};

const DEFAULT_MODES: GetFlowResponseTargetModesItem[] = ["mux_ids", "qids"];

const MODE_LABEL: Record<TargetMode, string> = {
  mux: "MUX IDs",
  qubit: "Qubit IDs",
  pairs: "Coupling pairs",
};

interface FlowExecuteConfirmModalProps {
  flowName: string;
  username: string;
  chipId: string;
  description: string;
  tags: string;
  targetDefaults?: FlowTargetOverride | null;
  /** Override types the flow accepts; omitted means MUX and qubit IDs. */
  targetModes?: GetFlowResponseTargetModesItem[];
  disabledReason: string | null;
  onConfirm: (override?: FlowTargetOverride) => void;
  onClose: () => void;
}

const formatPairs = (pairs: string[][]) => pairs.map((pair) => pair.join("-")).join(", ");

/** Parse `control-target` pairs such as `63-85`; returns null when any entry is malformed. */
function parsePairs(value: string): string[][] | null {
  const trimmed = value.trim();
  if (!trimmed) return [];
  const pairs: string[][] = [];
  for (const token of trimmed.split(/[\s,]+/)) {
    const match = /^(\d+)-(\d+)$/.exec(token);
    if (!match) return null;
    pairs.push([match[1], match[2]]);
  }
  return pairs;
}

export function FlowExecuteConfirmModal({
  flowName,
  username,
  chipId,
  description,
  tags,
  targetDefaults,
  targetModes,
  disabledReason,
  onConfirm,
  onClose,
}: FlowExecuteConfirmModalProps) {
  const disabledReasonId = useId();
  const errorId = useId();
  const pairsHelpId = useId();
  const modes = (targetModes?.length ? targetModes : DEFAULT_MODES).map(
    (item) => MODE_FROM_API[item],
  );
  const resolvedMode: TargetMode | null = targetDefaults?.coupling_pairs
    ? "pairs"
    : targetDefaults?.qids
      ? "qubit"
      : targetDefaults?.mux_ids
        ? "mux"
        : null;
  // Code defaults the flow cannot accept as an override (for example pairs
  // without SetCRSchedule) are treated as unknown so they are never submitted.
  const defaults = resolvedMode && modes.includes(resolvedMode) ? targetDefaults : null;
  const defaultMode: TargetMode = (defaults && resolvedMode) || modes[0];
  const defaultIds = defaults?.coupling_pairs
    ? formatPairs(defaults.coupling_pairs)
    : (defaults?.mux_ids ?? defaults?.qids ?? []).join(", ");
  const defaultExcluded = (defaults?.exclude_qids ?? []).join(", ");
  const [mode, setMode] = useState<TargetMode>(defaultMode);
  const [ids, setIds] = useState(defaultIds);
  const [excluded, setExcluded] = useState(defaultExcluded);
  const [changed, setChanged] = useState(false);
  const tagList = tags
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
  const parseIds = (value: string) => (value.trim() ? value.trim().split(/[\s,]+/) : []);
  const pairs = mode === "pairs" ? parsePairs(ids) : [];
  const selected = mode === "pairs" ? [] : parseIds(ids);
  const exclusions = mode === "mux" ? parseIds(excluded) : [];
  const invalid =
    [...selected, ...exclusions].some((id) => !/^\d+$/.test(id)) ||
    (mode === "mux" && selected.some((id) => !Number.isSafeInteger(Number(id))));
  const duplicate =
    new Set<string | number>(mode === "mux" ? selected.map(Number) : selected).size !==
      selected.length || new Set(exclusions).size !== exclusions.length;
  const pairKeys = (pairs ?? []).map((pair) => pair.join("-"));
  const pairError =
    pairs === null
      ? "Use control-target pairs such as 63-85, separated by commas, spaces or new lines."
      : !pairs.length
        ? "Enter at least one coupling pair."
        : pairs.some(([control, target]) => control === target)
          ? "Each pair needs two different qubits."
          : new Set(pairKeys).size !== pairKeys.length
            ? "Remove duplicate coupling pairs."
            : null;
  const error = !changed
    ? null
    : mode === "pairs"
      ? pairError
      : !selected.length
        ? "Enter at least one target ID."
        : invalid
          ? "Use non-negative integer IDs separated by commas or spaces."
          : duplicate
            ? "Remove duplicate target IDs."
            : null;

  function resetTargets() {
    setMode(defaultMode);
    setIds(defaultIds);
    setExcluded(defaultExcluded);
    setChanged(false);
  }

  function buildOverride(): FlowTargetOverride {
    if (mode === "pairs") return { coupling_pairs: pairs ?? [] };
    if (mode === "qubit") return { qids: selected };
    return { mux_ids: selected.map(Number), exclude_qids: exclusions };
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
                ? mode === "pairs"
                  ? "These pairs replace the coupling targets and CR schedule of each CalibService in this flow run. Parallel groups are generated from hardware constraints."
                  : "These targets replace the initial targets of each CalibService in this flow run. Later filtering steps still apply."
                : defaults
                  ? "Defaults from the saved workflow. Edit to override for this execution only."
                  : "Targets are dynamic, unset, or differ within the saved workflow. Leave unchanged to use the code, or enter targets to override this execution."}
            </p>
            {modes.length > 1 && (
              <label className="block space-y-1">
                <span className="text-sm">Target type</span>
                <select
                  className="select w-full"
                  value={mode}
                  onChange={(event) => {
                    setMode(event.target.value as TargetMode);
                    setIds("");
                    setChanged(true);
                  }}
                >
                  {modes.map((option) => (
                    <option key={option} value={option}>
                      {MODE_LABEL[option]}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {mode === "pairs" ? (
              <div className="space-y-1">
                <label className="block space-y-1">
                  <span className="text-sm">{MODE_LABEL.pairs}</span>
                  <textarea
                    className="textarea w-full font-mono"
                    rows={3}
                    value={ids}
                    placeholder="63-85, 64-42, 39-61"
                    aria-invalid={Boolean(error)}
                    aria-describedby={error ? `${pairsHelpId} ${errorId}` : pairsHelpId}
                    onChange={(event) => {
                      setIds(event.target.value);
                      setChanged(true);
                    }}
                  />
                </label>
                <p id={pairsHelpId} className="label whitespace-normal">
                  Write each pair as control-target; 85-63 runs the opposite direction of 63-85.
                </p>
              </div>
            ) : (
              <label className="block space-y-1">
                <span className="text-sm">{MODE_LABEL[mode]}</span>
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
            )}
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
            data-coachmark="flow-execute-confirm"
            disabled={Boolean(disabledReason || error)}
            aria-describedby={disabledReason ? disabledReasonId : error ? errorId : undefined}
            onClick={() => {
              if (disabledReason || error) return;
              onConfirm(changed ? buildOverride() : undefined);
            }}
          >
            Execute
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
