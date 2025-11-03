"use client";

import { useState } from "react";
import { useCreateChip } from "@/client/chip/chip";
import { useQueryClient } from "@tanstack/react-query";

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
  const [size, setSize] = useState<64 | 144 | 256 | 1024>(64);
  const [error, setError] = useState<string | null>(null);

  const queryClient = useQueryClient();
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
        setSize(64);
        setError(null);
        onClose();
      },
      onError: (err: any) => {
        setError(err.response?.data?.detail || "Failed to create chip");
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

    // Create chip
    createChipMutation.mutate({
      data: {
        chip_id: chipId.trim(),
        size: size,
      },
    });
  };

  const handleClose = () => {
    if (!createChipMutation.isPending) {
      setChipId("");
      setSize(64);
      setError(null);
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal modal-open">
      <div className="modal-box">
        <h3 className="font-bold text-lg mb-4">Create New Chip</h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Chip ID Input */}
          <div className="form-control">
            <label className="label">
              <span className="label-text">Chip ID</span>
            </label>
            <input
              type="text"
              placeholder="e.g., 64Q, Chip001"
              className="input input-bordered w-full"
              value={chipId}
              onChange={(e) => setChipId(e.target.value)}
              disabled={createChipMutation.isPending}
            />
          </div>

          {/* Size Selection */}
          <div className="form-control">
            <label className="label">
              <span className="label-text">Chip Size</span>
            </label>
            <select
              className="select select-bordered w-full"
              value={size}
              onChange={(e) =>
                setSize(Number(e.target.value) as 64 | 144 | 256 | 1024)
              }
              disabled={createChipMutation.isPending}
            >
              <option value={64}>64 Qubits</option>
              <option value={144}>144 Qubits</option>
              <option value={256}>256 Qubits</option>
              <option value={1024}>1024 Qubits</option>
            </select>
          </div>

          {/* Error Message */}
          {error && (
            <div className="alert alert-error">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="stroke-current shrink-0 h-6 w-6"
                fill="none"
                viewBox="0 0 24 24"
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
                  <span className="loading loading-spinner loading-sm"></span>
                  Creating...
                </>
              ) : (
                "Create Chip"
              )}
            </button>
          </div>
        </form>
      </div>
      <div className="modal-backdrop" onClick={handleClose}></div>
    </div>
  );
}
