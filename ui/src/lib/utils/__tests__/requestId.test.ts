import { afterEach, describe, expect, it, vi } from "vitest";

import { createRequestId } from "../requestId";

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const realCrypto = globalThis.crypto;

/** A crypto object as a plain-HTTP page sees it: no randomUUID. */
function insecureContextCrypto(getRandomValues = realCrypto.getRandomValues.bind(realCrypto)) {
  return { getRandomValues } as unknown as Crypto;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("createRequestId", () => {
  it("uses the native randomUUID when the context provides it", () => {
    const randomUUID = vi.fn(() => "11111111-2222-4333-8444-555555555555" as const);
    vi.stubGlobal("crypto", { randomUUID, getRandomValues: vi.fn() });

    expect(createRequestId()).toBe("11111111-2222-4333-8444-555555555555");
    expect(randomUUID).toHaveBeenCalledTimes(1);
  });

  it("builds a UUID v4 from getRandomValues when randomUUID is unavailable", () => {
    const getRandomValues = vi.fn(<T extends ArrayBufferView | null>(array: T): T => {
      (array as unknown as Uint8Array).fill(0xff);
      return array;
    });
    vi.stubGlobal("crypto", insecureContextCrypto(getRandomValues));
    const mathRandom = vi.spyOn(Math, "random");

    // All-ones input shows the version and variant bits are forced.
    expect(createRequestId()).toBe("ffffffff-ffff-4fff-bfff-ffffffffffff");
    expect(getRandomValues).toHaveBeenCalledTimes(1);
    expect(mathRandom).not.toHaveBeenCalled();
  });

  it("keeps the random bytes in order and sets the version and variant bits", () => {
    vi.stubGlobal(
      "crypto",
      insecureContextCrypto(<T extends ArrayBufferView | null>(array: T): T => {
        (array as unknown as Uint8Array).set([
          0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x06, 0x77, 0x08, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee,
          0xff,
        ]);
        return array;
      }),
    );

    expect(createRequestId()).toBe("00112233-4455-4677-8899-aabbccddeeff");
  });

  it("returns distinct well-formed IDs on the fallback path", () => {
    vi.stubGlobal("crypto", insecureContextCrypto());

    const ids = Array.from({ length: 50 }, createRequestId);
    for (const id of ids) expect(id).toMatch(UUID_V4);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
