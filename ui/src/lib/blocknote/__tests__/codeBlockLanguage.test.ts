import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  changedCodeBlockIds,
  useCodeBlockLanguageDetection,
  withDetectedCodeLanguages,
} from "../codeBlockLanguage";

type Change = {
  type: "insert" | "delete" | "update" | "move";
  block: Record<string, unknown>;
  prevBlock?: Record<string, unknown>;
};
type OnChangeCallback = (editor: unknown, context: { getChanges: () => Change[] }) => void;

function createMockEditor(document: Record<string, unknown>[]) {
  let onChangeCallback: OnChangeCallback | null = null;
  const updateBlock = vi.fn((id: string, update: { props: Record<string, unknown> }) => {
    const block = document.find((b) => b.id === id);
    if (block) {
      block.props = { ...(block.props as Record<string, unknown>), ...update.props };
    }
  });
  const getBlock = vi.fn((id: string) => document.find((b) => b.id === id));
  const onChange = vi.fn((callback: OnChangeCallback) => {
    onChangeCallback = callback;
    return () => {
      onChangeCallback = null;
    };
  });
  const editor = { document, updateBlock, getBlock, onChange } as unknown as Parameters<
    typeof useCodeBlockLanguageDetection
  >[0];
  return {
    editor,
    updateBlock,
    getBlock,
    onChange,
    triggerChange: (changes: Change[]) => onChangeCallback?.(editor, { getChanges: () => changes }),
  };
}

function insertChange(block: Record<string, unknown>): Change {
  return { type: "insert", block };
}

function updateChange(block: Record<string, unknown>, prevBlock: Record<string, unknown>): Change {
  return { type: "update", block, prevBlock };
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

  it("fills in the language of a code block explicitly set to an empty string", () => {
    const blocks = [
      codeBlock(
        "1",
        `SELECT chip_id, avg(t1)
FROM calibration_results
WHERE created_at > '2026-01-01'
GROUP BY chip_id;
`,
        "",
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

describe("changedCodeBlockIds", () => {
  it("includes an inserted code block", () => {
    const block = codeBlock("1", "print('hi')");

    expect(changedCodeBlockIds([insertChange(block)])).toEqual(["1"]);
  });

  it("excludes an inserted block that is not a code block", () => {
    const block = paragraph("1", "hello");

    expect(changedCodeBlockIds([insertChange(block)])).toEqual([]);
  });

  it("includes a code block whose text changed", () => {
    const prevBlock = codeBlock("1", "print('h");
    const block = codeBlock("1", "print('hi')");

    expect(changedCodeBlockIds([updateChange(block, prevBlock)])).toEqual(["1"]);
  });

  it("excludes a code block update where only props changed", () => {
    const prevBlock = codeBlock("1", "print('hi')", "python");
    const block = codeBlock("1", "print('hi')", "text");

    expect(changedCodeBlockIds([updateChange(block, prevBlock)])).toEqual([]);
  });

  it("excludes a deleted code block", () => {
    const block = codeBlock("1", "print('hi')");

    expect(changedCodeBlockIds([{ type: "delete", block }])).toEqual([]);
  });

  it("excludes a moved code block", () => {
    const prevBlock = codeBlock("1", "print('hi')");
    const block = codeBlock("1", "print('hi')");

    expect(changedCodeBlockIds([{ type: "move", block, prevBlock }])).toEqual([]);
  });

  it("excludes a non-code-block text update", () => {
    const prevBlock = paragraph("1", "hello");
    const block = paragraph("1", "hello world");

    expect(changedCodeBlockIds([updateChange(block, prevBlock)])).toEqual([]);
  });
});

describe("useCodeBlockLanguageDetection", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const PYTHON_CODE = `import numpy as np

def calibrate(qubit_id: str, shots: int = 1000) -> float:
    for i in range(shots):
        result = np.mean(i)
    print(f"calibrated {qubit_id}")
    return result
`;

  it("detects the language of an edited auto code block after the debounce elapses", () => {
    const block = codeBlock("1", PYTHON_CODE);
    const prevBlock = codeBlock("1", "import numpy as np");
    const blocks = [block];
    const { editor, updateBlock, triggerChange } = createMockEditor(blocks);

    renderHook(() => useCodeBlockLanguageDetection(editor));
    triggerChange([updateChange(block, prevBlock)]);

    expect(updateBlock).not.toHaveBeenCalled();

    vi.advanceTimersByTime(500);

    expect(updateBlock).toHaveBeenCalledWith("1", {
      type: "codeBlock",
      props: { language: "python" },
    });
  });

  it("detects the language of an inserted code block", () => {
    const block = codeBlock("1", PYTHON_CODE);
    const blocks = [block];
    const { editor, updateBlock, triggerChange } = createMockEditor(blocks);

    renderHook(() => useCodeBlockLanguageDetection(editor));
    triggerChange([insertChange(block)]);
    vi.advanceTimersByTime(500);

    expect(updateBlock).toHaveBeenCalledWith("1", {
      type: "codeBlock",
      props: { language: "python" },
    });
  });

  it("does not re-detect a prop-only update, such as choosing Plain Text", () => {
    const prevBlock = codeBlock("1", PYTHON_CODE, "python");
    const block = codeBlock("1", PYTHON_CODE, "text");
    const blocks = [block];
    const { editor, updateBlock, triggerChange } = createMockEditor(blocks);

    renderHook(() => useCodeBlockLanguageDetection(editor));
    triggerChange([updateChange(block, prevBlock)]);
    vi.advanceTimersByTime(500);

    expect(updateBlock).not.toHaveBeenCalled();
  });

  it("does not update a code block that already has an explicit non-auto language", () => {
    const prevBlock = codeBlock("1", "hello", "yaml");
    const block = codeBlock("1", "hello world", "yaml");
    const blocks = [block];
    const { editor, updateBlock, triggerChange } = createMockEditor(blocks);

    renderHook(() => useCodeBlockLanguageDetection(editor));
    triggerChange([updateChange(block, prevBlock)]);
    vi.advanceTimersByTime(500);

    expect(updateBlock).not.toHaveBeenCalled();
  });

  it("clears the timer and unsubscribes on unmount", () => {
    const block = codeBlock("1", PYTHON_CODE);
    const blocks = [block];
    const { editor, updateBlock, onChange, triggerChange } = createMockEditor(blocks);

    const { unmount } = renderHook(() => useCodeBlockLanguageDetection(editor));
    triggerChange([insertChange(block)]);
    unmount();

    vi.advanceTimersByTime(500);

    expect(updateBlock).not.toHaveBeenCalled();
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});
