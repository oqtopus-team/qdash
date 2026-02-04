/** Render a collapsible parameters table (matching ExecutionClient pattern). */
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
    <div className="collapse collapse-arrow border border-base-300 bg-base-100">
      <input type="checkbox" />
      <div className="collapse-title text-sm font-semibold min-h-0 py-2">
        {title}
        <span className="badge badge-xs badge-ghost ml-2">
          {entries.length}
        </span>
      </div>
      <div className="collapse-content">
        <div className="overflow-x-auto">
          <table className="table table-zebra table-sm">
            <thead>
              <tr>
                <th>Parameter</th>
                <th>Value</th>
                <th>Unit</th>
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
                    <td className="font-medium">{key}</td>
                    <td className="font-mono">
                      {typeof paramValue.value === "number"
                        ? paramValue.value.toFixed(6)
                        : typeof paramValue.value === "object"
                          ? JSON.stringify(paramValue.value)
                          : String(paramValue.value ?? "N/A")}
                    </td>
                    <td>{String(paramValue.unit ?? "-")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
