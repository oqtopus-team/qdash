import { describe, expect, it } from "vitest";

import { withDetectedCodeLanguages } from "../codeBlockLanguage";

function textContent(text: string) {
  return [{ type: "text", text, styles: {} }];
}

function codeBlock(
  id: string,
  text: string,
  language?: string,
  children: Record<string, unknown>[] = [],
) {
  return {
    id,
    type: "codeBlock",
    props: language === undefined ? {} : { language },
    content: textContent(text),
    children,
  };
}

function paragraph(id: string, text: string, children: Record<string, unknown>[] = []) {
  return {
    id,
    type: "paragraph",
    props: {},
    content: textContent(text),
    children,
  };
}

describe("withDetectedCodeLanguages", () => {
  it("fills in the language of a code block with no explicit language", () => {
    const blocks = [
      codeBlock(
        "1",
        `import numpy as np

def calibrate(qubit_id: str, shots: int = 1000) -> float:
    for i in range(shots):
        result = np.mean(i)
    print(f"calibrated {qubit_id}")
    return result
`,
      ),
    ];

    const result = withDetectedCodeLanguages(blocks);

    expect((result[0].props as Record<string, unknown>).language).toBe("python");
  });

  it("fills in the language of a code block explicitly set to text", () => {
    const blocks = [
      codeBlock(
        "1",
        `SELECT chip_id, avg(t1)
FROM calibration_results
WHERE created_at > '2026-01-01'
GROUP BY chip_id;
`,
        "text",
      ),
    ];

    const result = withDetectedCodeLanguages(blocks);

    expect((result[0].props as Record<string, unknown>).language).toBe("sql");
  });

  it("leaves a code block with an explicit non-text language unchanged", () => {
    const blocks = [
      codeBlock(
        "1",
        `SELECT chip_id, avg(t1)
FROM calibration_results
WHERE created_at > '2026-01-01'
GROUP BY chip_id;
`,
        "yaml",
      ),
    ];

    const result = withDetectedCodeLanguages(blocks);

    expect((result[0].props as Record<string, unknown>).language).toBe("yaml");
  });

  it("leaves a text code block unchanged when detection is not confident", () => {
    const blocks = [codeBlock("1", "hello")];

    const result = withDetectedCodeLanguages(blocks);

    expect((result[0].props as Record<string, unknown>).language).toBeUndefined();
  });

  it("recurses into nested children", () => {
    const nestedCode = codeBlock(
      "2",
      `chip:
  id: chip-64
  qubits:
    - id: 1
      t1: 12.3
    - id: 2
      t1: 15.1
`,
    );
    const blocks = [paragraph("1", "see below", [nestedCode])];

    const result = withDetectedCodeLanguages(blocks);

    const child = (result[0].children as Record<string, unknown>[])[0];
    expect((child.props as Record<string, unknown>).language).toBe("yaml");
  });

  it("does not mutate its input", () => {
    const original = [
      codeBlock(
        "1",
        `import numpy as np

def calibrate(qubit_id: str, shots: int = 1000) -> float:
    for i in range(shots):
        result = np.mean(i)
    print(f"calibrated {qubit_id}")
    return result
`,
      ),
    ];
    const snapshot = JSON.parse(JSON.stringify(original));

    const result = withDetectedCodeLanguages(original);

    expect(original).toEqual(snapshot);
    expect(result).not.toBe(original);
    expect(result[0]).not.toBe(original[0]);
  });
});
