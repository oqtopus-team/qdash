import { describe, expect, it } from "vitest";
import { matchSkills, skillInvocation, skillQuery } from "../chatSkills";

const skills = [
  { name: "qdash", description: "Query a running QDash instance." },
  { name: "qdash-characterization", description: "Remeasure T1 and T2 of named qubits." },
  { name: "qdash-one-qubit-calibration", description: "Calibrate single qubits." },
  { name: "qcaleval", description: "Evaluate calibration plots." },
];

describe("skillQuery", () => {
  it("reads the name typed after a leading slash, with or without skill:", () => {
    expect(skillQuery("/")).toBe("");
    expect(skillQuery("/cal")).toBe("cal");
    expect(skillQuery("/skill:")).toBe("");
    expect(skillQuery("/skill:qdash-ch")).toBe("qdash-ch");
  });

  it("is null once arguments start or when the slash is not at the start", () => {
    expect(skillQuery("/skill:qdash ")).toBeNull();
    expect(skillQuery("/cal\n")).toBeNull();
    expect(skillQuery(" /cal")).toBeNull();
    expect(skillQuery("see /cal")).toBeNull();
    expect(skillQuery("")).toBeNull();
  });
});

describe("matchSkills", () => {
  it("lists every skill for an empty query", () => {
    expect(matchSkills(skills, "")).toEqual(skills);
  });

  it("ranks name prefixes, then names containing the query, then descriptions", () => {
    expect(matchSkills(skills, "QC").map((s) => s.name)).toEqual(["qcaleval"]);
    expect(matchSkills(skills, "cal").map((s) => s.name)).toEqual([
      "qdash-one-qubit-calibration",
      "qcaleval",
    ]);
    const ranked = [
      { name: "plot", description: "Calibration plots." },
      { name: "x-cal" },
      { name: "cal-x" },
    ];
    expect(matchSkills(ranked, "cal").map((s) => s.name)).toEqual(["cal-x", "x-cal", "plot"]);
    expect(matchSkills(skills, "t1").map((s) => s.name)).toEqual(["qdash-characterization"]);
    expect(matchSkills(skills, "nothing")).toEqual([]);
  });

  it("tolerates a skill without a description", () => {
    expect(matchSkills([{ name: "bare" }], "x")).toEqual([]);
  });
});

describe("skillInvocation", () => {
  it("spells the pi command and leaves room for arguments", () => {
    expect(skillInvocation("qdash-characterization")).toBe("/skill:qdash-characterization ");
  });
});
