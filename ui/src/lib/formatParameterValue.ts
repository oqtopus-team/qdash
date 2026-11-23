/** Short rendering of a parameter value for a table cell, row or graph node. */
export function formatParameterValue(value: unknown, unit?: string): string {
  if (value === null || value === undefined) return "-";
  let text: string;
  if (typeof value === "number") {
    const magnitude = Math.abs(value);
    text =
      value !== 0 && (magnitude >= 1e6 || magnitude < 1e-3)
        ? value.toExponential(3)
        : String(Number(value.toPrecision(6)));
  } else if (typeof value === "boolean") {
    text = value ? "true" : "false";
  } else {
    text = String(value);
  }
  return unit ? `${text} ${unit}` : text;
}
