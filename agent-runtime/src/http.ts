import { timingSafeEqual } from "node:crypto";

/** Safe client-facing failure raised while validating an HTTP request. */
export class RequestError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "RequestError";
  }
}

/** Read and parse a bounded JSON request body. */
export async function readJsonBody<T>(
  body: AsyncIterable<unknown>,
  maxBytes: number,
): Promise<T> {
  const chunks: Buffer[] = [];
  let bytes = 0;
  for await (const chunk of body) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk as Uint8Array);
    bytes += buffer.length;
    if (bytes > maxBytes) {
      throw new RequestError(413, "request body is too large");
    }
    chunks.push(buffer);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8")) as T;
  } catch {
    throw new RequestError(400, "request body must be valid JSON");
  }
}

/** Compare a bearer credential without leaking matching-prefix timing. */
export function hasBearerToken(authorization: string | undefined, token: string | undefined): boolean {
  if (!authorization?.startsWith("Bearer ") || !token) return false;
  const actual = Buffer.from(authorization.slice("Bearer ".length));
  const expected = Buffer.from(token);
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}
