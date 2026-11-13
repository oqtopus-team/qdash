import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EvaluationPromptPreview } from "../EvaluationPromptPreview";

const { customInstance, projectState } = vi.hoisted(() => ({
  customInstance: vi.fn(),
  projectState: { canEdit: false },
}));
vi.mock("@/lib/api/custom-instance", () => ({ customInstance }));
vi.mock("@/contexts/ProjectContext", () => ({ useProject: () => projectState }));

const DRAFT = {
  draft_id: "ab".repeat(32),
  task_name: "CheckRabi",
  filename: "rabi.zip",
  uploaded_by: "alice",
  created_at: "2026-10-21T00:00:00Z",
  warnings: [],
  reference: { statuses: { SUCCESS: "ok" }, parameters: {} },
  example_count: 1,
  figure_count: 1,
};

const PREVIEW = {
  task_name: "CheckRabi",
  with_examples: false,
  model: "vllm/nvidia/Ising-Calibration",
  questions: [
    { key: "fit_reliability", prompt: "Assess whether the fit [figure] is reliable." },
    {
      key: "calibration_diagnosis",
      prompt: "Evaluate the image [figure] and determine the status.",
    },
  ],
  knowledge_chars: 988,
  knowledge_sha256: "ab".repeat(32),
  examples: [],
  examples_used: 0,
};

function renderPreview(exampleCount = 0) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <EvaluationPromptPreview taskName="CheckRabi" exampleCount={exampleCount} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  projectState.canEdit = false;
  customInstance.mockImplementation(
    async (config: { url: string; params?: Record<string, unknown> }) => ({
      data:
        config.url === "/evaluations/knowledge-drafts"
          ? DRAFT
          : config.params?.with_examples
            ? {
                ...PREVIEW,
                with_examples: true,
                examples: [
                  {
                    id: "e1",
                    title: "TLS",
                    outcome: "suboptimal",
                    status: "SHORT_T1",
                    figures: [],
                  },
                ],
                examples_used: 1,
              }
            : PREVIEW,
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("EvaluationPromptPreview", () => {
  it("builds the prompts on demand and shows one block per question", async () => {
    renderPreview();
    expect(customInstance).not.toHaveBeenCalled();
    expect(screen.getByText(/Press/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /preview/i }));

    await screen.findByText("fit_reliability");
    expect(customInstance).toHaveBeenCalledTimes(1);
    expect(customInstance.mock.calls[0][0]).toMatchObject({
      url: "/tasks/CheckRabi/evaluation-prompts",
      method: "GET",
      params: { with_examples: false },
    });
    expect(screen.getByText("Fit")).toBeTruthy();
    expect(screen.getByText("Diagnosis")).toBeTruthy();
    expect(screen.getByText("Assess whether the fit [figure] is reliable.")).toBeTruthy();
    expect(screen.getByText("vllm/nvidia/Ising-Calibration")).toBeTruthy();
    expect(screen.getByText("reference 988 chars")).toBeTruthy();
    expect(screen.getByText("zero-shot")).toBeTruthy();
    expect(screen.getByRole("button", { name: /refresh/i })).toBeTruthy();
  });

  it("disables in-context when the task has no examples, and requests it when it has", async () => {
    renderPreview(0);
    const inContext = screen.getByRole("button", { name: "In-context" });
    expect((inContext as HTMLButtonElement).disabled).toBe(true);
    cleanup();

    renderPreview(2);
    fireEvent.click(screen.getByRole("button", { name: /preview/i }));
    await screen.findByText("fit_reliability");
    fireEvent.click(screen.getByRole("button", { name: "In-context" }));

    await waitFor(() =>
      expect(customInstance.mock.lastCall?.[0]).toMatchObject({ params: { with_examples: true } }),
    );
    await screen.findByText("1 of 1 examples shown");
  });

  it("shows the API error", async () => {
    customInstance.mockRejectedValueOnce({
      response: { data: { detail: "evaluation: no reference" } },
    });
    renderPreview();
    fireEvent.click(screen.getByRole("button", { name: /preview/i }));
    await screen.findByText(/no reference/);
  });

  it("lets an editor build the prompts from a dropped knowledge draft", async () => {
    projectState.canEdit = true;
    renderPreview(0);
    const file = new File(["zip"], "rabi.zip", { type: "application/zip" });
    fireEvent.change(screen.getByTestId("knowledge-draft-input"), { target: { files: [file] } });
    await screen.findByTestId("knowledge-draft");
    // The draft has an example, so in-context is offered even though the shared task has none.
    expect((screen.getByRole("button", { name: "In-context" }) as HTMLButtonElement).disabled).toBe(
      false,
    );

    fireEvent.click(screen.getByRole("button", { name: /^preview$/i }));

    await screen.findByText("fit_reliability");
    expect(customInstance.mock.lastCall?.[0]).toMatchObject({
      url: "/tasks/CheckRabi/evaluation-prompts",
      params: { with_examples: false, knowledge_draft_id: "ab".repeat(32) },
    });
    expect(screen.getByText(/built from the draft/).textContent).toContain("rabi.zip");
  });

  it("offers no draft upload to viewers", () => {
    renderPreview();
    expect(screen.queryByTestId("knowledge-draft-input")).toBeNull();
  });
});
