"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import {
  getGetMetricScriptQueryKey,
  getListMetricScriptsQueryKey,
  useGetMetricScript,
  useUpdateMetricScript,
} from "@/client/metric-script/metric-script";
import type { MetricScriptResponse, MetricScriptResponseVisibility } from "@/schemas";
import { useToast } from "@/components/ui/Toast";
import { getApiErrorMessage } from "@/lib/utils/apiError";

import { errorStatus } from "./errors";

interface MetricScriptSettings {
  name: string;
  description: string;
  visibility: MetricScriptResponseVisibility;
}

interface Baseline extends MetricScriptSettings {
  code: string;
  /** The revision the draft was opened from; sent as `expected_revision` on save. */
  revision: number;
}

/**
 * One metric script open in the editor: the saved document, the draft code and settings,
 * and the save that writes them back. Modelled on `useFlowDocument`.
 */
export interface MetricScriptDocument {
  /** The saved script, updated after each save. */
  script: MetricScriptResponse | undefined;
  isLoading: boolean;
  error: unknown;
  /** The draft below belongs to the script; false until it has loaded. */
  isReady: boolean;
  code: string;
  setCode: (code: string) => void;
  settings: MetricScriptSettings;
  setSettings: (patch: Partial<MetricScriptSettings>) => void;
  /** The draft code or settings differ from the saved script. */
  isDirty: boolean;
  /**
   * Save the draft with the revision it was opened from. A conflict (409) keeps the draft,
   * moves the baseline to the version saved elsewhere and offers to load it. Resolves with
   * the saved script, or null when nothing was saved.
   */
  save: () => Promise<MetricScriptResponse | null>;
  isSaving: boolean;
  /** Drop the draft and show the saved script. */
  discardDraft: () => void;
}

function settingsOf(script: MetricScriptResponse): MetricScriptSettings {
  return { name: script.name, description: script.description, visibility: script.visibility };
}

function baselineOf(script: MetricScriptResponse): Baseline {
  return { ...settingsOf(script), code: script.source, revision: script.revision };
}

const EMPTY_SETTINGS: MetricScriptSettings = { name: "", description: "", visibility: "private" };

export function useMetricScriptDocument(scriptId: string): MetricScriptDocument {
  const toast = useToast();
  const queryClient = useQueryClient();
  const query = useGetMetricScript(scriptId, { query: { enabled: !!scriptId } });
  const script = query.data?.data;
  const refetch = query.refetch;
  const updateMutation = useUpdateMetricScript();

  const [loadedId, setLoadedId] = useState<string | null>(null);
  // Read by a save that answers later, to tell whether the editor still shows its script.
  const loadedIdRef = useRef<string | null>(null);
  // Counts each load, so a save that answers after a reload does not move the new baseline.
  const openCountRef = useRef(0);
  const savingRef = useRef(false);
  const [baseline, setBaseline] = useState<Baseline | null>(null);
  const [code, setCode] = useState("");
  const [settings, setSettingsState] = useState<MetricScriptSettings>(EMPTY_SETTINGS);

  const load = useCallback((next: MetricScriptResponse) => {
    openCountRef.current += 1;
    setBaseline(baselineOf(next));
    setCode(next.source);
    setSettingsState(settingsOf(next));
  }, []);

  // Load the script into the draft once per script. A refetch, such as the one after a save,
  // never replaces the draft, so edits made while a save was pending survive.
  useEffect(() => {
    if (!script || script.script_id !== scriptId) return;
    if (loadedIdRef.current === scriptId) return;
    load(script);
    loadedIdRef.current = scriptId;
    setLoadedId(scriptId);
  }, [load, script, scriptId]);

  const isReady = Boolean(script && baseline && loadedId === scriptId);

  const setSettings = useCallback(
    (patch: Partial<MetricScriptSettings>) =>
      setSettingsState((current) => ({ ...current, ...patch })),
    [],
  );

  const storeScript = useCallback(
    (next: MetricScriptResponse) => {
      queryClient.setQueryData(getGetMetricScriptQueryKey(next.script_id), (current: unknown) =>
        current && typeof current === "object" ? { ...current, data: next } : current,
      );
      void queryClient.invalidateQueries({ queryKey: getListMetricScriptsQueryKey() });
    },
    [queryClient],
  );

  const discardDraft = useCallback(() => {
    void refetch().then((result) => {
      const latest = result.data?.data;
      if (latest && loadedIdRef.current === latest.script_id) load(latest);
    });
  }, [load, refetch]);

  const mutateAsync = updateMutation.mutateAsync;
  const save = useCallback(async (): Promise<MetricScriptResponse | null> => {
    if (!isReady || !baseline || savingRef.current) return null;
    const id = scriptId;
    const openCount = openCountRef.current;
    savingRef.current = true;
    try {
      const response = await mutateAsync({
        scriptId: id,
        data: {
          name: settings.name.trim(),
          description: settings.description,
          visibility: settings.visibility,
          ...(code !== baseline.code ? { source: code } : {}),
          expected_revision: baseline.revision,
        },
      });
      const saved = response.data;
      storeScript(saved);
      if (loadedIdRef.current !== id || openCountRef.current !== openCount) return saved;
      setBaseline(baselineOf(saved));
      if (saved.status === "invalid") {
        toast.warning(
          saved.active_revision
            ? `Saved r${saved.revision} with errors; r${saved.active_revision} stays active`
            : `Saved r${saved.revision} with errors; the script has no valid revision yet`,
        );
      } else {
        toast.success(`Saved r${saved.revision}`);
      }
      return saved;
    } catch (error) {
      if (errorStatus(error) === 409) {
        // Keep the draft; compare it with the version saved elsewhere from now on.
        const result = await refetch();
        const latest = result.data?.data;
        if (latest && loadedIdRef.current === id && openCountRef.current === openCount) {
          setBaseline(baselineOf(latest));
        }
        toast.error("This script was saved elsewhere", {
          description: `${getApiErrorMessage(error, "The script changed")}. Your draft is kept; save again to replace it.`,
          action: { label: "Load saved version", onClick: discardDraft },
        });
      } else {
        toast.error(getApiErrorMessage(error, "Failed to save the script"));
      }
      return null;
    } finally {
      savingRef.current = false;
    }
  }, [
    baseline,
    code,
    discardDraft,
    isReady,
    mutateAsync,
    refetch,
    scriptId,
    settings,
    storeScript,
    toast,
  ]);

  const isDirty =
    isReady &&
    baseline !== null &&
    (code !== baseline.code ||
      settings.name !== baseline.name ||
      settings.description !== baseline.description ||
      settings.visibility !== baseline.visibility);

  return {
    script,
    isLoading: query.isLoading,
    error: query.error,
    isReady,
    code,
    setCode,
    settings,
    setSettings,
    isDirty,
    save,
    isSaving: updateMutation.isPending,
    discardDraft,
  };
}
