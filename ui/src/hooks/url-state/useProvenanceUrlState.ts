import { useCallback, useState, useEffect } from "react";

import { useQueryState, parseAsString } from "nuqs";

import { type ProvenanceTab } from "./types";

interface UseProvenanceUrlStateResult {
  activeTab: ProvenanceTab;
  parameter: string;
  qid: string;
  entityId: string;
  setActiveTab: (tab: ProvenanceTab) => void;
  setParameter: (parameter: string) => void;
  setQid: (qid: string) => void;
  setEntityId: (entityId: string) => void;
  isInitialized: boolean;
  hasSearchParams: boolean;
}

export function useProvenanceUrlState(): UseProvenanceUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management for provenance page
  const [activeTab, setActiveTabState] = useQueryState("tab", parseAsString);
  const [parameter, setParameterState] = useQueryState(
    "parameter",
    parseAsString,
  );
  const [qid, setQidState] = useQueryState("qid", parseAsString);
  const [entityId, setEntityIdState] = useQueryState("entity", parseAsString);

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  // Wrapped setters
  const setActiveTab = useCallback(
    (tab: ProvenanceTab) => {
      setActiveTabState(tab === "history" ? null : tab); // history is default
    },
    [setActiveTabState],
  );

  const setParameter = useCallback(
    (param: string) => {
      setParameterState(param || null);
    },
    [setParameterState],
  );

  const setQid = useCallback(
    (q: string) => {
      setQidState(q || null);
    },
    [setQidState],
  );

  const setEntityId = useCallback(
    (id: string) => {
      setEntityIdState(id || null);
    },
    [setEntityIdState],
  );

  // Check if we have search params for automatic search
  const hasSearchParams = !!(parameter && qid);

  return {
    activeTab: (activeTab as ProvenanceTab) ?? "history",
    parameter: parameter ?? "",
    qid: qid ?? "",
    entityId: entityId ?? "",
    setActiveTab,
    setParameter,
    setQid,
    setEntityId,
    isInitialized,
    hasSearchParams,
  };
}
