import { journeyStorageKey } from "@/lib/firstCalibrationJourney";

/** Mirrors the storage key `getProjectId()` reads the active project from. */
export const PROJECT_STORAGE_KEY = "qdash_current_project_id";

function journeyKey(projectId: string, username = "alice"): string {
  return journeyStorageKey(username, projectId);
}

export function storeJourney(
  projectId: string,
  overrides: Record<string, unknown> = {},
  username = "alice",
): void {
  window.localStorage.setItem(
    journeyKey(projectId, username),
    JSON.stringify({
      version: 1,
      status: "active",
      chipId: null,
      flowName: null,
      executionId: null,
      hardwareConfirmedChipId: null,
      inspectedTaskId: null,
      chipOverviewSeen: false,
      startedAt: "2026-11-05T00:00:00.000Z",
      updatedAt: "2026-11-05T00:00:00.000Z",
      ...overrides,
    }),
  );
}

export function storedJourney(projectId: string, username = "alice") {
  const raw = window.localStorage.getItem(journeyKey(projectId, username));
  return raw ? JSON.parse(raw) : null;
}

/** A promise the test settles by hand, to answer a request after something else happened. */
export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
