"use client";

import { useCallback, useEffect, useMemo, useRef, useSyncExternalStore } from "react";

import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { getProjectId } from "@/lib/auth/session";
import {
  JOURNEY_CHANGE_EVENT,
  applyJourneyEvent,
  journeyStorageKey,
  parseJourneyState,
  readJourneyRaw,
  writeJourneyState,
  type JourneyEvent,
  type JourneyState,
} from "@/lib/firstCalibrationJourney";

type DistributiveOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never;
type JourneyEventInput = DistributiveOmit<JourneyEvent, "now">;

/**
 * The user and project an action was submitted in. A request that answers after the user switched
 * project (or signed out) belongs to the old context: `isCurrent()` turns false and `record` does
 * nothing, so a late answer can neither move the new context's journey nor speak for it.
 */
export interface JourneyContext {
  isCurrent: () => boolean;
  /**
   * Record an event in the captured context. Returns the stored journey after the event, or null
   * when nothing was recorded (another context, no journey, or not allowed to edit).
   */
  record: (event: JourneyEventInput) => JourneyState | null;
  /**
   * Whether the journey stored now is still the active journey the action was submitted for:
   * the same journey (same start), active then and active now. A journey paused, finished or
   * restarted while the request was pending is not followed, so its answer never moves the user.
   */
  followsSubmittedJourney: () => boolean;
}

export interface FirstCalibrationJourney {
  /** The stored journey of this user and project, or null when none is open. */
  state: JourneyState | null;
  /** Whether the current user may run the journey here: signed in, in a project, and an editor. */
  enabled: boolean;
  record: (event: JourneyEventInput) => void;
  /** Forget the journey of this user and project. */
  reset: () => void;
  /** Snapshot the current user and project, to check an asynchronous answer against later. */
  capture: () => JourneyContext;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(JOURNEY_CHANGE_EVENT, onChange);
  // Another tab of the same browser can move the journey too.
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(JOURNEY_CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

function writeEvent(key: string, event: JourneyEventInput): JourneyState | null {
  const current = parseJourneyState(readJourneyRaw(key));
  const next = applyJourneyEvent(current, {
    ...event,
    now: new Date().toISOString(),
  } as JourneyEvent);
  if (next !== current) writeJourneyState(key, next);
  return next;
}

/**
 * The first calibration journey of the signed-in user in the active project.
 *
 * Viewers get `enabled: false` and a null state, so no journey UI or event recording runs for
 * them even when a record was left behind by an earlier editor role.
 */
export function useFirstCalibrationJourney(): FirstCalibrationJourney {
  const { username } = useAuth();
  const { projectId, canEdit } = useProject();
  const key = username && projectId ? journeyStorageKey(username, projectId) : null;

  const raw = useSyncExternalStore(
    subscribe,
    () => (key ? readJourneyRaw(key) : null),
    () => null,
  );
  const parsed = useMemo(() => parseJourneyState(raw), [raw]);
  const enabled = Boolean(key) && canEdit;

  // The context this component renders in now; cleared on unmount, so an answer that lands after
  // the page is gone is not treated as current either.
  const latest = useRef<{
    key: string | null;
    projectId: string | null;
    enabled: boolean;
  }>({
    key,
    projectId,
    enabled,
  });
  useEffect(() => {
    latest.current = { key, projectId, enabled };
  });
  useEffect(
    () => () => {
      latest.current = { key: null, projectId: null, enabled: false };
    },
    [],
  );

  // Drop a record that no longer parses, e.g. one written by an older version.
  useEffect(() => {
    if (key && raw !== null && parsed === null) writeJourneyState(key, null);
  }, [key, raw, parsed]);

  const record = useCallback(
    (event: JourneyEventInput) => {
      if (!key || !enabled) return;
      writeEvent(key, event);
    },
    [key, enabled],
  );

  const reset = useCallback(() => {
    if (key) writeJourneyState(key, null);
  }, [key]);

  const capture = useCallback((): JourneyContext => {
    const captured = { key, projectId, enabled };
    // The journey the action is submitted for, read from storage so it is never a stale render.
    const submitted = key && enabled ? parseJourneyState(readJourneyRaw(key)) : null;
    const submittedActive = submitted?.status === "active" ? submitted : null;
    const isCurrent = () => {
      const now = latest.current;
      // The project header of API requests is read from storage, which a switch updates before
      // React renders the new project; checking both closes that window.
      return (
        captured.key !== null &&
        now.key === captured.key &&
        now.projectId === captured.projectId &&
        getProjectId() === captured.projectId
      );
    };
    return {
      isCurrent,
      record: (event) => {
        if (!captured.key || !captured.enabled || !isCurrent()) return null;
        return writeEvent(captured.key, event);
      },
      followsSubmittedJourney: () => {
        if (!captured.key || submittedActive === null || !isCurrent()) return false;
        const now = parseJourneyState(readJourneyRaw(captured.key));
        return now?.status === "active" && now.startedAt === submittedActive.startedAt;
      },
    };
  }, [key, projectId, enabled]);

  return { state: enabled ? parsed : null, enabled, record, reset, capture };
}
