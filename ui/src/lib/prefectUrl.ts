export type PrefectUrlLocation = { hostname: string };

/** Resolves the browser-facing Prefect UI URL from the env override or the current page host. */
export function resolvePrefectUrl(location?: PrefectUrlLocation): string {
  const override = process.env.NEXT_PUBLIC_PREFECT_URL?.trim();
  if (override) {
    return override.replace(/\/+$/, "");
  }
  const port = process.env.NEXT_PUBLIC_PREFECT_PORT?.trim() || "4200";
  if (!location) {
    return `http://localhost:${port}`;
  }
  const { hostname } = location;
  const host = hostname.includes(":") && !hostname.startsWith("[") ? `[${hostname}]` : hostname;
  return `http://${host}:${port}`;
}
