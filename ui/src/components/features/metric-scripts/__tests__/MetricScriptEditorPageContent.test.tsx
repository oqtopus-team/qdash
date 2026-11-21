import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PageContextProvider } from "@/contexts/ChatDockContext";

import { MetricScriptEditorPageContent } from "../MetricScriptEditorPageContent";
import { evaluateResponse, qubitCell } from "./fixtures";
import { scriptResponse, SOURCE } from "./scriptFixtures";

const mocks = vi.hoisted(() => ({
  script: null as unknown,
  editor: {
    revealLineInCenter: vi.fn(),
    setPosition: vi.fn(),
    focus: vi.fn(),
    getModel: () => ({ id: "model" }),
  },
  setModelMarkers: vi.fn(),
  editorMounted: vi.fn(),
  validate: vi.fn(),
  validateResult: null as unknown,
  draftEvaluate: vi.fn(),
  previewResult: null as unknown,
  mutateAsync: vi.fn(),
  provider: null as PageContextProvider | null,
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("next/dynamic", () => ({
  default: () =>
    /** Monaco stand-in: a text area that hands the editor handles to onMount. */
    function MockEditor({
      value,
      onChange,
      onMount,
      options,
    }: {
      value?: string;
      onChange?: (value?: string) => void;
      onMount?: (editor: unknown, monaco: unknown) => void;
      options?: { readOnly?: boolean };
    }) {
      useEffect(() => {
        mocks.editorMounted();
      }, []);
      useEffect(() => {
        onMount?.(mocks.editor, {
          editor: { remeasureFonts: () => undefined, setModelMarkers: mocks.setModelMarkers },
          MarkerSeverity: { Error: 8 },
        });
      }, [onMount]);
      return (
        <textarea
          aria-label="Code"
          value={value ?? ""}
          readOnly={options?.readOnly}
          onChange={(event) => onChange?.(event.target.value)}
        />
      );
    },
}));

vi.mock("react-resizable-panels", () => ({
  Panel: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Group: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Separator: () => <div />,
}));

vi.mock("@/client/metric-script/metric-script", async () => {
  const { useState } = await import("react");
  const idle = () => ({ mutate: vi.fn(), isPending: false, data: undefined, error: null });
  return {
    getGetMetricScriptQueryKey: (id: string) => [`/metric-scripts/${id}`],
    getListMetricScriptsQueryKey: () => ["/metric-scripts"],
    useGetMetricScript: () => ({
      data: mocks.script ? { data: mocks.script } : undefined,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    }),
    useUpdateMetricScript: () => ({ mutateAsync: mocks.mutateAsync, isPending: false }),
    useValidateMetricScript: () => ({
      isPending: false,
      mutate: (
        variables: unknown,
        options: { onSuccess: (response: { data: unknown }) => void },
      ) => {
        mocks.validate(variables);
        options.onSuccess({ data: mocks.validateResult });
      },
    }),
    useEvaluateMetricScriptDraft: () => {
      const [data, setData] = useState<{ data: unknown } | undefined>(undefined);
      return {
        isPending: false,
        error: null,
        data,
        mutate: (variables: unknown) => {
          mocks.draftEvaluate(variables);
          setData({ data: mocks.previewResult });
        },
      };
    },
    useEvaluateMetricScript: idle,
    useCopyMetricScript: idle,
  };
});

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({
    data: { data: { chips: [{ chip_id: "chip-1", installed_at: "2026-06-01T00:00:00Z" }] } },
  }),
  useGetChip: () => ({ data: { data: { chip_id: "chip-1", topology_id: "topo" } } }),
}));

vi.mock("@/components/selectors/ChipSelector", () => ({
  ChipSelector: ({ selectedChip }: { selectedChip: string }) => (
    <div data-testid="chip-selector">{selectedChip}</div>
  ),
}));

vi.mock("@/hooks/useTopologyConfig", async () => {
  const { TOPOLOGY: topology } = await import("./fixtures");
  return { useTopologyConfig: () => topology };
});
vi.mock("@/hooks/useMetricsConfig", () => ({
  useMetricsConfig: () => ({ colorScale: { colors: ["#000000", "#ffffff"] } }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: "project-1", canEdit: true }),
}));

