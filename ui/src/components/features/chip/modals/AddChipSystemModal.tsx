"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useQueryClient } from "@tanstack/react-query";

import { getListChipSystemsQueryKey, useAddChipSystem } from "@/client/chip/chip";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import type { AddChipSystemResponse } from "@/schemas";

import { ProvisioningResultPanel } from "../ProvisioningResultPanel";
import { BACKEND_OPTIONS } from "./CreateChipModal";

/** "0, 4,8" → [0, 4, 8]; null when a token is not a non-negative integer. */
export function parseMuxIds(value: string): number[] | null {
  const tokens = value
    .split(/[\s,]+/)
    .map((t) => t.trim())
    .filter((t) => t !== "");
  const ids: number[] = [];
  for (const token of tokens) {
    if (!/^\d+$/.test(token)) return null;
    const id = Number(token);
    if (!ids.includes(id)) ids.push(id);
  }
  return ids;
}

const addSystemSchema = z.object({
  backend: z.string().min(1, "Select a backend"),
  muxIds: z
    .string()
    .trim()
    .min(1, "Enter at least one MUX number")
    .refine((v) => (parseMuxIds(v)?.length ?? 0) > 0, "MUX numbers are non-negative integers"),
  settings: z
    .string()
    .trim()
    .refine((v) => {
      if (!v) return true;
      try {
        const parsed: unknown = JSON.parse(v);
        return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed);
      } catch {
        return false;
      }
    }, "Settings must be a JSON object"),
});

type AddSystemFormData = z.infer<typeof addSystemSchema>;

interface AddChipSystemModalProps {
  chipId: string;
  existingBackends: string[];
  onClose: () => void;
}

/** Moves MUXes of a chip to a new System on another backend. */
export function AddChipSystemModal({ chipId, existingBackends, onClose }: AddChipSystemModalProps) {
  const queryClient = useQueryClient();
  const [serverError, setServerError] = useState<string | null>(null);
  const [result, setResult] = useState<AddChipSystemResponse | null>(null);
  const freeBackends = BACKEND_OPTIONS.filter((b) => !existingBackends.includes(b));
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<AddSystemFormData>({
    resolver: zodResolver(addSystemSchema),
    defaultValues: { backend: freeBackends[0] ?? "", muxIds: "", settings: "" },
  });

  const addSystem = useAddChipSystem({
    mutation: {
      onSuccess: (data) => {
        queryClient.invalidateQueries({ queryKey: getListChipSystemsQueryKey(chipId) });
        setServerError(null);
        setResult(data.data);
      },
      onError: (err: Error) => {
        setServerError(getApiErrorMessage(err, "Failed to add the System"));
      },
    },
  });

  const submit = (data: AddSystemFormData) => {
    setServerError(null);
    addSystem.mutate({
      chipId,
      data: {
        backend: data.backend,
        mux_ids: parseMuxIds(data.muxIds) ?? [],
        settings: data.settings
          ? (JSON.parse(data.settings) as Record<string, unknown>)
          : undefined,
      },
    });
  };

  const pending = addSystem.isPending;
  const handleClose = () => {
    if (!pending) onClose();
  };

  return (
    <Dialog open onOpenChange={(open) => !open && handleClose()}>
      <DialogContent>
        <DialogTitle className="mb-1">
          {result ? `System ${result.system.system_id} added` : `Add a System to ${chipId}`}
        </DialogTitle>
        <DialogDescription className="mb-4 text-sm text-base-content/70">
          {result
            ? "The MUXes now belong to the new System."
            : "The MUXes move to a System on the chosen backend. Register its boxes first."}
        </DialogDescription>

        {result ? (
          <div className="space-y-4">
            <ProvisioningResultPanel
              systemIds={[result.system.system_id]}
              files={result.files}
              publish={result.publish}
              warnings={result.warnings}
            />
            <div className="modal-action">
              <button type="button" className="btn btn-primary" onClick={onClose}>
                Close
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit(submit)} className="space-y-4" noValidate>
            <div className="form-control">
              <label className="label" htmlFor="add-system-backend">
                <span className="label-text">Backend</span>
              </label>
              <select
                id="add-system-backend"
                className={`select select-bordered w-full ${errors.backend ? "select-error" : ""}`}
                disabled={pending}
                {...register("backend")}
              >
                {freeBackends.length === 0 && (
                  <option value="">Every backend already has a System</option>
                )}
                {freeBackends.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
              {errors.backend && (
                <p className="mt-1 text-sm text-error">{errors.backend.message}</p>
              )}
            </div>

            <div className="form-control">
              <label className="label" htmlFor="add-system-mux">
                <span className="label-text">MUX numbers</span>
              </label>
              <input
                id="add-system-mux"
                type="text"
                placeholder="e.g., 8, 9, 10, 11"
                className={`input input-bordered w-full font-mono ${errors.muxIds ? "input-error" : ""}`}
                disabled={pending}
                aria-invalid={Boolean(errors.muxIds)}
                {...register("muxIds")}
              />
              {errors.muxIds && <p className="mt-1 text-sm text-error">{errors.muxIds.message}</p>}
            </div>

            <div className="form-control">
              <label className="label" htmlFor="add-system-settings">
                <span className="label-text">Backend settings</span>
                <span className="label-text-alt text-base-content/60">optional JSON</span>
              </label>
              <textarea
                id="add-system-settings"
                rows={3}
                placeholder='{"clock_master": "..."}'
                className={`textarea textarea-bordered w-full font-mono text-xs ${errors.settings ? "textarea-error" : ""}`}
                disabled={pending}
                {...register("settings")}
              />
              {errors.settings && (
                <p className="mt-1 text-sm text-error">{errors.settings.message}</p>
              )}
            </div>

            {serverError && (
              <div className="alert alert-error text-sm" role="alert">
                <span>{serverError}</span>
              </div>
            )}

            <div className="modal-action">
              <button type="button" className="btn" onClick={handleClose} disabled={pending}>
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={pending || freeBackends.length === 0}
              >
                {pending ? (
                  <>
                    <span className="loading loading-spinner loading-sm" aria-hidden="true"></span>
                    Adding...
                  </>
                ) : (
                  "Add"
                )}
              </button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
