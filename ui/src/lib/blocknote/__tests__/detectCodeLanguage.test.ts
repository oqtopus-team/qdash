import { describe, expect, it } from "vitest";

import { detectCodeLanguage } from "../detectCodeLanguage";

describe("detectCodeLanguage", () => {
  it("detects python", () => {
    const code = `import numpy as np

def calibrate(qubit_id: str, shots: int = 1000) -> float:
    for i in range(shots):
        result = np.mean(i)
    print(f"calibrated {qubit_id}")
    return result
`;
    expect(detectCodeLanguage(code)).toBe("python");
  });

  it("detects bash as shellscript", () => {
    const code = `#!/bin/bash
cd /workspace/qdash
export PREFECT_API_URL="http://localhost:4200/api"
cat config.yaml | grep chip_id | head -n 5
`;
    expect(detectCodeLanguage(code)).toBe("shellscript");
  });

  it("detects json", () => {
    const code = `{
  "chip_id": "chip-64",
  "qubits": [1, 2, 3],
  "params": {"t1": 12.3, "t2": 45.6}
}`;
    expect(detectCodeLanguage(code)).toBe("json");
  });

  it("detects a json array", () => {
    expect(detectCodeLanguage('[1, 2, {"id": "q0"}]')).toBe("json");
  });

  it("detects yaml", () => {
    const code = `chip:
  id: chip-64
  qubits:
    - id: 1
      t1: 12.3
    - id: 2
      t1: 15.1
`;
    expect(detectCodeLanguage(code)).toBe("yaml");
  });

  it("detects sql", () => {
    const code = `SELECT chip_id, avg(t1)
FROM calibration_results
WHERE created_at > '2026-01-01'
GROUP BY chip_id;
`;
    expect(detectCodeLanguage(code)).toBe("sql");
  });

  it("detects typescript", () => {
    const code = `interface ChipSummary {
  chipId: string;
  qubitCount: number;
}

function summarize(chip: ChipSummary): string {
  return \`\${chip.chipId}: \${chip.qubitCount} qubits\`;
}
`;
    expect(detectCodeLanguage(code)).toBe("typescript");
  });

  it("returns null for an empty string", () => {
    expect(detectCodeLanguage("")).toBeNull();
    expect(detectCodeLanguage("   \n  ")).toBeNull();
  });

  it("returns null for a single word", () => {
    expect(detectCodeLanguage("hello")).toBeNull();
  });

  it("returns null for an English sentence", () => {
    expect(
      detectCodeLanguage("This is just a plain English sentence describing something."),
    ).toBeNull();
  });

  it("detects a short python snippet that clearly beats the runner-up", () => {
    expect(detectCodeLanguage('import request\n\nprint("hello")')).toBe("python");
  });

  it("returns null when the top two languages tie", () => {
    expect(detectCodeLanguage('print("hello")')).toBeNull();
    expect(detectCodeLanguage("import numpy as np")).toBeNull();
  });

  it("returns null for two unrelated words", () => {
    expect(detectCodeLanguage("hello world")).toBeNull();
  });

  it("returns null for a note-like sentence with low relevance", () => {
    expect(detectCodeLanguage("This is a note about calibration results.")).toBeNull();
  });

  it("detects a short bash snippet as shellscript", () => {
    expect(detectCodeLanguage("ls -la\ncd /tmp")).toBe("shellscript");
  });
});
