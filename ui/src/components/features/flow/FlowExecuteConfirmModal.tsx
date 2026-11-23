"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useId, useRef, useState, type KeyboardEvent } from "react";
import { useForm, useWatch } from "react-hook-form";

import type { FlowExecutionPlanState } from "@/hooks/useFlowExecutionPlan";
import type { FlowTargetOverride, GetFlowResponseTargetModesItem } from "@/schemas";

import { FlowExecutionPreview } from "@/components/features/flow/FlowExecutionPreview";
import { flowTagsSchema } from "@/components/features/flow/flowMetadataSchema";
import {
  flowTargetsSchema,
  type FlowTargetsFormData,
  type FlowTargetsFormInput,
  type TargetMode,
} from "@/components/features/flow/flowTargetsSchema";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";

type ConfirmTab = "settings" | "preview";

const TABS: ReadonlyArray<{ id: ConfirmTab; label: string }> = [
  { id: "settings", label: "Settings" },
  { id: "preview", label: "Execution preview" },
];

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
  /**
   * Override types the flow accepts; omitted means MUX and qubit IDs, and an empty list means
   * the flow accepts no override (for example because it runs manual rounds).
   */
  targetModes?: GetFlowResponseTargetModesItem[];
  /** The execution preview of the saved source; omitted means unavailable. */
  plan?: FlowExecutionPlanState;
  /** Whether the editor holds changes that the saved source, and so this run, lacks. */
  hasUnsavedChanges?: boolean;
  disabledReason: string | null;
  onConfirm: (override?: FlowTargetOverride) => void;
  onClose: () => void;
}

const formatPairs = (pairs: string[][]) => pairs.map((pair) => pair.join("-")).join(", ");

