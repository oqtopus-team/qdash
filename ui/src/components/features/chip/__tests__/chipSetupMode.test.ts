import { describe, expect, it } from "vitest";

import {
  canCreatePresetChip,
  resolveChipSetupMode,
} from "@/components/features/chip/chipSetupMode";
import type { ConfigPresetResponse, ListConfigSourcesResponse } from "@/schemas";

const QIBOCAL_PRESET: ConfigPresetResponse = {
  preset_id: "qibocal",
  name: "Qibocal emulator qubit",
  description: "",
  topology_id: "qibocal-emulator-1",
  n_qubits: 1,
  mux_count: 0,
  workflow_template_id: "qibocal_rabi_amplitude",
  requires_config_tree: false,
};

function sources(overrides: Partial<ListConfigSourcesResponse>): ListConfigSourcesResponse {
  return { available: true, sources: [], presets: [], deployment_backend: "qubex", ...overrides };
}

describe("resolveChipSetupMode", () => {
  it("uses the qibocal preset on a qibocal deployment, even without a configuration tree", () => {
    const mode = resolveChipSetupMode(
      sources({ deployment_backend: "qibocal", presets: [QIBOCAL_PRESET], available: false }),
      { isError: false },
    );

    expect(mode).toEqual({
      kind: "preset",
      backend: "qibocal",
      preset: QIBOCAL_PRESET,
      configAvailable: false,
    });
    expect(canCreatePresetChip(mode)).toBe(true);
  });

  it("never offers hardware setup on a qibocal deployment without its preset", () => {
    const mode = resolveChipSetupMode(sources({ deployment_backend: "qibocal" }), {
      isError: false,
    });

    expect(mode).toEqual({
      kind: "preset",
      backend: "qibocal",
      preset: null,
      configAvailable: true,
    });
    expect(canCreatePresetChip(mode)).toBe(false);
  });

  it("blocks a preset that writes configuration while no tree is mounted", () => {
    const mode = resolveChipSetupMode(
      sources({
        deployment_backend: "fake",
        available: false,
        presets: [{ ...QIBOCAL_PRESET, preset_id: "fake", requires_config_tree: true }],
      }),
      { isError: false },
    );

    expect(canCreatePresetChip(mode)).toBe(false);
  });

  it("keeps hardware setup on a qubex deployment", () => {
    expect(resolveChipSetupMode(sources({}), { isError: false })).toEqual({ kind: "hardware" });
  });
});
