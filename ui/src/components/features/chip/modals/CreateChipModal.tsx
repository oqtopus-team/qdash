"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useQueryClient } from "@tanstack/react-query";

import { useCreateChip, getListChipsQueryKey, useListChipConfigSources } from "@/client/chip/chip";
import { useListTopologies } from "@/client/topology/topology";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/Dialog";
import { SelectedLabel } from "@/components/ui/SelectedLabel";
import { useToast } from "@/components/ui/Toast/useToast";
import { newFlowTemplateHref } from "@/lib/flowTemplates";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import type { ChipCreateSubmission } from "@/components/features/first-calibration/useChipPageJourney";
import type { ChipConfigOptionsPreset, ChipConfigResult, ConfigPresetResponse } from "@/schemas";

import {
  canCreatePresetChip,
  presetBackendLabel,
  presetTemplateName,
  resolveChipSetupMode,
} from "../chipSetupMode";

interface TopologyItem {
  id: string;
  name: string;
  num_qubits: number;
}

interface CreateChipModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (
    chipId: string,
    config: ChipConfigResult | null,
    submission?: ChipCreateSubmission,
  ) => void;
  /**
   * Snapshot taken when Create Chip is submitted and handed back with that submission's answer,
   * so the answer is judged by the guide, user and project it was submitted in.
   */
  captureSubmission?: () => ChipCreateSubmission;
  /**
   * The first calibration guide takes the user on from the new chip, so the success message
   * leaves out its Open template shortcut, which would bypass the guide.
   */
  guidedByJourney?: boolean;
}

const EMPTY_WIRING = "";

// The topology is required only for a hardware chip; submit() checks it there.
const createChipSchema = z.object({
  chipId: z.string().trim().min(1, "Chip ID is required"),
  topologyId: z.string(),
  createConfig: z.boolean(),
  wiringSource: z.string(),
  backend: z.enum(["quel1", "quel3"]),
});

type CreateChipFormData = z.infer<typeof createChipSchema>;

