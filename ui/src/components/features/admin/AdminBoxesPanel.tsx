"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus } from "lucide-react";

import {
  getListConfigBoxesQueryKey,
  useListConfigBoxes,
  useUpsertConfigBox,
} from "@/client/config/config";
import { PublishStatusBadge } from "@/components/features/chip/ProvisioningResultPanel";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import type { ChipPublishStatus, ConfigBox } from "@/schemas";

/** One option per line (or comma); undefined when empty. */
export function parseOptions(value: string): string[] | undefined {
  const options = value
    .split(/[\n,]+/)
    .map((v) => v.trim())
    .filter((v) => v !== "");
  return options.length > 0 ? options : undefined;
}

/** Box types whose entry carries a network address and an adapter id. */
export function needsAddress(type: string): boolean {
  return type.startsWith("quel1") || type.startsWith("qube");
}

const boxSchema = z.object({
  boxId: z
    .string()
    .trim()
    .min(1, "Box ID is required")
    .regex(/^[A-Za-z0-9][A-Za-z0-9_.-]*$/, "Use letters, digits, '-', '_' and '.' only"),
  name: z.string().trim().min(1, "Name is required").max(200),
  type: z.string().min(1, "Select a box type"),
  address: z.string().trim(),
  adapter: z.string().trim(),
  options: z.string().trim(),
});

type BoxFormData = z.infer<typeof boxSchema>;

const EMPTY: BoxFormData = { boxId: "", name: "", type: "", address: "", adapter: "", options: "" };

function toForm(box: ConfigBox): BoxFormData {
  return {
    boxId: box.box_id,
    name: box.name,
    type: box.type,
    address: box.address ?? "",
    adapter: box.adapter ?? "",
    options: (box.options ?? []).join("\n"),
  };
}

/**
 * The control boxes every chip's wiring may reference (`config/box.yaml`),
 * with a form to register or edit one. Administrators only.
 */
