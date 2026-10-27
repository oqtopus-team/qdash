"use client";

import { useState } from "react";

import { Plus } from "lucide-react";

import { useListChipSystems } from "@/client/chip/chip";
import type { ChipSystemInfo } from "@/schemas";

import { AddChipSystemModal } from "./modals/AddChipSystemModal";

function SystemRow({ system }: { system: ChipSystemInfo }) {
  const muxes = system.mux_ids ?? [];
  const boxes = system.box_ids ?? [];
  return (
    <tr>
      <td className="font-mono">
        {system.system_id}
        {system.is_default && <span className="badge badge-primary badge-xs ml-2">default</span>}
      </td>
      <td>
        <span className="badge badge-outline badge-sm">{system.backend}</span>
        <span className="ml-1 text-xs text-base-content/60">{system.driver}</span>
      </td>
      <td className="font-mono text-xs" title={muxes.join(", ")}>
        {muxes.length === 0 ? "—" : `${muxes.length} MUX`}
        {muxes.length > 0 && <span className="text-base-content/60"> ({muxes.join(", ")})</span>}
      </td>
      <td className="font-mono text-xs">{boxes.length === 0 ? "—" : boxes.join(", ")}</td>
      <td>
        <span
          className={`badge badge-xs ${system.has_params ? "badge-success" : "badge-ghost"}`}
          title="params/<system_id>/"
        >
          params
        </span>{" "}
        <span
          className={`badge badge-xs ${system.has_calib_note ? "badge-success" : "badge-ghost"}`}
          title="calibration/<system_id>/calib_note.json"
        >
          note
        </span>
      </td>
    </tr>
  );
}

/**
 * The Systems (box sets per backend) driving a chip, from the Qubex
 * configuration tree, with the action to add one on another backend.
 * Hidden for a legacy-layout chip with its single implicit System.
 */
export function ChipSystemsCard({ chipId, canEdit }: { chipId: string; canEdit: boolean }) {
  const [isAddOpen, setIsAddOpen] = useState(false);
  const { data, isError } = useListChipSystems(chipId, {
    query: { enabled: chipId !== "", staleTime: 30_000 },
  });
  const response = data?.data;
  if (!response || isError) return null;
  const systems = response.systems ?? [];
  if (!response.provisionable && systems.length <= 1) return null;

  return (
    <section className="card card-border bg-base-100" data-testid="chip-systems-card">
      <div className="card-body gap-3 p-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="card-title text-base">Systems</h2>
            <p className="text-xs text-base-content/60">
              {systems.length === 1
                ? "One System drives every MUX of this chip."
                : `${systems.length} Systems drive this chip; a run stays within one System.`}
            </p>
          </div>
          {canEdit && response.provisionable && (
            <button
              type="button"
              className="btn btn-sm btn-outline gap-1"
              onClick={() => setIsAddOpen(true)}
            >
              <Plus size={16} />
              Add System
            </button>
          )}
        </div>
        {systems.length === 0 ? (
          <p className="text-sm text-base-content/70">{response.message ?? "No Systems found."}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="table table-sm">
              <thead>
                <tr>
                  <th>System</th>
                  <th>Backend</th>
                  <th>MUX</th>
                  <th>Boxes</th>
                  <th>Files</th>
                </tr>
              </thead>
              <tbody>
                {systems.map((system) => (
                  <SystemRow key={system.system_id} system={system} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {isAddOpen && (
        <AddChipSystemModal
          chipId={chipId}
          existingBackends={systems.map((s) => s.backend)}
          onClose={() => setIsAddOpen(false)}
        />
      )}
    </section>
  );
}