/** Confirms a flow run, showing its settings, optional target override, and execution preview. */
export function FlowExecuteConfirmModal({
  flowName,
  username,
  chipId,
  description,
  tags,
  targetDefaults,
  targetModes,
  plan,
  hasUnsavedChanges = false,
  disabledReason,
  onConfirm,
  onClose,
}: FlowExecuteConfirmModalProps) {
  const disabledReasonId = useId();
  const errorId = useId();
  const pairsHelpId = useId();
  const planBlockId = useId();
  const tabsId = useId();
  const [tab, setTab] = useState<ConfirmTab>("settings");
  const tabRefs = useRef<Partial<Record<ConfirmTab, HTMLButtonElement | null>>>({});
  const overridesAccepted = targetModes === undefined || targetModes.length > 0;
  const modes = (targetModes?.length ? targetModes : DEFAULT_MODES).map(
    (item) => MODE_FROM_API[item],
  );
  const readyPlan = plan?.status === "ready" ? plan.plan : null;
  const planBlock =
    readyPlan?.status === "invalid"
      ? "Manual rounds in this workflow cannot run. See Execution preview for the problems."
      : null;
  const overrideReason =
    readyPlan?.target_override_reason ??
    "This workflow accepts no target override. Its targets come from the source.";
  const resolvedMode: TargetMode | null = targetDefaults?.coupling_pairs
    ? "pairs"
    : targetDefaults?.qids
      ? "qubit"
      : targetDefaults?.mux_ids
        ? "mux"
        : null;
  // Code defaults the flow cannot accept as an override (for example pairs of
  // a pipeline with custom steps) are treated as unknown so they are never submitted.
  const defaults = resolvedMode && modes.includes(resolvedMode) ? targetDefaults : null;
  const defaultMode: TargetMode = (defaults && resolvedMode) || modes[0];
  const defaultIds = defaults?.coupling_pairs
    ? formatPairs(defaults.coupling_pairs)
    : (defaults?.mux_ids ?? defaults?.qids ?? []).join(", ");
  const defaultExcluded = (defaults?.exclude_qids ?? []).join(", ");
  const defaultValues: FlowTargetsFormInput = {
    mode: defaultMode,
    ids: defaultIds,
    excluded: defaultExcluded,
  };
  const { control, register, reset, setValue, handleSubmit } = useForm<
    FlowTargetsFormInput,
    unknown,
    FlowTargetsFormData
  >({ resolver: zodResolver(flowTargetsSchema), defaultValues });
  const [mode, ids, excluded] = useWatch({ control, name: ["mode", "ids", "excluded"] });
  const [changed, setChanged] = useState(false);
  const tagList = flowTagsSchema.parse(tags);
  const parsed = flowTargetsSchema.safeParse({ mode, ids, excluded });
  const error = changed && !parsed.success ? (parsed.error.issues[0]?.message ?? null) : null;
  /** Records that the user edited the targets, which shows errors and submits the override. */
  const markChanged = () => setChanged(true);

  /** Restores the code defaults so the run leaves its targets to the code. */
  function resetTargets() {
    reset(defaultValues);
    setChanged(false);
  }

  const selectTab = (next: ConfirmTab) => {
    setTab(next);
    tabRefs.current[next]?.focus();
  };

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const index = TABS.findIndex((item) => item.id === tab);
    const last = TABS.length - 1;
    const target: Record<string, number> = {
      ArrowRight: index === last ? 0 : index + 1,
      ArrowLeft: index === 0 ? last : index - 1,
      Home: 0,
      End: last,
    };
    if (!(event.key in target)) return;
    event.preventDefault();
    selectTab(TABS[target[event.key]].id);
  };

  const blockedReason = disabledReason ?? planBlock;
  const blockedId = disabledReason ? disabledReasonId : planBlock ? planBlockId : undefined;

  /** Runs the flow, submitting the validated target override only after the targets change. */
  function handleExecute() {
    if (blockedReason || error) return;
    if (!changed || !overridesAccepted) {
      onConfirm(undefined);
      return;
    }
    void handleSubmit((override) => onConfirm(override))();
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="flex max-h-[90vh] max-w-3xl flex-col gap-0 p-4 sm:p-6">
        <DialogTitle>Execute Flow</DialogTitle>
        <DialogDescription className="mt-1 text-sm text-base-content/70">
          Review the settings and the execution plan for this run
        </DialogDescription>
        <div role="tablist" aria-label="Execution details" className="tabs tabs-border mt-3">
          {TABS.map((item) => (
            <button
              key={item.id}
              ref={(element) => {
                tabRefs.current[item.id] = element;
              }}
              type="button"
              role="tab"
              id={`${tabsId}-tab-${item.id}`}
              aria-selected={tab === item.id}
              aria-controls={`${tabsId}-panel-${item.id}`}
              tabIndex={tab === item.id ? 0 : -1}
              className={`tab ${tab === item.id ? "tab-active" : ""}`}
              onClick={() => setTab(item.id)}
              onKeyDown={handleTabKeyDown}
            >
              {item.label}
              {item.id === "preview" && planBlock && (
                <span className="badge badge-error badge-xs ml-2" aria-label="has problems" />
              )}
            </button>
          ))}
        </div>
        {/* Both panels stay mounted so edits survive switching tabs. */}
        <div
          role="tabpanel"
          id={`${tabsId}-panel-settings`}
          aria-labelledby={`${tabsId}-tab-settings`}
          hidden={tab !== "settings"}
          className="min-h-0 flex-1 space-y-4 overflow-y-auto py-4"
        >
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
          {hasUnsavedChanges && (
            <p className="text-sm text-warning">
              The editor has unsaved changes; this run uses the saved version.
            </p>
          )}
          {description && <p>{description}</p>}
          {tagList.length > 0 && (
            <p className="text-xs text-base-content/60">Tags: {tagList.join(", ")}</p>
          )}
          <fieldset className="fieldset gap-3 border-t border-base-300 pt-4">
            <legend className="fieldset-legend">Calibration targets</legend>
            {!overridesAccepted ? (
              <p className="label whitespace-normal">{overrideReason}</p>
            ) : (
              <>
                <p className="label whitespace-normal">
                  {changed
                    ? mode === "pairs"
                      ? "These directed pairs replace the coupling targets of each CalibService in this flow run. The scheduler groups exactly these pairs from hardware constraints; later filtering steps still apply."
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
                      {...register("mode", {
                        onChange: () => {
                          setValue("ids", "");
                          markChanged();
                        },
                      })}
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
                        placeholder="63-85, 64-42, 39-61"
                        aria-invalid={Boolean(error)}
                        aria-describedby={error ? `${pairsHelpId} ${errorId}` : pairsHelpId}
                        {...register("ids", { onChange: markChanged })}
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
                      placeholder="0, 1, 2"
                      aria-invalid={Boolean(error)}
                      aria-describedby={error ? errorId : undefined}
                      {...register("ids", { onChange: markChanged })}
                    />
                  </label>
                )}
                {mode === "mux" && (
                  <label className="block space-y-1">
                    <span className="text-sm">Excluded qubit IDs</span>
                    <input
                      className="input w-full font-mono"
                      placeholder="Optional"
                      aria-invalid={Boolean(error)}
                      aria-describedby={error ? errorId : undefined}
                      {...register("excluded", { onChange: markChanged })}
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
              </>
            )}
          </fieldset>
        </div>
        <div
          role="tabpanel"
          id={`${tabsId}-panel-preview`}
          aria-labelledby={`${tabsId}-tab-preview`}
          hidden={tab !== "preview"}
          className="min-h-0 flex-1 overflow-y-auto py-4"
        >
          <FlowExecutionPreview state={plan} hasUnsavedChanges={hasUnsavedChanges} />
        </div>
        {disabledReason && (
          <div id={disabledReasonId} className="alert alert-info mb-4" role="status">
            {disabledReason}
          </div>
        )}
        {!disabledReason && planBlock && (
          <div id={planBlockId} className="alert alert-error mb-4" role="status">
            <span>{planBlock}</span>
            {tab !== "preview" && (
              <button type="button" className="btn btn-sm" onClick={() => selectTab("preview")}>
                Show problems
              </button>
            )}
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
            disabled={Boolean(blockedReason || error)}
            aria-describedby={blockedReason ? blockedId : error ? errorId : undefined}
            onClick={handleExecute}
          >
            Execute
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
