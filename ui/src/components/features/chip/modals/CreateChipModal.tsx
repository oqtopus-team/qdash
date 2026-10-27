"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useQueryClient } from "@tanstack/react-query";

import {
  getListChipsQueryKey,
  useCreateChip,
  useListChipSystems,
  useListChips,
} from "@/client/chip/chip";
import { useListCooldowns } from "@/client/cooldown/cooldown";
import { useListTopologies } from "@/client/topology/topology";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/Dialog";
import { SelectedLabel } from "@/components/ui/SelectedLabel";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import type { ChipProvisioningResult, CooldownResponse } from "@/schemas";

import { ProvisioningResultPanel } from "../ProvisioningResultPanel";

interface TopologyItem {
  id: string;
  name: string;
  num_qubits: number;
}

interface CreateChipModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (chipId: string) => void;
  /** Cool-down selected on the page; preselected as the chip's cool-down. */
  defaultCooldownId?: string | null;
}

export const BACKEND_OPTIONS = ["quel1", "quel3"] as const;

const createChipSchema = z.object({
  chipId: z
    .string()
    .trim()
    .min(1, "Chip ID is required")
    .regex(/^[A-Za-z0-9][A-Za-z0-9_-]*$/, "Use letters, digits, '-' and '_' only"),
  topologyId: z.string().min(1, "Please select a topology template"),
  displayName: z.string().trim().max(200, "Display name is too long"),
  cooldownId: z.string(),
  inheritFrom: z.string(),
  backend: z.string(),
  provision: z.enum(["auto", "on", "off"]),
});

type CreateChipFormData = z.infer<typeof createChipSchema>;

/**
 * The chip that was loaded in the cool-down before `cooldown` on the same
 * cryostat: the default source of wiring for a new chip. Null when unknown.
 */
export function previousChipOnCryostat(
  cooldowns: CooldownResponse[],
  cooldownId: string,
): string | null {
  const current = cooldowns.find((c) => c.cooldown_id === cooldownId);
  if (!current) return null;
  const earlier = cooldowns
    .filter(
      (c) =>
        c.cryo_id === current.cryo_id &&
        c.cooldown_id !== current.cooldown_id &&
        c.started_at < current.started_at &&
        c.chip_ids.length > 0,
    )
    .sort((a, b) => (a.started_at < b.started_at ? 1 : -1));
  return earlier[0]?.chip_ids[earlier[0].chip_ids.length - 1] ?? null;
}

