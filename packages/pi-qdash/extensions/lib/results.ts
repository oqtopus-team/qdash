export function redact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => {
        if (/token|password|secret|authorization|api[_-]?key/i.test(key)) return [key, "[redacted]"];
        return [key, redact(item)];
      }),
    );
  }
  return value;
}

export function toToolResult(data: unknown, details: Record<string, unknown> = {}) {
  const safeData = redact(data);
  let text = JSON.stringify(safeData, null, 2);
  if (text.length > 20_000) text = `${text.slice(0, 20_000)}\n... [truncated]`;
  return {
    content: [{ type: "text" as const, text }],
    details: { ...details, data: safeData },
  };
}

export function toTextToolResult(text: string, data: unknown, details: Record<string, unknown> = {}) {
  const safeData = redact(data);
  return {
    content: [{ type: "text" as const, text }],
    details: { ...details, data: safeData },
  };
}

/**
 * Result of a tool that fetched a figure: the text summary plus, for an image,
 * the image itself as model-visible content. Without the image block a
 * vision model only reads that a figure exists; with it, it can judge the
 * curve. Non-image figures (JSON) keep a text-only result.
 */
export function toFigureToolResult(
  text: string,
  figure: { base64?: string; mediaType: string },
  data: unknown,
  details: Record<string, unknown> = {},
) {
  const result = toTextToolResult(text, data, details);
  if (!figure.base64 || !figure.mediaType.startsWith("image/")) return result;
  return {
    ...result,
    content: [
      ...result.content,
      { type: "image" as const, data: figure.base64, mimeType: figure.mediaType },
    ],
  };
}