export function CreateChipModal({
  isOpen,
  onClose,
  onSuccess,
  guidedByJourney = false,
  captureSubmission,
}: CreateChipModalProps) {
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    setValue,
    watch,
    formState: { errors },
  } = useForm<CreateChipFormData>({
    resolver: zodResolver(createChipSchema),
    defaultValues: {
      chipId: "",
      topologyId: "",
      createConfig: true,
      wiringSource: EMPTY_WIRING,
      backend: "quel1",
    },
  });
  const selectedTopologyId = watch("topologyId");
  const chipIdValue = watch("chipId");
  const createConfig = watch("createConfig");
  const wiringSource = watch("wiringSource");
  const toast = useToast();
  const router = useRouter();

  // Systems in the Qubex configuration tree whose wiring a new chip can copy
  const { data: configSourcesData, isError: isConfigSourcesError } = useListChipConfigSources({
    query: { enabled: isOpen },
  });
  const configAvailable = configSourcesData?.data?.available ?? false;
  const configSources = configSourcesData?.data?.sources ?? [];
  // A preset deployment (fake or qibocal) creates only its fixed device; until the deployment is
  // known, no setup controls are shown so a preset deployment never offers hardware settings.
  const setupMode = resolveChipSetupMode(configSourcesData?.data, {
    isError: isConfigSourcesError,
  });
  const devicePreset = setupMode.kind === "preset" ? setupMode.preset : null;
  const presetBackend = setupMode.kind === "preset" ? setupMode.backend : null;

  // Fetch available topologies
  const { data: topologiesData, isLoading: isLoadingTopologies } = useListTopologies(undefined, {
    query: {
      staleTime: Infinity,
    },
  });

  // Parse topologies from API response (Axios wraps in .data)
  const topologies = useMemo(() => {
    const axiosResponse = topologiesData as { data?: { topologies?: TopologyItem[] } } | undefined;
    return axiosResponse?.data?.topologies ?? [];
  }, [topologiesData]);

  // Group topologies by size for better UX
  const groupedTopologies = useMemo(() => {
    const grouped = new Map<number, TopologyItem[]>();
    topologies.forEach((t) => {
      const existing = grouped.get(t.num_qubits) ?? [];
      existing.push(t);
      grouped.set(t.num_qubits, existing);
    });
    // Sort by size
    return Array.from(grouped.entries()).sort(([a], [b]) => a - b);
  }, [topologies]);

  // Get selected topology details
  const selectedTopology = useMemo(
    () => topologies.find((t) => t.id === selectedTopologyId),
    [topologies, selectedTopologyId],
  );

  // Set default topology when data loads
  useEffect(() => {
    if (!selectedTopologyId && topologies.length > 0) {
      // Default to first 64-qubit topology or first available
      const default64 = topologies.find((t) => t.num_qubits === 64);
      setValue("topologyId", default64?.id ?? topologies[0].id, {
        shouldValidate: true,
      });
    }
  }, [setValue, topologies, selectedTopologyId]);

  const queryClient = useQueryClient();

  // The snapshot of the submission whose answer is pending; the submit button stays disabled
  // until it answers, so one submission is in flight at a time.
  const pendingSubmission = useRef<ChipCreateSubmission | undefined>(undefined);

  const createChipMutation = useCreateChip({
    mutation: {
      onSuccess: (data) => {
        // Invalidate chips list to refresh
        queryClient.invalidateQueries({ queryKey: getListChipsQueryKey() });

        const config = data.data?.config;
        if (config?.message) {
          // A preset without configuration files reports "skipped" but is ready to run.
          const presetReady =
            config.status === "created" || (config.status === "skipped" && config.preset != null);
          if (presetReady) {
            const templateId =
              !guidedByJourney &&
              presetBackend !== null &&
              config.preset === devicePreset?.preset_id &&
              devicePreset?.workflow_template_id;
            toast.success(
              config.message,
              templateId
                ? {
                    action: {
                      label: "Open template",
                      onClick: () =>
                        router.push(
                          newFlowTemplateHref(presetBackend ?? "", templateId, data.data.chip_id),
                        ),
                    },
                  }
                : undefined,
            );
          } else {
            toast.info(config.message);
          }
        }

        // The success callback goes first, so a page that leaves for another route has done so
        // before the dialog reports its close.
        const submission = pendingSubmission.current;
        pendingSubmission.current = undefined;
        if (onSuccess && data.data) {
          onSuccess(data.data.chip_id, config ?? null, submission);
        }

        // Reset form and close modal
        reset();
        setServerError(null);
        onClose();
      },
      onError: (err: Error) => {
        pendingSubmission.current = undefined;
        setServerError(getApiErrorMessage(err, "Failed to create chip"));
      },
    },
  });

  const create = (request: Parameters<typeof createChipMutation.mutate>[0]) => {
    pendingSubmission.current = captureSubmission?.();
    createChipMutation.mutate(request);
  };

  const submit = (data: CreateChipFormData) => {
    if (setupMode.kind === "pending") return;
    setServerError(null);
    if (setupMode.kind === "preset") {
      // Never fall back to a hardware chip on a preset deployment.
      if (!canCreatePresetChip(setupMode)) return;
      create({
        data: {
          chip_id: data.chipId,
          size: setupMode.preset.n_qubits,
          topology_id: setupMode.preset.topology_id,
          config: { preset: setupMode.preset.preset_id as ChipConfigOptionsPreset },
        },
      });
      return;
    }
    if (!selectedTopology) {
      setError("topologyId", { message: "Please select a topology template" });
      return;
    }

    const withConfig = configAvailable && data.createConfig;
    create({
      data: {
        chip_id: data.chipId,
        size: selectedTopology.num_qubits,
        topology_id: data.topologyId,
        config: withConfig
          ? data.wiringSource
            ? { source_system_id: data.wiringSource }
            : { backend: data.backend }
          : { create: false },
      },
    });
  };

  const handleClose = () => {
    if (!createChipMutation.isPending) {
      reset();
      setServerError(null);
      onClose();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent>
        <DialogTitle className="mb-4">Create New Chip</DialogTitle>

        <form onSubmit={handleSubmit(submit)} className="space-y-4" noValidate>
          {/* Chip ID Input */}
          <div className="form-control">
            <label className="label" htmlFor="chip-id-input">
              <span className="label-text">Chip ID</span>
            </label>
            <input
              id="chip-id-input"
              type="text"
              placeholder="e.g., 64Q, Chip001"
              className={`input input-bordered w-full ${errors.chipId ? "input-error" : ""}`}
              disabled={createChipMutation.isPending}
              aria-invalid={Boolean(errors.chipId)}
              aria-describedby={errors.chipId ? "chip-id-error" : undefined}
              {...register("chipId")}
            />
            {errors.chipId && (
              <p id="chip-id-error" className="mt-1 text-sm text-error">
                {errors.chipId.message}
              </p>
            )}
          </div>

          {setupMode.kind === "pending" ? (
            setupMode.failed ? (
              <div className="alert alert-error alert-soft" role="alert">
                <span className="min-w-0 break-words">
                  Unable to check how this deployment creates chips. Close and reopen this dialog to
                  retry.
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <span className="loading loading-spinner loading-sm shrink-0"></span>
                <span className="text-sm text-base-content/60">Checking the deployment...</span>
              </div>
            )
          ) : setupMode.kind === "preset" ? (
            <PresetDeviceSetup
              backend={setupMode.backend}
              preset={setupMode.preset}
              configAvailable={setupMode.configAvailable}
              chipId={chipIdValue.trim()}
              topologyName={
                topologies.find((topology) => topology.id === setupMode.preset?.topology_id)?.name
              }
            />
          ) : (
            <>
              {/* Topology Template Selection */}
              <div className="form-control">
                <label className="label" htmlFor="topology-select">
                  <span className="label-text">Topology Template</span>
                </label>
                {isLoadingTopologies ? (
                  <div className="flex items-center gap-2 h-12">
                    <span className="loading loading-spinner loading-sm"></span>
                    <span className="text-sm text-base-content/60">Loading templates...</span>
                  </div>
                ) : (
                  <select
                    id="topology-select"
                    className={`select select-bordered w-full ${errors.topologyId ? "select-error" : ""}`}
                    disabled={createChipMutation.isPending}
                    aria-invalid={Boolean(errors.topologyId)}
                    aria-describedby={errors.topologyId ? "topology-error" : undefined}
                    {...register("topologyId")}
                  >
                    <SelectedLabel />
                    {groupedTopologies.map(([size, topos]) => (
                      <optgroup key={size} label={`${size} Qubits`}>
                        {topos.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.name}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                )}
                {errors.topologyId && (
                  <p id="topology-error" className="mt-1 text-sm text-error">
                    {errors.topologyId.message}
                  </p>
                )}
                {selectedTopology && (
                  <p className="mt-1 text-xs text-base-content/60">
                    {selectedTopology.num_qubits} qubits
                  </p>
                )}
              </div>

              {/* Qubex configuration directory (system_id == chip_id) */}
              <fieldset
                className="min-w-0 space-y-2 rounded-lg border border-base-300 p-3"
                data-coachmark="chip-config"
              >
                <legend className="px-1 text-sm font-medium">Qubex configuration</legend>
                {!configAvailable ? (
                  <p className="text-sm text-base-content/60">
                    No Qubex configuration tree is mounted, so only the chip record is created.
                  </p>
                ) : (
                  <>
                    <label className="flex cursor-pointer items-start gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="checkbox checkbox-sm mt-0.5 shrink-0"
                        disabled={createChipMutation.isPending}
                        {...register("createConfig")}
                      />
                      <span className="min-w-0 flex-1">
                        Create{" "}
                        <code className="break-all">{chipIdValue.trim() || "<chip_id>"}/</code> with
                        system ID = chip ID
                      </span>
                    </label>
                    {createConfig && (
                      <>
                        <div className="form-control">
                          <label className="label" htmlFor="wiring-source-select">
                            <span className="label-text">Wiring</span>
                          </label>
                          <select
                            id="wiring-source-select"
                            className="select select-bordered select-sm w-full"
                            disabled={createChipMutation.isPending}
                            {...register("wiringSource")}
                          >
                            <option value={EMPTY_WIRING}>Start from template</option>
                            {configSources.map((source) => (
                              <option key={source.system_id} value={source.system_id}>
                                Copy from {source.system_id} ({source.backend}, {source.mux_count}{" "}
                                MUX)
                              </option>
                            ))}
                          </select>
                        </div>
                        {wiringSource === EMPTY_WIRING && (
                          <div className="form-control">
                            <label className="label" htmlFor="backend-select">
                              <span className="label-text">Backend</span>
                            </label>
                            <select
                              id="backend-select"
                              className="select select-bordered select-sm w-full"
                              disabled={createChipMutation.isPending}
                              {...register("backend")}
                            >
                              <option value="quel1">quel1</option>
                              <option value="quel3">quel3</option>
                            </select>
                          </div>
                        )}
                        <p className="text-xs break-words text-base-content/60">
                          {wiringSource === EMPTY_WIRING
                            ? "Config templates include commented examples. Edit hardware settings on the Config page before running."
                            : `Wiring, boxes and other hardware files are copied from ${wiringSource}.`}{" "}
                          Parameter files start from templates. An existing directory is kept as is.
                          Push the new files from the Config page.
                        </p>
                      </>
                    )}
                  </>
                )}
              </fieldset>
            </>
          )}

          {/* Error Message */}
          {serverError && (
            <div id="chip-error" className="alert alert-error" role="alert">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="stroke-current shrink-0 h-6 w-6"
                fill="none"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span>{serverError}</span>
            </div>
          )}

          {/* Action Buttons */}
          <div className="modal-action">
            <button
              type="button"
              className="btn"
              onClick={handleClose}
              disabled={createChipMutation.isPending}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              data-coachmark="create-chip-submit"
              disabled={
                createChipMutation.isPending ||
                setupMode.kind === "pending" ||
                (setupMode.kind === "preset" && !canCreatePresetChip(setupMode))
              }
            >
              {createChipMutation.isPending ? (
                <>
                  <span className="loading loading-spinner loading-sm" aria-hidden="true"></span>
                  Creating...
                </>
              ) : (
                "Create Chip"
              )}
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

interface PresetDeviceSetupProps {
  backend: string;
  preset: ConfigPresetResponse | null;
  configAvailable: boolean;
  chipId: string;
  topologyName?: string;
}

/** The fixed device every chip of a preset deployment is; nothing to choose. */
function PresetDeviceSetup({
  backend,
  preset,
  configAvailable,
  chipId,
  topologyName,
}: PresetDeviceSetupProps) {
  const backendLabel = presetBackendLabel(backend);
  if (!preset) {
    return (
      <div className="alert alert-error alert-soft" role="alert">
        <span className="min-w-0 break-words">
          This deployment runs the {backendLabel}, but the API does not offer its device
          configuration, so no chip can be created here.
        </span>
      </div>
    );
  }
  const writesConfig = preset.requires_config_tree !== false;
  return (
    <fieldset
      className="min-w-0 space-y-2 rounded-lg border border-base-300 p-3"
      aria-describedby="preset-device-summary"
    >
      <legend className="px-1 text-sm font-medium">{preset.name}</legend>
      <p id="preset-device-summary" className="text-xs break-words text-base-content/60">
        Fixed by this deployment. No hardware is contacted.
      </p>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
        <dt className="text-base-content/60">Backend</dt>
        <dd className="min-w-0">{backendLabel.charAt(0).toUpperCase() + backendLabel.slice(1)}</dd>
        <dt className="text-base-content/60">Topology</dt>
        <dd className="min-w-0 break-words" data-testid="preset-device-topology">
          {topologyName ? `${topologyName} ` : ""}
          <code className="break-all text-xs">{preset.topology_id}</code>
        </dd>
        <dt className="text-base-content/60">Size</dt>
        <dd className="min-w-0">
          {preset.n_qubits === 1 ? "1 qubit" : `${preset.n_qubits} qubits`}
          {preset.mux_count > 0 ? `, ${preset.mux_count} MUX` : ""}
        </dd>
        <dt className="text-base-content/60">Configuration</dt>
        <dd className="min-w-0 break-words">
          {writesConfig ? (
            <>
              <code className="break-all">{chipId || "<chip_id>"}/</code> generated from the chip ID
            </>
          ) : (
            "None; the backend uses its own platform files"
          )}
        </dd>
      </dl>
      {!writesConfig ? (
        <p className="text-xs break-words text-base-content/60">
          {preset.description} Run it with the {presetTemplateName({ backend })} template.
        </p>
      ) : configAvailable ? (
        <p className="text-xs break-words text-base-content/60">
          Writes the device&apos;s configuration files and keeps an existing directory as is.
          Calibrate it with the {presetTemplateName({ backend })} template.
        </p>
      ) : (
        <div className="alert alert-warning alert-soft" role="alert">
          <span className="min-w-0 break-words">
            No Qubex configuration tree is mounted, so the device configuration cannot be generated
            and no chip can be created. Mount the configuration tree for this deployment, then
            reopen this dialog.
          </span>
        </div>
      )}
    </fieldset>
  );
}
