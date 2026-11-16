/**
 * Returns a random UUID v4 for identifying one request.
 *
 * `crypto.randomUUID()` exists only in secure contexts (HTTPS or localhost),
 * so a UI served over plain HTTP builds the UUID from `crypto.getRandomValues()`,
 * which every context provides.
 */
export function createRequestId(): string {
  const { crypto } = globalThis;
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();

  const bytes = crypto.getRandomValues(new Uint8Array(16));
  // RFC 9562: version 4 in the high nibble of byte 6, variant 10xx in byte 8.
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
