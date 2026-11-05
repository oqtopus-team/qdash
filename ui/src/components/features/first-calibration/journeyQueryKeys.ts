import { getListChipConfigSourcesQueryKey, getListChipsQueryKey } from "@/client/chip/chip";
import { getGetExecutionQueryKey } from "@/client/execution/execution";
import { getGetFlowQueryKey } from "@/client/flow/flow";

/** The signed-in user and active project whose records the journey reads. */
export interface JourneyScope {
  username: string;
  projectId: string;
}

/**
 * Query keys of the records the first calibration journey reads.
 *
 * Each key is the generated key followed by the user and project, so cached answers of one
 * project are never read as evidence in another (the API scopes these routes by the project
 * header, which the generated keys do not include). Starting with the generated key keeps
 * existing invalidations, such as `getListChipsQueryKey()` after creating a chip, reaching them.
 */
function scoped<T extends readonly unknown[]>(base: T, scope: JourneyScope | null) {
  return [
    ...base,
    {
      firstCalibration: {
        username: scope?.username ?? null,
        projectId: scope?.projectId ?? null,
      },
    },
  ] as const;
}

export const journeyQueryKeys = {
  chips: (scope: JourneyScope | null) => scoped(getListChipsQueryKey(), scope),
  configSources: (scope: JourneyScope | null) => scoped(getListChipConfigSourcesQueryKey(), scope),
  flow: (scope: JourneyScope | null, name: string) => scoped(getGetFlowQueryKey(name), scope),
  execution: (scope: JourneyScope | null, executionId: string) =>
    scoped(getGetExecutionQueryKey(executionId), scope),
};
