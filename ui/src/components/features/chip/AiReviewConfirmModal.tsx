"use client";

import { Bot, X } from "lucide-react";

import type { ModelOverride } from "@/lib/copilotModels";

interface ModelOption {
  key: string;
  label: string;
  model: ModelOverride | null;
}

interface AiReviewConfirmModalProps {
  isOpen: boolean;
  selectedCount: number;
  taskName: string;
  modelOptions: ModelOption[];
  selectedModelKey: string;
  isSubmitting: boolean;
  onModelChange: (key: string) => void;
  onConfirm: () => void;
  onClose: () => void;
}

export function AiReviewConfirmModal({
  isOpen,
  selectedCount,
  taskName,
  modelOptions,
  selectedModelKey,
  isSubmitting,
  onModelChange,
  onConfirm,
  onClose,
}: AiReviewConfirmModalProps) {
  if (!isOpen) return null;

  const selectedModel =
    modelOptions.find((option) => option.key === selectedModelKey) ?? modelOptions[0];
  const modelName = selectedModel?.model
    ? `${selectedModel.model.provider}/${selectedModel.model.name}`
    : selectedModel?.label || "Configured model";

  return (
    <div className="modal modal-open">
      <div className="modal-box max-w-lg rounded-lg">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-primary" />
            <h3 className="font-semibold text-lg">Request AI review</h3>
          </div>
          <button
            type="button"
            className="btn btn-sm btn-ghost btn-circle"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4 space-y-3 text-sm">
          <div className="rounded-md bg-base-200 px-3 py-2">
            <div className="flex justify-between gap-3">
              <span className="text-base-content/60">Task</span>
              <span className="font-mono text-right">{taskName}</span>
            </div>
            <div className="flex justify-between gap-3 mt-1">
              <span className="text-base-content/60">Selected results</span>
              <span className="font-semibold">{selectedCount}</span>
            </div>
            <div className="flex justify-between gap-3 mt-1">
              <span className="text-base-content/60">Review model</span>
              <span className="font-mono text-right">{modelName}</span>
            </div>
          </div>

          <label className="form-control w-full">
            <span className="label-text mb-1">Review model</span>
            <select
              className="select select-bordered select-sm w-full"
              value={selectedModelKey}
              onChange={(event) => onModelChange(event.target.value)}
              disabled={isSubmitting}
            >
              {modelOptions.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="modal-action">
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-sm btn-primary gap-2"
            onClick={onConfirm}
            disabled={selectedCount === 0 || isSubmitting}
          >
            {isSubmitting ? (
              <span className="loading loading-spinner loading-xs" />
            ) : (
              <Bot className="h-4 w-4" />
            )}
            Request review
          </button>
        </div>
      </div>
    </div>
  );
}
