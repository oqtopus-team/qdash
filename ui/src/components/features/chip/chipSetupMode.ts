import type { ConfigPresetResponse, ListConfigSourcesResponse } from "@/schemas";

/** Preset (and deployment backend) of the fake backend's virtual device. */
const FAKE_PRESET_ID = "fake";
/** Preset (and deployment backend) of the Qibocal one-qubit emulator. */
const QIBOCAL_PRESET_ID = "qibocal";

/** Deployment backends whose chips are always created from the backend's own preset. */
const PRESET_BACKENDS: ReadonlySet<string> = new Set([FAKE_PRESET_ID, QIBOCAL_PRESET_ID]);

/**
 * How the Create Chip dialog sets up a new chip on this deployment.
 *
 * - `pending`: the deployment is not known yet (loading, or the check failed); show no setup
 *   controls, so a preset deployment never shows hardware controls.
 * - `hardware`: the deployment calibrates real devices; choose the topology and wiring.
 * - `preset`: the deployment runs a backend without hardware (fake or qibocal); every chip is
 *   that backend's fixed device and QDash sets it up. `backend` is the deployment backend.
 *   `preset` is null when the API does not offer it, and `configAvailable` is false when no
 *   configuration tree is mounted; both block creation when the preset needs that tree.
 */
export type ChipSetupMode =
  | { kind: "pending"; failed: boolean }
  | { kind: "hardware" }
  | {
      kind: "preset";
      backend: string;
      preset: ConfigPresetResponse | null;
      configAvailable: boolean;
    };

export function resolveChipSetupMode(
  data: ListConfigSourcesResponse | undefined,
  { isError }: { isError: boolean },
): ChipSetupMode {
  if (isError) return { kind: "pending", failed: true };
  if (!data) return { kind: "pending", failed: false };
  const backend = data.deployment_backend ?? null;
  // The API lists only the presets of the deployment backend.
  const preset =
    data.presets?.find((item) => item.preset_id === backend) ?? data.presets?.[0] ?? null;
  if ((backend !== null && PRESET_BACKENDS.has(backend)) || preset) {
    return {
      kind: "preset",
      backend: backend ?? preset?.preset_id ?? FAKE_PRESET_ID,
      preset,
      configAvailable: data.available,
    };
  }
  return { kind: "hardware" };
}

/** Whether a preset deployment can create its device chip now. */
export function canCreatePresetChip(mode: ChipSetupMode): mode is {
  kind: "preset";
  backend: string;
  preset: ConfigPresetResponse;
  configAvailable: boolean;
} {
  return (
    mode.kind === "preset" &&
    mode.preset !== null &&
    (mode.configAvailable || mode.preset.requires_config_tree === false)
  );
}

/** How the UI names a preset deployment's backend. */
export function presetBackendLabel(backend: string): string {
  if (backend === FAKE_PRESET_ID) return "fake backend";
  if (backend === QIBOCAL_PRESET_ID) return "Qibocal emulator backend";
  return `${backend} backend`;
}

/** Name of the flow template a preset deployment calibrates its chip with. */
export function presetTemplateName(mode: { backend: string }): string {
  if (mode.backend === FAKE_PRESET_ID) return "Fake Backend Calibration";
  if (mode.backend === QIBOCAL_PRESET_ID) return "Qibocal Emulator Rabi Amplitude";
  return "preset template";
}
