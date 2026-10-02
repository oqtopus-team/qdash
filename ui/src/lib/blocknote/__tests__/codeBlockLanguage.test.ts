import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  collectCodeLanguageUpdates,
  useCodeBlockLanguageDetection,
  withDetectedCodeLanguages,
} from "../codeBlockLanguage";

function createMockEditor(document: Record<string, unknown>[]) {
  let onChangeCallback: (() => void) | null = null;
  const updateBlock = vi.fn(
    (id: string, update: { props: Record<string, unknown> }) => {
      const block = document.find((b) => b.id === id);
      if (block) {
        block.props = { ...(block.props as Record<string, unknown>), ...update.props };
      }
    },
  );
  const onChange = vi.fn((callback: () => void) => {
    onChangeCallback = callback;
    return () => {
      onChangeCallback = null;
    };
  });
  return {
    editor: { document, updateBlock, onChange } as unknown as Parameters<
      typeof useCodeBlockLanguageDetection
    >[0],
    updateBlock,
    onChange,
    triggerChange: () => onChangeCallback?.(),
  };
}

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

describe("collectCodeLanguageUpdates", () => {
  it("detects the language of a code block with no explicit language", () => {
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

    expect(collectCodeLanguageUpdates(blocks)).toEqual([{ id: "1", language: "python" }]);
  });

  it("detects the language of a code block explicitly set to text", () => {
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

    expect(collectCodeLanguageUpdates(blocks)).toEqual([{ id: "1", language: "sql" }]);
  });

  it("skips a code block with an explicit non-text language", () => {
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

    expect(collectCodeLanguageUpdates(blocks)).toEqual([]);
  });

  it("skips a text code block when detection is not confident", () => {
    const blocks = [codeBlock("1", "hello")];

    expect(collectCodeLanguageUpdates(blocks)).toEqual([]);
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

    expect(collectCodeLanguageUpdates(blocks)).toEqual([{ id: "2", language: "yaml" }]);
  });
});

describe("useCodeBlockLanguageDetection", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("applies the detected language after the debounce elapses", () => {
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
    const { editor, updateBlock, triggerChange } = createMockEditor(blocks);

    renderHook(() => useCodeBlockLanguageDetection(editor));
    triggerChange();

    expect(updateBlock).not.toHaveBeenCalled();

    vi.advanceTimersByTime(500);

    expect(updateBlock).toHaveBeenCalledWith("1", {
      type: "codeBlock",
      props: { language: "python" },
    });
  });

  it("does not update anything when no auto code blocks are detected", () => {
    const blocks = [codeBlock("1", "hello", "yaml")];
    const { editor, updateBlock, triggerChange } = createMockEditor(blocks);

    renderHook(() => useCodeBlockLanguageDetection(editor));
    triggerChange();
    vi.advanceTimersByTime(500);

    expect(updateBlock).not.toHaveBeenCalled();
  });

  it("clears the timer and unsubscribes on unmount", () => {
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
    const { editor, updateBlock, onChange, triggerChange } = createMockEditor(blocks);

    const { unmount } = renderHook(() => useCodeBlockLanguageDetection(editor));
    triggerChange();
    unmount();

    vi.advanceTimersByTime(500);

    expect(updateBlock).not.toHaveBeenCalled();
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});
