import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import type { AxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useFirstCalibrationJourney } from "@/components/features/first-calibration/useFirstCalibrationJourney";
import { useFirstCalibrationProgress } from "@/components/features/first-calibration/useFirstCalibrationProgress";
import { useRecordJourneyResultView } from "@/components/features/first-calibration/useRecordJourneyResultView";

import { PROJECT_STORAGE_KEY, deferred, storeJourney, storedJourney } from "./journeyTestUtils";

type Answer = { data: unknown };

const api = vi.hoisted(() => ({
  projectId: "project-1",
  /** While set, every request of project-2 waits for it. */
  gate: null as Promise<void> | null,
  requests: [] as { project: string | null; url: string }[],
}));

const FAKE_SOURCES = {
  available: true,
  sources: [],
  deployment_backend: "fake",
  presets: [
    {
      preset_id: "fake",
      name: "Virtual fake device",
      description: "",
      topology_id: "square-lattice-mux-64",
      n_qubits: 64,
      mux_count: 16,
      workflow_template_id: "fake_calibration",
    },
  ],
};

/**
 * Both projects hold a chip, flow and execution with the same ids; only their state differs.
 * Project 1's run finished with a result, project 2's run is still going.
 */
function answer(project: string | null, url: string): unknown {
  if (url === "/chips") return { chips: [{ chip_id: "chip-a", size: 64 }] };
  if (url === "/chips/config-sources") return FAKE_SOURCES;
  if (url === "/flows/first_calibration") return { name: "first_calibration", chip_id: "chip-a" };
  if (url === "/executions/20261105-001") {
    return project === "project-1"
      ? {
          execution_id: "20261105-001",
          chip_id: "chip-a",
          status: "completed",
          task: [
            {
              task_id: "t1",
              name: "CheckT1",
              status: "completed",
              qid: "0",
              figure_path: ["a"],
            },
          ],
        }
      : {
          execution_id: "20261105-001",
          chip_id: "chip-a",
          status: "running",
          task: [{ task_id: "t2", name: "CheckT1", status: "running", qid: "0" }],
        };
  }
  throw new Error(`Unexpected request ${url}`);
}

// The real generated hooks run; only the HTTP call is replaced. Like the real axios
// interceptor, it reads the project header from storage when the request is sent.
vi.mock("@/lib/api/custom-instance", () => ({
  customInstance: async (config: AxiosRequestConfig): Promise<Answer> => {
    const project = window.localStorage.getItem("qdash_current_project_id");
    const url = config.url ?? "";
    api.requests.push({ project, url });
    if (project === "project-2" && api.gate) await api.gate;
    return { data: answer(project, url) };
  },
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ username: "alice" }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: api.projectId, canEdit: true }),
}));

const seen: {
  project: string;
  stage: string | null;
  pending: boolean | null;
}[] = [];

function Probe() {
  const { state } = useFirstCalibrationJourney();
  const { progress } = useFirstCalibrationProgress(state);
  seen.push({
    project: api.projectId,
    stage: progress?.stage ?? null,
    pending: progress?.pending ?? null,
  });
  return <p data-testid="stage">{progress ? `${progress.stage}` : "none"}</p>;
}

function ResultViewer({ taskId }: { taskId: string }) {
  useRecordJourneyResultView({
    task_id: taskId,
    execution_id: "20261105-001",
    status: "completed",
  });
  return null;
}

function setup(children: () => React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  // Fresh elements on every render, so a rerender reaches the hooks like a context change does.
  const tree = () => <QueryClientProvider client={client}>{children()}</QueryClientProvider>;
  const view = render(tree());
  return {
    client,
    rerender: () => view.rerender(tree()),
    /** What ProjectContext does on a switch: storage first, then state, then invalidation. */
    switchTo: async (projectId: string) => {
      window.localStorage.setItem(PROJECT_STORAGE_KEY, projectId);
      api.projectId = projectId;
      await act(async () => {
        view.rerender(tree());
        void client.invalidateQueries();
      });
    },
  };
}

describe("first calibration progress across a project switch", () => {
  beforeEach(() => {
    api.projectId = "project-1";
    api.gate = null;
    api.requests = [];
    seen.length = 0;
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "project-1");
    const sameIds = {
      chipId: "chip-a",
      flowName: "first_calibration",
      executionId: "20261105-001",
    };
    storeJourney("project-1", sameIds);
    storeJourney("project-2", sameIds);
  });

  afterEach(() => {
    cleanup();
    window.localStorage.clear();
  });

  it("never shows the old project's records as the new project's progress", async () => {
    const view = setup(() => <Probe />);
    await waitFor(() => expect(screen.getByTestId("stage").textContent).toBe("results"));

    const release = deferred<void>();
    api.gate = release.promise;
    await view.switchTo("project-2");

    // Project 2 has not answered yet: its journey waits instead of reading project 1's cache.
    const afterSwitch = () => seen.filter((entry) => entry.project === "project-2");
    expect(afterSwitch().length).toBeGreaterThan(0);
    expect(afterSwitch().every((entry) => entry.stage !== "results")).toBe(true);
    const latest = afterSwitch();
    expect(latest[latest.length - 1]?.pending).toBe(true);

    await act(async () => {
      release.resolve();
      await release.promise;
    });
    await waitFor(() => expect(screen.getByTestId("stage").textContent).toBe("progress"));
    expect(afterSwitch().every((entry) => entry.stage !== "results")).toBe(true);
    // Every record project 2's journey used was requested with project 2's header.
    const project2Urls = api.requests.filter((request) => request.project === "project-2");
    expect(project2Urls.map((request) => request.url)).toEqual(
      expect.arrayContaining([
        "/chips",
        "/chips/config-sources",
        "/flows/first_calibration",
        "/executions/20261105-001",
      ]),
    );
  });

  it("does not let a result cached in the old project finish the new project's result step", async () => {
    let showViewer = true;
    const view = setup(() => (
      <>
        <Probe />
        {showViewer && <ResultViewer taskId="t1" />}
      </>
    ));
    // Project 1's run confirms the open result; it counts once the user is done with it.
    await waitFor(() =>
      expect(
        api.requests.some(
          (request) =>
            request.project === "project-1" && request.url === "/executions/20261105-001",
        ),
      ).toBe(true),
    );
    await waitFor(() => expect(screen.getByTestId("stage").textContent).toBe("results"));
    expect(storedJourney("project-1").inspectedTaskId).toBeNull();

    const release = deferred<void>();
    api.gate = release.promise;
    await view.switchTo("project-2");
    // Project 1's answers are still cached while project 2's are on their way.
    expect(storedJourney("project-2").inspectedTaskId).toBeNull();

    await act(async () => {
      release.resolve();
      await release.promise;
    });
    await waitFor(() => expect(screen.getByTestId("stage").textContent).toBe("progress"));

    // Closing the result in project 2 finishes neither journey: the result was confirmed in
    // project 1, and task t1 of execution 20261105-001 exists only there.
    showViewer = false;
    await act(async () => {
      view.rerender();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(storedJourney("project-2").inspectedTaskId).toBeNull();
    expect(storedJourney("project-1").inspectedTaskId).toBeNull();
  });
});
