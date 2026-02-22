/** Render a fully-expanded parameters table (no internal scroll). */
export function ParametersTable({
  title,
  parameters,
}: {
  title: string;
  parameters: Record<string, unknown>;
}) {
  const entries = Object.entries(parameters);
  if (entries.length === 0) return null;

  return (
    <div className="border border-base-300 bg-base-100 rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-base-200 border-b border-base-300 flex items-center justify-between">
        <span className="text-sm font-semibold">{title}</span>
        <span className="badge badge-xs badge-ghost">{entries.length}</span>
      </div>
      <table className="table table-zebra table-xs w-full">
        <thead>
          <tr>
            <th className="text-xs">Parameter</th>
            <th className="text-xs">Value</th>
            <th className="text-xs">Unit</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([key, val]) => {
            const paramValue =
              typeof val === "object" && val !== null && "value" in val
                ? (val as Record<string, unknown>)
                : { value: val };
            return (
              <tr key={key}>
                <td className="font-medium text-xs">{key}</td>
                <td className="font-mono text-xs">
                  {typeof paramValue.value === "number"
                    ? paramValue.value.toFixed(6)
                    : typeof paramValue.value === "object"
                      ? JSON.stringify(paramValue.value)
                      : String(paramValue.value ?? "N/A")}
                </td>
                <td className="text-xs">{String(paramValue.unit ?? "-")}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