export function CreateChipModal({
  isOpen,
  onClose,
  onSuccess,
  defaultCooldownId,
}: CreateChipModalProps) {
  const [serverError, setServerError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    chipId: string;
    provisioning: ChipProvisioningResult | null;
  } | null>(null);
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
      displayName: "",
      cooldownId: defaultCooldownId ?? "",
      inheritFrom: "",
      backend: "",
      provision: "auto",
    },
  });
  const selectedTopologyId = watch("topologyId");
  const cooldownId = watch("cooldownId");
  const inheritFrom = watch("inheritFrom");
  const backend = watch("backend");

  // Fetch available topologies
  const { data: topologiesData, isLoading: isLoadingTopologies } = useListTopologies(undefined, {
    query: {
      staleTime: Infinity,
    },
  });
  const { data: chipsData } = useListChips();
  const { data: cooldownsData } = useListCooldowns(undefined, {
    query: { enabled: isOpen, staleTime: 30_000 },
  });
  const { data: inheritedSystemsData } = useListChipSystems(inheritFrom, {
    query: { enabled: isOpen && inheritFrom !== "", staleTime: 30_000 },
  });

  // Parse topologies from API response (Axios wraps in .data)
  const topologies = useMemo(() => {
    const axiosResponse = topologiesData as { data?: { topologies?: TopologyItem[] } } | undefined;
    return axiosResponse?.data?.topologies ?? [];
  }, [topologiesData]);
  const chips = useMemo(() => chipsData?.data?.chips ?? [], [chipsData?.data?.chips]);
  const cooldowns = useMemo(
    () => cooldownsData?.data?.cooldowns ?? [],
    [cooldownsData?.data?.cooldowns],
  );
  const inheritedSystems = useMemo(
    () => inheritedSystemsData?.data?.systems ?? [],
    [inheritedSystemsData?.data?.systems],
  );

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
      setValue("topologyId", default64?.id ?? topologies[0].id, { shouldValidate: true });
    }
  }, [setValue, topologies, selectedTopologyId]);

  // Preselect the page's cool-down once the dialog opens
  useEffect(() => {
    if (isOpen && defaultCooldownId && !cooldownId) {
      setValue("cooldownId", defaultCooldownId);
    }
  }, [cooldownId, defaultCooldownId, isOpen, setValue]);

  // The chip the new one replaces on the same cryostat is the default wiring source
  const suggestedInheritFrom = useMemo(
    () => (cooldownId ? previousChipOnCryostat(cooldowns, cooldownId) : null),
    [cooldownId, cooldowns],
  );
  useEffect(() => {
    if (
      suggestedInheritFrom &&
      !inheritFrom &&
      chips.some((c) => c.chip_id === suggestedInheritFrom)
    ) {
      setValue("inheritFrom", suggestedInheritFrom);
    }
  }, [chips, inheritFrom, setValue, suggestedInheritFrom]);

  // The inherited chip's default System decides the backend unless the user picked one
  const inheritedBackend = useMemo(
    () => (inheritedSystems.find((s) => s.is_default) ?? inheritedSystems[0])?.backend ?? "",
    [inheritedSystems],
  );
  useEffect(() => {
    if (inheritedBackend && !backend) setValue("backend", inheritedBackend);
  }, [backend, inheritedBackend, setValue]);

  const queryClient = useQueryClient();

  const createChipMutation = useCreateChip({
    mutation: {
      onSuccess: (data) => {
        // Invalidate chips list to refresh
        queryClient.invalidateQueries({ queryKey: getListChipsQueryKey() });

        // Call success callback if provided
        if (onSuccess && data.data) {
          onSuccess(data.data.chip_id);
        }
        setServerError(null);
        const provisioning = data.data?.provisioning ?? null;
        if (provisioning) {
          // Keep the dialog open so the generated files and warnings can be read
          setResult({ chipId: data.data.chip_id, provisioning });
          return;
        }
        reset();
        onClose();
      },
      onError: (err: Error) => {
        setServerError(getApiErrorMessage(err, "Failed to create chip"));
      },
    },
  });

  const submit = (data: CreateChipFormData) => {
    setServerError(null);
    if (!selectedTopology) {
      setError("topologyId", { message: "Please select a topology template" });
      return;
    }

    // Create chip
    createChipMutation.mutate({
      data: {
        chip_id: data.chipId,
        size: selectedTopology.num_qubits,
        topology_id: data.topologyId,
        display_name: data.displayName || undefined,
        cooldown_id: data.cooldownId || undefined,
        inherit_wiring_from: data.inheritFrom || undefined,
        backend: data.backend || undefined,
        provision_config: data.provision === "auto" ? undefined : data.provision === "on",
      },
    });
  };

  const handleClose = () => {
    if (!createChipMutation.isPending) {
      reset();
      setServerError(null);
      setResult(null);
      onClose();
    }
  };

  const pending = createChipMutation.isPending;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent>
        <DialogTitle className="mb-4">
          {result ? `Chip ${result.chipId} created` : "Create New Chip"}
        </DialogTitle>

        {result ? (
          <div className="space-y-4">
            <ProvisioningResultPanel result={result.provisioning} />
            <div className="modal-action">
              <button type="button" className="btn btn-primary" onClick={handleClose}>
                Close
              </button>
            </div>
          </div>
        ) : (
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
                disabled={pending}
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

            {/* Display name */}
            <div className="form-control">
              <label className="label" htmlFor="chip-display-name-input">
                <span className="label-text">Display name</span>
                <span className="label-text-alt text-base-content/60">optional</span>
              </label>
              <input
                id="chip-display-name-input"
                type="text"
                placeholder="Name written to chip.yaml"
                className={`input input-bordered w-full ${errors.displayName ? "input-error" : ""}`}
                disabled={pending}
                {...register("displayName")}
              />
              {errors.displayName && (
                <p className="mt-1 text-sm text-error">{errors.displayName.message}</p>
              )}
            </div>

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
                  disabled={pending}
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
                <label className="label">
                  <span className="label-text-alt text-base-content/60">
                    {selectedTopology.num_qubits} qubits
                  </span>
                </label>
              )}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              {/* Cool-down */}
              <div className="form-control">
                <label className="label" htmlFor="chip-cooldown-select">
                  <span className="label-text">Cool-down</span>
                </label>
                <select
                  id="chip-cooldown-select"
                  className="select select-bordered w-full"
                  disabled={pending}
                  {...register("cooldownId")}
                >
                  <option value="">Not assigned</option>
                  {cooldowns.map((c) => (
                    <option key={c.cooldown_id} value={c.cooldown_id}>
                      {c.cooldown_id}
                      {c.ended_at ? "" : " (active)"}
                    </option>
                  ))}
                </select>
              </div>

              {/* Inherit wiring from */}
              <div className="form-control">
                <label className="label" htmlFor="chip-inherit-select">
                  <span className="label-text">Inherit wiring from</span>
                </label>
                <select
                  id="chip-inherit-select"
                  className="select select-bordered w-full"
                  disabled={pending}
                  {...register("inheritFrom")}
                >
                  <option value="">None (empty wiring)</option>
                  {chips.map((c) => (
                    <option key={c.chip_id} value={c.chip_id}>
                      {c.chip_id}
                    </option>
                  ))}
                </select>
                {suggestedInheritFrom && inheritFrom === suggestedInheritFrom && (
                  <label className="label">
                    <span className="label-text-alt text-base-content/60">
                      Previous chip on this cryostat
                    </span>
                  </label>
                )}
              </div>

              {/* Backend */}
              <div className="form-control">
                <label className="label" htmlFor="chip-backend-select">
                  <span className="label-text">Backend</span>
                </label>
                <select
                  id="chip-backend-select"
                  className="select select-bordered w-full"
                  disabled={pending}
                  {...register("backend")}
                >
                  <option value="">
                    {inheritedBackend ? inheritedBackend : "quel1 (default)"}
                  </option>
                  {BACKEND_OPTIONS.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
              </div>

              {/* Configuration generation */}
              <div className="form-control">
                <label className="label" htmlFor="chip-provision-select">
                  <span className="label-text">Generate configuration files</span>
                </label>
                <select
                  id="chip-provision-select"
                  className="select select-bordered w-full"
                  disabled={pending}
                  {...register("provision")}
                >
                  <option value="auto">Auto (shared layout only)</option>
                  <option value="on">Always</option>
                  <option value="off">Never (database record only)</option>
                </select>
              </div>
            </div>

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
              <button type="button" className="btn" onClick={handleClose} disabled={pending}>
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={pending}
                data-tour="submit-chip"
              >
                {pending ? (
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
        )}
      </DialogContent>
    </Dialog>
  );
}
