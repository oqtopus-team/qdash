"use client";

import { useEffect, useRef, useState } from "react";

import { AlertCircle, Check, Loader2 } from "lucide-react";

import { formatDate } from "@/lib/utils/datetime";

type SaveState = "idle" | "saving" | "saved" | "error";

function useNow(intervalMs: number, enabled: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return;
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs, enabled]);
  return now;
}

function formatAgo(savedAt: Date | null, now: number): string {
  if (!savedAt) return "";
  const seconds = Math.max(0, Math.floor((now - savedAt.getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return formatDate(savedAt.toISOString());
}

export function SaveStatus({
  state,
  savedAt,
}: {
  state: SaveState;
  savedAt: Date | null;
}) {
  const now = useNow(15_000, state === "saved" && savedAt !== null);
  if (state === "saving") {
    return (
      <span className="flex items-center gap-1 text-[11px] text-base-content/50">
        <Loader2 className="h-3 w-3 animate-spin" />
        Saving…
      </span>
    );
  }
  if (state === "error") {
    return (
      <span className="flex items-center gap-1 text-[11px] text-error">
        <AlertCircle className="h-3 w-3" />
        Save failed — retrying on next edit
      </span>
    );
  }
  if (state === "saved" && savedAt) {
    return (
      <span className="flex items-center gap-1 text-[11px] text-base-content/50">
        <Check className="h-3 w-3" />
        Saved · {formatAgo(savedAt, now)}
      </span>
    );
  }
  return null;
}

interface UseDebouncedAutosaveOptions<T> {
  /** Equality check to skip no-op saves. Defaults to JSON.stringify compare. */
  isEqual?: (a: T, b: T) => boolean;
  /** Snapshot of the currently-persisted value (used for the no-op check). */
  initialBaseline: T;
  /** Debounce window in milliseconds. */
  delayMs?: number;
  /** Performs the actual save. Resolves on success, rejects on failure. */
  save: (value: T) => Promise<void>;
}

interface AutosaveHandle<T> {
  state: SaveState;
  savedAt: Date | null;
  /** Schedule a save (debounced). */
  schedule: (value: T) => void;
  /** Force an immediate save now (skips the debounce). */
  flush: () => Promise<void>;
}

const defaultIsEqual = <T,>(a: T, b: T): boolean =>
  JSON.stringify(a) === JSON.stringify(b);

/**
 * Drives a debounced autosave with a status state machine.
 *
 *   const auto = useDebouncedAutosave({
 *     initialBaseline: serverValue,
 *     save: async (v) => { await mutate(v); },
 *   });
 *   <input onChange={(e) => auto.schedule(e.target.value)} />
 *   <SaveStatus state={auto.state} savedAt={auto.savedAt} />
 */
export function useDebouncedAutosave<T>(
  opts: UseDebouncedAutosaveOptions<T>,
): AutosaveHandle<T> {
  const {
    isEqual = defaultIsEqual,
    initialBaseline,
    delayMs = 800,
    save,
  } = opts;
  const [state, setState] = useState<SaveState>("idle");
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const baselineRef = useRef<T>(initialBaseline);
  const pendingRef = useRef<{ value: T } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveRef = useRef(save);
  const isEqualRef = useRef(isEqual);
  saveRef.current = save;
  isEqualRef.current = isEqual;

  const flush = async () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const pending = pendingRef.current;
    if (!pending) return;
    if (isEqualRef.current(pending.value, baselineRef.current)) {
      pendingRef.current = null;
      return;
    }
    pendingRef.current = null;
    setState("saving");
    try {
      await saveRef.current(pending.value);
      baselineRef.current = pending.value;
      setSavedAt(new Date());
      setState("saved");
    } catch {
      setState("error");
    }
  };

  const schedule = (value: T) => {
    pendingRef.current = { value };
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      void flush();
    }, delayMs);
  };

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        void flush();
      }
    };
  }, []);

  return { state, savedAt, schedule, flush };
}
