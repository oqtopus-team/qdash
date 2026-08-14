"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useQueryClient } from "@tanstack/react-query";

import { useCreateChip, getListChipsQueryKey } from "@/client/chip/chip";
import { useListTopologies } from "@/client/topology/topology";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/Dialog";

interface TopologyItem {
  id: string;
  name: string;
  num_qubits: number;
}

interface CreateChipModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (chipId: string) => void;
}

const createChipSchema = z.object({
  chipId: z.string().trim().min(1, "Chip ID is required"),
  topologyId: z.string().min(1, "Please select a topology template"),
});

type CreateChipFormData = z.infer<typeof createChipSchema>;

export function CreateChipModal({ isOpen, onClose, onSuccess }: CreateChipModalProps) {
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
    defaultValues: { chipId: "", topologyId: "" },
  });
  const selectedTopologyId = watch("topologyId");

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
      setValue("topologyId", default64?.id ?? topologies[0].id, { shouldValidate: true });
    }
  }, [setValue, topologies, selectedTopologyId]);

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

        // Reset form and close modal
        reset();
        setServerError(null);
        onClose();
      },
      onError: (err: Error) => {
        const axiosErr = err as Error & {
          response?: { data?: { detail?: string } };
        };
        setServerError(axiosErr.response?.data?.detail || "Failed to create chip");
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
              disabled={createChipMutation.isPending}
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
