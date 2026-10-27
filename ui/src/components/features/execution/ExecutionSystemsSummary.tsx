interface ExecutionSystemsSummaryProps {
  note?: Record<string, unknown> | null;
}

function readStrings(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => (Array.isArray(item) ? item.join("-") : String(item)));
}

/**
 * Which Qubex Systems an execution used, and the couplings it could not
 * calibrate because their qubits sit on different Systems.
 */
export function ExecutionSystemsSummary({ note }: ExecutionSystemsSummaryProps) {
  const systemIds = readStrings(note?.system_ids);
  const crossSystem = readStrings(note?.cross_system_couplings);
  if (systemIds.length === 0 && crossSystem.length === 0) return null;

  return (
    <div className="bg-base-100 rounded-lg shadow-md p-6 space-y-3">
      {systemIds.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">Systems</span>
          {systemIds.map((systemId) => (
            <span key={systemId} className="badge badge-outline badge-primary">
              {systemId}
            </span>
          ))}
        </div>
      )}
      {crossSystem.length > 0 && (
        <div className="space-y-1">
          <div className="text-sm font-semibold">
            Couplings skipped across Systems ({crossSystem.length})
          </div>
          <p className="text-xs text-base-content/70">
            These couplings join qubits driven by different Systems, so one experiment cannot drive
            both ends. They were left out of the CR schedule.
          </p>
          <div className="flex flex-wrap gap-1">
            {crossSystem.map((pair) => (
              <span key={pair} className="badge badge-ghost badge-sm font-mono">
                {pair}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
