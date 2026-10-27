import { describe, expect, it } from "vitest";

import type { ChipSystemInfo } from "@/schemas";

import { filterCouplingEntries, filterQubitEntries, systemQids } from "../systemQids";

const quel3: ChipSystemInfo = {
  system_id: "144Qv3-quel3",
  chip_id: "144Qv3",
  driver: "qubex",
  backend: "quel3",
  mux_ids: [0, 6],
  is_default: false,
  has_params: true,
  has_calib_note: true,
};

describe("systemQids", () => {
  it("expands MUX numbers with the topology MUX width", () => {
    expect([...systemQids(quel3, 2)]).toEqual(["0", "1", "2", "3", "24", "25", "26", "27"]);
  });

  it("filters qubit and coupling entries, keeping everything without a System", () => {
    const qids = systemQids(quel3, 2);
    const qubits = { "0": 1, "3": 2, "4": 3 };
    expect(filterQubitEntries(qubits, qids)).toEqual({ "0": 1, "3": 2 });
    expect(filterQubitEntries(qubits, null)).toBe(qubits);

    const couplings = { "0-1": 1, "3-4": 2, "24-25": 3 };
    expect(filterCouplingEntries(couplings, qids)).toEqual({ "0-1": 1, "24-25": 3 });
    expect(filterCouplingEntries(undefined, qids)).toBeUndefined();
  });
});