vi.mock("@/contexts/ChatDockContext", () => ({
  useChatDock: () => ({
    registerPage: (provider: PageContextProvider) => {
      mocks.provider = provider;
      return () => undefined;
    },
    refreshPage: () => undefined,
  }),
}));

vi.mock("@/components/ui/Toast", () => ({ useToast: () => mocks.toast }));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MetricScriptEditorPageContent scriptId="ms_000000000001" />
    </QueryClientProvider>,
  );
}

describe("MetricScriptEditorPageContent", () => {
  beforeEach(() => {
    mocks.script = scriptResponse();
    mocks.provider = null;
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("loads the script with its saved and active revisions", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByLabelText("Code")).toHaveValue(SOURCE));
    expect(screen.getByRole("heading", { name: "Coherence" })).toBeInTheDocument();
    const status = screen.getByTestId("script-status");
    expect(status).toHaveTextContent("Saved r3");
    expect(status).toHaveTextContent("Active r3");
    expect(status).not.toHaveTextContent("Unsaved changes");
    expect(screen.getByLabelText("Name")).toHaveValue("Coherence");
  });

  it("explains which revision dashboards use when the saved text is invalid", async () => {
    mocks.script = scriptResponse({
      status: "invalid",
      revision: 4,
      active_revision: 3,
      diagnostics: [{ message: "NameError: name 'x' is not defined", line: 6 }],
    });
    renderPage();

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Revision r4 has errors. Dashboards keep using r3",
    );
    expect(screen.getByTestId("diagnostics")).toHaveTextContent("NameError");
  });

  it("validates the draft and jumps to a diagnostic's line", async () => {
    mocks.validateResult = {
      ok: false,
      metrics: [],
      diagnostics: [{ message: "SyntaxError: invalid syntax", line: 4, column: 5 }],
    };
    renderPage();
    await waitFor(() => expect(screen.getByLabelText("Code")).toHaveValue(SOURCE));

    fireEvent.change(screen.getByLabelText("Code"), { target: { value: "def broken(:\n" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));

    expect(mocks.validate).toHaveBeenCalledWith({ data: { source: "def broken(:\n" } });
    expect(screen.getByTestId("diagnostics")).toHaveTextContent("SyntaxError: invalid syntax");
    expect(mocks.setModelMarkers).toHaveBeenLastCalledWith({ id: "model" }, "metric-script", [
      expect.objectContaining({ startLineNumber: 4, startColumn: 5, severity: 8 }),
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Line 4:5" }));
    expect(mocks.editor.revealLineInCenter).toHaveBeenCalledWith(4);
    expect(mocks.editor.setPosition).toHaveBeenCalledWith({ lineNumber: 4, column: 5 });
  });

  it("previews the draft on the chosen chip and renders the result", async () => {
    mocks.previewResult = evaluateResponse("qubit", [qubitCell("0", { value: 42 })]);
    renderPage();
    await waitFor(() => expect(screen.getByLabelText("Code")).toHaveValue(SOURCE));

    expect(screen.getByTestId("chip-selector")).toHaveTextContent("chip-1");
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    expect(mocks.draftEvaluate).toHaveBeenCalledWith({
      data: {
        metric_id: "t1",
        chip_id: "chip-1",
        period: { kind: "relative", days: 14 },
        params: {},
        source: SOURCE,
      },
    });
    expect(await screen.findByTestId("qubit-map")).toBeInTheDocument();
    expect(screen.getByTestId("metric-qubit-0").nextSibling?.nextSibling).toHaveTextContent("42");
  });

  it("registers the editor with the chat and applies a proposed edit to the draft", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByLabelText("Code")).toHaveValue(SOURCE));

    expect(mocks.provider?.current()).toEqual({
      path: "/dashboards/scripts/ms_000000000001",
      title: "Metric script: Coherence",
      metricScript: { scriptId: "ms_000000000001", name: "Coherence", code: SOURCE, dirty: false },
    });

    act(() => mocks.provider?.applyCode?.("# proposed\n"));

    expect(screen.getByLabelText("Code")).toHaveValue("# proposed\n");
    expect(screen.getByTestId("script-status")).toHaveTextContent("Unsaved changes");
    expect(mocks.provider?.current()?.metricScript).toEqual(
      expect.objectContaining({ code: "# proposed\n", dirty: true }),
    );
  });

  it("saves with Cmd/Ctrl+S", async () => {
    mocks.mutateAsync.mockResolvedValue({ data: scriptResponse({ revision: 4 }) });
    renderPage();
    await waitFor(() => expect(screen.getByLabelText("Code")).toHaveValue(SOURCE));

    fireEvent.change(screen.getByLabelText("Code"), { target: { value: `${SOURCE}# more\n` } });
    await act(async () => {
      fireEvent.keyDown(window, { key: "s", metaKey: true });
    });

    expect(mocks.mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        scriptId: "ms_000000000001",
        data: expect.objectContaining({ source: `${SOURCE}# more\n`, expected_revision: 3 }),
      }),
    );
  });

  describe("on a narrow screen", () => {
    const originalMatchMedia = window.matchMedia;
    // The code tab panel is also labelled "Code"; the editor stand-in is the text box.
    const codeBox = () => screen.getByRole("textbox", { name: "Code", hidden: true });

    beforeEach(() => {
      window.matchMedia = (query: string) =>
        ({
          ...originalMatchMedia(query),
          matches: query === "(max-width: 767px)",
        }) as MediaQueryList;
    });

    afterEach(() => {
      window.matchMedia = originalMatchMedia;
    });

    it("switches between the code and the settings without losing the draft", async () => {
      renderPage();
      await waitFor(() => expect(codeBox()).toHaveValue(SOURCE));

      const codeTab = screen.getByRole("tab", { name: "Code" });
      const detailsTab = screen.getByRole("tab", { name: "Settings & preview" });
      expect(codeTab).toHaveAttribute("aria-selected", "true");
      expect(codeBox()).toBeVisible();
      expect(screen.getByLabelText("Name")).not.toBeVisible();

      fireEvent.change(codeBox(), { target: { value: `${SOURCE}# more\n` } });
      fireEvent.click(detailsTab);
      expect(detailsTab).toHaveAttribute("aria-selected", "true");
      expect(screen.getByLabelText("Name")).toBeVisible();
      fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Coherence v2" } });

      fireEvent.click(codeTab);
      expect(codeBox()).toBeVisible();
      expect(codeBox()).toHaveValue(`${SOURCE}# more\n`);
      expect(screen.getByLabelText("Name")).toHaveValue("Coherence v2");
      // One editor instance for the whole session: switching panes does not remount it.
      expect(mocks.editorMounted).toHaveBeenCalledTimes(1);
    });

    it("opens the settings pane for a link to #metric-script-settings", async () => {
      const scrollIntoView = vi.spyOn(HTMLElement.prototype, "scrollIntoView");
      window.history.replaceState(null, "", "/#metric-script-settings");
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole("tab", { name: "Settings & preview" })).toHaveAttribute(
          "aria-selected",
          "true",
        ),
      );
      expect(screen.getByLabelText("Name")).toBeVisible();
      expect(codeBox()).not.toBeVisible();
      await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
      expect(scrollIntoView.mock.contexts[0]).toHaveAttribute("id", "metric-script-settings");
    });

    it("shows the code when a diagnostic's line is chosen", async () => {
      mocks.script = scriptResponse({
        status: "invalid",
        revision: 4,
        active_revision: 3,
        diagnostics: [{ message: "NameError: name 'x' is not defined", line: 6 }],
      });
      renderPage();
      await waitFor(() => expect(codeBox()).toHaveValue(SOURCE));

      fireEvent.click(screen.getByRole("tab", { name: "Settings & preview" }));
      fireEvent.click(screen.getByRole("button", { name: /Line 6/ }));

      expect(screen.getByRole("tab", { name: "Code" })).toHaveAttribute("aria-selected", "true");
      expect(codeBox()).toBeVisible();
      await waitFor(() => expect(mocks.editor.revealLineInCenter).toHaveBeenCalledWith(6));
    });
  });
});
