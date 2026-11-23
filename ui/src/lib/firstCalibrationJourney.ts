/**
 * Browser-side record of the first calibration journey.
 *
 * The record only remembers which chip, flow, execution and task result the journey points at;
 * whether a stage is finished is always decided from the server records those ids name (see
 * `deriveJourneyProgress` in the first-calibration feature). It lives in localStorage under a key
 * scoped to the signed-in user and the active project, so switching either never shows another
 * journey.
 */

const JOURNEY_VERSION = 1;
const STORAGE_PREFIX = "qdash:first-calibration";
export const JOURNEY_CHANGE_EVENT = "qdash:first-calibration-change";

/** Query value that marks a link opened from the journey. */
export const JOURNEY_QUERY_VALUE = "first-calibration";
/** Query value that asks the Chip page to open the Create Chip dialog for the journey. */
export const JOURNEY_CREATE_CHIP_QUERY_VALUE = "create-chip";

export interface JourneyState {
  version: typeof JOURNEY_VERSION;
  /** `paused` hides the banner until the journey is resumed from Home. */
  status: "active" | "paused";
  chipId: string | null;
  flowName: string | null;
  executionId: string | null;
  /** Chip the user confirmed as ready for real hardware; only used on hardware deployments. */
  hardwareConfirmedChipId: string | null;
  /** A successful task result of `executionId` that the user opened. */
  inspectedTaskId: string | null;
  /** The user opened the Chip overview of `chipId` after inspecting a result. */
  chipOverviewSeen: boolean;
  startedAt: string;
  updatedAt: string;
}

export type JourneyEvent =
  | { type: "start"; chipId: string | null; now: string }
  | { type: "pause"; now: string }
  | { type: "resume"; now: string }
  | { type: "chipSelected"; chipId: string; now: string }
  | { type: "flowSaved"; flowName: string; chipId: string; now: string }
  | { type: "flowCleared"; now: string }
  | { type: "runStarted"; flowName: string; chipId: string; executionId: string; now: string }
  | { type: "hardwareConfirmed"; chipId: string; confirmed: boolean; now: string }
  | { type: "resultInspected"; executionId: string; taskId: string; now: string }
  | { type: "chipOverviewSeen"; chipId: string; now: string };

const FLOW_NAME_PATTERN = /^[A-Za-z0-9_]+$/;
const MAX_ID_LENGTH = 256;

export function journeyStorageKey(username: string, projectId: string): string {
  return `${STORAGE_PREFIX}:v${JOURNEY_VERSION}:${encodeURIComponent(username)}:${encodeURIComponent(projectId)}`;
}

function isId(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= MAX_ID_LENGTH;
}

function optionalId(value: unknown): string | null | undefined {
  if (value === null) return null;
  return isId(value) ? value : undefined;
}

/** Parse a stored record; anything malformed or from another version is treated as absent. */
export function parseJourneyState(raw: string | null): JourneyState | null {
  if (!raw) return null;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  if (record.version !== JOURNEY_VERSION) return null;
  if (record.status !== "active" && record.status !== "paused") return null;

  const chipId = optionalId(record.chipId);
  const flowName = optionalId(record.flowName);
  const executionId = optionalId(record.executionId);
  const hardwareConfirmedChipId = optionalId(record.hardwareConfirmedChipId);
  const inspectedTaskId = optionalId(record.inspectedTaskId);
  if (
    chipId === undefined ||
    flowName === undefined ||
    executionId === undefined ||
    hardwareConfirmedChipId === undefined ||
    inspectedTaskId === undefined
  ) {
    return null;
  }
  if (flowName !== null && !FLOW_NAME_PATTERN.test(flowName)) return null;
  if (typeof record.chipOverviewSeen !== "boolean") return null;
  if (typeof record.startedAt !== "string" || typeof record.updatedAt !== "string") return null;
  // Later stages only make sense on top of the earlier ones.
  if (flowName !== null && chipId === null) return null;
  if (executionId !== null && flowName === null) return null;
  if (inspectedTaskId !== null && executionId === null) return null;
  if (record.chipOverviewSeen && inspectedTaskId === null) return null;

  return {
    version: JOURNEY_VERSION,
    status: record.status,
    chipId,
    flowName,
    executionId,
    hardwareConfirmedChipId,
    inspectedTaskId,
    chipOverviewSeen: record.chipOverviewSeen,
    startedAt: record.startedAt,
    updatedAt: record.updatedAt,
  };
}

