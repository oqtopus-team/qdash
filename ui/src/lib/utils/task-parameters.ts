const RANGE_VALUE_TYPES = new Set(["np.linspace", "np.logspace", "np.arange", "range"]);

export function formatTaskParameter(value: unknown): string {
  if (value === null || value === undefined) return "";
  return Array.isArray(value) ? JSON.stringify(value) : String(value);
}

export function parseTaskParameter(raw: string, valueType: unknown): unknown {
  const normalized = raw.trim();
  if (valueType === "int") {
    const value = Number(normalized);
    if (!Number.isInteger(value)) throw new Error(`Expected an integer, got "${raw}"`);
    return value;
  }
  if (valueType === "float") {
    const value = Number(normalized);
    if (!Number.isFinite(value)) throw new Error(`Expected a finite number, got "${raw}"`);
    return value;
  }
  if (valueType === "list" || RANGE_VALUE_TYPES.has(String(valueType))) {
    const value: unknown = JSON.parse(normalized);
    if (!Array.isArray(value)) throw new Error(`Expected a JSON array, got "${raw}"`);
    if (valueType !== "list" && value.length !== 3) {
      throw new Error(`Expected exactly 3 array values for ${String(valueType)}`);
    }
    return value;
  }
  if (valueType === "bool") {
    if (normalized.toLowerCase() === "true") return true;
    if (normalized.toLowerCase() === "false") return false;
    throw new Error(`Expected true or false, got "${raw}"`);
  }
  if (valueType === "str" || valueType === "string") return raw;

  if (normalized === "true") return true;
  if (normalized === "false") return false;
  const numericValue = Number(normalized);
  return normalized !== "" && Number.isFinite(numericValue) ? numericValue : raw;
}
