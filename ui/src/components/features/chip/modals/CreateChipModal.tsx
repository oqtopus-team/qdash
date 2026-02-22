"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";

import { useQueryClient } from "@tanstack/react-query";

import { useCreateChip } from "@/client/chip/chip";
import { useListTopologies } from "@/client/topology/topology";

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

export function CreateChipModal({
  isOpen,
  onClose,
  onSuccess,
}: CreateChipModalProps) {
  const [chipId, setChipId] = useState("");
  const [selectedTopologyId, setSelectedTopologyId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Fetch available topologies
  const { data: topologiesData, isLoading: isLoadingTopologies } =
    useListTopologies(undefined, {
      query: {
        staleTime: Infinity,
      },
    });

  // Parse topologies from API response (Axios wraps in .data)
  const topologies = useMemo(() => {
    const axiosResponse = topologiesData as
      | { data?: { topologies?: TopologyItem[] } }
      | undefined;
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
      setSelectedTopologyId(default64?.id ?? topologies[0].id);
    }
  }, [topologies, selectedTopologyId]);

  const queryClient = useQueryClient();

  // Handle keyboard navigation
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    },
    [onClose],
  );

  // Focus management and keyboard handling
  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
      document.addEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [isOpen, handleKeyDown]);
  const createChipMutation = useCreateChip({
    mutation: {
      onSuccess: (data) => {
        // Invalidate chips list to refresh
        queryClient.invalidateQueries({ queryKey: ["listChips"] });

        // Call success callback if provided
        if (onSuccess && data.data) {
          onSuccess(data.data.chip_id);
        }

        // Reset form and close modal
        setChipId("");
        setSelectedTopologyId("");
        setError(null);
        onClose();
      },
      onError: (err: Error) => {
        const axiosErr = err as Error & {
          response?: { data?: { detail?: string } };
        };
        setError(axiosErr.response?.data?.detail || "Failed to create chip");
      },
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validation
    if (!chipId.trim()) {
      setError("Chip ID is required");
      return;
    }

    if (!selectedTopology) {
      setError("Please select a topology template");
      return;
    }

    // Create chip
    createChipMutation.mutate({
      data: {
        chip_id: chipId.trim(),
        size: selectedTopology.num_qubits,
        topology_id: selectedTopologyId,
      },
    });
  };

  const handleClose = () => {
    if (!createChipMutation.isPending) {
      setChipId("");
      setSelectedTopologyId("");
      setError(null);
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="modal modal-open"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-chip-title"
    >
      <div className="modal-box">
        <h3 id="create-chip-title" className="font-bold text-lg mb-4">
          Create New Chip
        </h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Chip ID Input */}
          <div className="form-control">
            <label className="label" htmlFor="chip-id-input">
              <span className="label-text">Chip ID</span>
            </label>
            <input
              ref={inputRef}
              id="chip-id-input"
              type="text"
              placeholder="e.g., 64Q, Chip001"
              className="input input-bordered w-full"
              value={chipId}
              onChange={(e) => setChipId(e.target.value)}
              disabled={createChipMutation.isPending}
              aria-describedby={error ? "chip-error" : undefined}
            />
          </div>

          {/* Topology Template Selection */}
          <div className="form-control">
            <label className="label" htmlFor="topology-select">
              <span className="label-text">Topology Template</span>
            </label>
            {isLoadingTopologies ? (
              <div className="flex items-center gap-2 h-12">
                <span className="loading loading-spinner loading-sm"></span>
                <span className="text-sm text-base-content/60">
                  Loading templates...
                </span>
              </div>
            ) : (
              <select
                id="topology-select"
                className="select select-bordered w-full"
                value={selectedTopologyId}
                onChange={(e) => setSelectedTopologyId(e.target.value)}
                disabled={createChipMutation.isPending}
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
            {selectedTopology && (
              <label className="label">
                <span className="label-text-alt text-base-content/60">
                  {selectedTopology.num_qubits} qubits
                </span>
              </label>
            )}
          </div>

          {/* Error Message */}
          {error && (
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
              <span>{error}</span>
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
                  <span
                    className="loading loading-spinner loading-sm"
                    aria-hidden="true"
                  ></span>
                  Creating...
                </>
              ) : (
                "Create Chip"
              )}
            </button>
          </div>
        </form>
      </div>
      <div
        className="modal-backdrop"
        onClick={handleClose}
        aria-label="Close modal"
      ></div>
    </div>
  );
}