function withChip(state: JourneyState, chipId: string, now: string): JourneyState {
  if (state.chipId === chipId) return { ...state, updatedAt: now };
  return {
    ...state,
    chipId,
    flowName: null,
    executionId: null,
    inspectedTaskId: null,
    chipOverviewSeen: false,
    updatedAt: now,
  };
}

/**
 * Apply one journey event. An event that does not belong to the journey (another chip, flow or
 * execution than the one it tracks) leaves the state unchanged, so routine work done while a
 * journey is open never moves it.
 */
export function applyJourneyEvent(
  state: JourneyState | null,
  event: JourneyEvent,
): JourneyState | null {
  if (event.type === "start") {
    return {
      version: JOURNEY_VERSION,
      status: "active",
      chipId: event.chipId,
      flowName: null,
      executionId: null,
      hardwareConfirmedChipId: null,
      inspectedTaskId: null,
      chipOverviewSeen: false,
      startedAt: event.now,
      updatedAt: event.now,
    };
  }
  if (!state) return null;

  switch (event.type) {
    case "pause":
      return { ...state, status: "paused", updatedAt: event.now };
    case "resume":
      return { ...state, status: "active", updatedAt: event.now };
    case "chipSelected":
      return withChip(state, event.chipId, event.now);
    case "flowSaved":
      if (state.chipId !== event.chipId) return state;
      if (state.flowName === event.flowName) return { ...state, updatedAt: event.now };
      return {
        ...state,
        flowName: event.flowName,
        executionId: null,
        inspectedTaskId: null,
        chipOverviewSeen: false,
        updatedAt: event.now,
      };
    case "flowCleared":
      return {
        ...state,
        flowName: null,
        executionId: null,
        inspectedTaskId: null,
        chipOverviewSeen: false,
        updatedAt: event.now,
      };
    case "runStarted":
      if (state.chipId !== event.chipId || state.flowName !== event.flowName) return state;
      return {
        ...state,
        executionId: event.executionId,
        inspectedTaskId: null,
        chipOverviewSeen: false,
        updatedAt: event.now,
      };
    case "hardwareConfirmed":
      if (state.chipId !== event.chipId) return state;
      return {
        ...state,
        hardwareConfirmedChipId: event.confirmed ? event.chipId : null,
        updatedAt: event.now,
      };
    case "resultInspected":
      if (state.executionId !== event.executionId) return state;
      return { ...state, inspectedTaskId: event.taskId, updatedAt: event.now };
    case "chipOverviewSeen":
      if (state.chipId !== event.chipId || state.inspectedTaskId === null) return state;
      if (state.chipOverviewSeen) return state;
      return { ...state, chipOverviewSeen: true, updatedAt: event.now };
  }
}

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function readJourneyRaw(key: string): string | null {
  try {
    return storage()?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

export function writeJourneyState(key: string, state: JourneyState | null): void {
  const store = storage();
  if (!store) return;
  try {
    if (state) {
      store.setItem(key, JSON.stringify(state));
    } else {
      store.removeItem(key);
    }
  } catch {
    // Storage can be full or blocked; the journey then lasts only for this page view.
  }
  window.dispatchEvent(new CustomEvent(JOURNEY_CHANGE_EVENT, { detail: { key } }));
}

/** A flow name for the journey that does not overwrite one of the user's existing flows. */
export function suggestJourneyFlowName(existingNames: readonly string[]): string {
  const taken = new Set(existingNames);
  const base = "first_calibration";
  if (!taken.has(base)) return base;
  for (let index = 2; index < 1000; index += 1) {
    const candidate = `${base}_${index}`;
    if (!taken.has(candidate)) return candidate;
  }
  return `${base}_${Date.now()}`;
}
