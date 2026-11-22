import assert from "node:assert/strict";

/** Zones east and west of UTC: under either, `new Date(naive)` names the wrong instant. */
export const NON_UTC_ZONES = ["Asia/Tokyo", "America/New_York"];

/** Run `body` (sync or async) with the process time zone set to `zone`, and check the zone took effect. */
export async function inZone(zone, body) {
  const previous = process.env.TZ;
  process.env.TZ = zone;
  try {
    // The host reads a naive value as local time; if it read UTC, the zone was not applied.
    assert.notEqual(new Date("2026-11-22T02:53:20").getTime(), Date.UTC(2026, 10, 22, 2, 53, 20), `TZ=${zone} not applied`);
    return await body();
  } finally {
    if (previous === undefined) delete process.env.TZ;
    else process.env.TZ = previous;
  }
}
