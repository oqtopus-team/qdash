import type { ConfigPresetResponse, ListConfigSourcesResponse } from "@/schemas";

/** Preset (and deployment backend) of the fake backend's virtual device. */
export const FAKE_PRESET_ID = "fake";

/**
 * How the Create Chip dialog sets up a new chip on this deployment.
 *
 * - `pending`: the deployment is not known yet (loading, or the check failed); show no setup
 *   controls, so a fake deployment never shows hardware controls.
 * - `hardware`: the deployment calibrates real devices; choose the topology and wiring.
 * - `fake`: the deployment runs the fake backend; every chip is its fixed virtual device and
 *   QDash generates the configuration. `preset` is null when the API does not offer it, and
 *   `configAvailable` is false when no configuration tree is mounted; both block creation.
 */
export type ChipSetupMode =
  | { kind: "pending"; failed: boolean }
  | { kind: "hardware" }
  | {
      kind: "fake";
      preset: ConfigPresetResponse | null;
      configAvailable: boolean;
    };

export function resolveChipSetupMode(
  data: ListConfigSourcesResponse | undefined,
  { isError }: { isError: boolean },
): ChipSetupMode {
  if (isError) return { kind: "pending", failed: true };
  if (!data) return { kind: "pending", failed: false };
  const preset = data.presets?.find((item) => item.preset_id === FAKE_PRESET_ID) ?? null;
  if (data.deployment_backend === FAKE_PRESET_ID || preset) {
    return { kind: "fake", preset, configAvailable: data.available };
  }
  return { kind: "hardware" };
}

/** Whether a fake deployment can create its virtual chip now. */
export function canCreateFakeChip(mode: ChipSetupMode): mode is {
  kind: "fake";
  preset: ConfigPresetResponse;
  configAvailable: true;
} {
  return mode.kind === "fake" && mode.preset !== null && mode.configAvailable;
}