export function AdminBoxesPanel() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useListConfigBoxes();
  const response = data?.data;
  const boxes = useMemo(() => response?.boxes ?? [], [response?.boxes]);
  const boxTypes = useMemo(() => response?.box_types ?? [], [response?.box_types]);
  const [editing, setEditing] = useState<ConfigBox | "new" | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [lastPublish, setLastPublish] = useState<ChipPublishStatus | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<BoxFormData>({ resolver: zodResolver(boxSchema), defaultValues: EMPTY });
  const type = watch("type");

  useEffect(() => {
    if (editing === null) return;
    reset(editing === "new" ? { ...EMPTY, type: boxTypes[0] ?? "" } : toForm(editing));
    setServerError(null);
  }, [boxTypes, editing, reset]);

  const upsert = useUpsertConfigBox({
    mutation: {
      onSuccess: (result) => {
        queryClient.invalidateQueries({ queryKey: getListConfigBoxesQueryKey() });
        setLastPublish(result.data.publish);
        setEditing(null);
      },
      onError: (err: Error) => setServerError(getApiErrorMessage(err, "Failed to save the box")),
    },
  });

  const submit = (form: BoxFormData) => {
    setServerError(null);
    upsert.mutate({
      data: {
        box_id: form.boxId,
        name: form.name,
        type: form.type,
        address: form.address || undefined,
        adapter: form.adapter || undefined,
        options: parseOptions(form.options),
      },
    });
  };

  return (
    <section className="card card-border bg-base-100">
      <div className="card-body gap-5 p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="card-title text-lg">Control boxes</h2>
            <p className="mt-1 text-sm text-base-content/60">
              The box catalog shared by every chip&apos;s wiring (box.yaml).
            </p>
          </div>
          <div className="flex items-center gap-2">
            {lastPublish && <PublishStatusBadge publish={lastPublish} />}
            <button
              type="button"
              className="btn btn-sm btn-primary gap-1"
              onClick={() => setEditing("new")}
              disabled={!response?.editable}
            >
              <Plus size={16} />
              Register box
            </button>
          </div>
        </div>

        {response && !response.editable && (
          <div className="alert alert-info text-sm" role="status">
            <span>{response.message ?? "Boxes can be registered only in the shared layout."}</span>
          </div>
        )}
        {error && (
          <div className="alert alert-error text-sm" role="alert">
            <span>{getApiErrorMessage(error, "Failed to load boxes")}</span>
          </div>
        )}

        {isLoading ? (
          <span className="loading loading-spinner loading-sm" />
        ) : boxes.length === 0 ? (
          <p className="text-sm text-base-content/60">No boxes registered.</p>
        ) : (
          <div className="overflow-x-auto rounded-box border border-base-300">
            <table className="table table-zebra table-sm">
              <thead>
                <tr>
                  <th>Box ID</th>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Address</th>
                  <th>Adapter</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {boxes.map((box) => (
                  <tr key={box.box_id}>
                    <td className="font-mono">{box.box_id}</td>
                    <td>{box.name}</td>
                    <td>
                      <span className="badge badge-outline badge-sm">{box.type}</span>
                    </td>
                    <td className="font-mono text-xs">{box.address ?? "—"}</td>
                    <td className="font-mono text-xs">{box.adapter ?? "—"}</td>
                    <td className="text-right">
                      <button
                        type="button"
                        className="btn btn-xs btn-ghost gap-1"
                        onClick={() => setEditing(box)}
                        disabled={!response?.editable}
                        aria-label={`Edit ${box.box_id}`}
                      >
                        <Pencil size={14} />
                        Edit
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {editing !== null && (
          <form
            onSubmit={handleSubmit(submit)}
            className="rounded-box border border-base-300 bg-base-200/40 p-4 space-y-3"
            noValidate
            aria-label={editing === "new" ? "Register box" : `Edit ${editing.box_id}`}
          >
            <h3 className="font-medium">
              {editing === "new" ? "Register a box" : `Edit ${editing.box_id}`}
            </h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="form-control">
                <label className="label" htmlFor="box-id-input">
                  <span className="label-text">Box ID</span>
                </label>
                <input
                  id="box-id-input"
                  className={`input input-bordered input-sm w-full font-mono ${errors.boxId ? "input-error" : ""}`}
                  placeholder="e.g., Q73A"
                  disabled={editing !== "new" || upsert.isPending}
                  {...register("boxId")}
                />
                {errors.boxId && <p className="mt-1 text-xs text-error">{errors.boxId.message}</p>}
              </div>
              <div className="form-control">
                <label className="label" htmlFor="box-name-input">
                  <span className="label-text">Name</span>
                </label>
                <input
                  id="box-name-input"
                  className={`input input-bordered input-sm w-full ${errors.name ? "input-error" : ""}`}
                  disabled={upsert.isPending}
                  {...register("name")}
                />
                {errors.name && <p className="mt-1 text-xs text-error">{errors.name.message}</p>}
              </div>
              <div className="form-control">
                <label className="label" htmlFor="box-type-select">
                  <span className="label-text">Type</span>
                </label>
                <select
                  id="box-type-select"
                  className={`select select-bordered select-sm w-full ${errors.type ? "select-error" : ""}`}
                  disabled={upsert.isPending}
                  {...register("type")}
                >
                  {boxTypes.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                {errors.type && <p className="mt-1 text-xs text-error">{errors.type.message}</p>}
              </div>
              {needsAddress(type) && (
                <>
                  <div className="form-control">
                    <label className="label" htmlFor="box-address-input">
                      <span className="label-text">Address</span>
                    </label>
                    <input
                      id="box-address-input"
                      className="input input-bordered input-sm w-full font-mono"
                      placeholder="10.1.0.21"
                      disabled={upsert.isPending}
                      {...register("address")}
                    />
                  </div>
                  <div className="form-control">
                    <label className="label" htmlFor="box-adapter-input">
                      <span className="label-text">Adapter</span>
                    </label>
                    <input
                      id="box-adapter-input"
                      className="input input-bordered input-sm w-full font-mono"
                      placeholder="e.g., 1"
                      disabled={upsert.isPending}
                      {...register("adapter")}
                    />
                  </div>
                </>
              )}
              <div className="form-control sm:col-span-2">
                <label className="label" htmlFor="box-options-input">
                  <span className="label-text">Options</span>
                  <span className="label-text-alt text-base-content/60">
                    optional, one per line
                  </span>
                </label>
                <textarea
                  id="box-options-input"
                  rows={3}
                  className={`textarea textarea-bordered w-full font-mono text-xs ${errors.options ? "textarea-error" : ""}`}
                  disabled={upsert.isPending}
                  {...register("options")}
                />
                {errors.options && (
                  <p className="mt-1 text-xs text-error">{errors.options.message}</p>
                )}
              </div>
            </div>
            {serverError && (
              <div className="alert alert-error text-sm" role="alert">
                <span>{serverError}</span>
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={() => setEditing(null)}
                disabled={upsert.isPending}
              >
                Cancel
              </button>
              <button type="submit" className="btn btn-sm btn-primary" disabled={upsert.isPending}>
                {upsert.isPending ? "Saving..." : "Save"}
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}
