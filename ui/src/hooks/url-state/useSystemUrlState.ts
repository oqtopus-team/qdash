import { useCallback } from "react";

import { parseAsString, useQueryState } from "nuqs";

interface UseSystemUrlStateResult {
  /** Selected Qubex System, or null for every System of the chip. */
  selectedSystemId: string | null;
  setSelectedSystemId: (systemId: string | null) => void;
}

/** `?system=<system_id>` shared by the chip and metrics pages. */
export function useSystemUrlState(): UseSystemUrlStateResult {
  const [selectedSystemId, setSelectedSystemIdState] = useQueryState("system", parseAsString);

  const setSelectedSystemId = useCallback(
    (systemId: string | null) => {
      setSelectedSystemIdState(systemId || null);
    },
    [setSelectedSystemIdState],
  );

  return { selectedSystemId, setSelectedSystemId };
}
