import { act, cleanup, render, screen } from "@testing-library/react";
import { withNuqsTestingAdapter, type UrlUpdateEvent } from "nuqs/adapters/testing";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChipPageContent } from "@/components/features/chip/ChipPageContent";

type Chip = { chip_id: string; installed_at?: string; activity_status?: string };

const mocks = vi.hoisted(() => ({
  /** The project the app works in; requests carry it. */
  projectId: "project-2" as string | null,
  /** The query string Next reports, which names the project of the URL. */
  search: "project=project-2",
  /** The current project's chip list; undefined while it loads. */
  chips: undefined as Chip[] | undefined,
  chipsFetching: false,
  leavingForGuide: false,
  chipRequests: [] as { chipId: string; enabled: boolean }[],
  muxRequests: [] as { chipId: string; enabled: boolean }[],
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(mocks.search),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ canEdit: true, projectId: mocks.projectId }),
}));

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({
    data: mocks.chips === undefined ? undefined : { data: { chips: mocks.chips } },
    isLoading: mocks.chips === undefined,
    isFetching: mocks.chips === undefined || mocks.chipsFetching,
  }),
  useGetChip: (chipId: string, options?: { query?: { enabled?: boolean } }) => {
    mocks.chipRequests.push({ chipId, enabled: options?.query?.enabled ?? true });
    return { data: undefined };
  },
  useListChipMuxes: (chipId: string, options?: { query?: { enabled?: boolean } }) => {
    mocks.muxRequests.push({ chipId, enabled: options?.query?.enabled ?? true });
    return { data: undefined, isLoading: false, isError: false };
  },
}));

vi.mock("@/client/task-file/task-file", () => ({
  useListTaskInfo: () => ({ data: undefined }),
  useGetTaskFileSettings: () => ({ data: undefined }),
}));

vi.mock("@/components/features/first-calibration/useChipPageJourney", () => ({
  useChipPageJourney: () => ({
    adoptsCreatedChip: false,
    leavingForGuide: mocks.leavingForGuide,
    captureCreateSubmission: vi.fn(),
    onChipCreated: () => "stay",
    onCreateChipClosed: vi.fn(),
  }),
}));

vi.mock("@/hooks/useQubitTaskResults", () => ({
  useQubitTaskResults: () => ({ data: undefined }),
}));
vi.mock("@/hooks/useCouplingTaskResults", () => ({
  useCouplingTaskResults: () => ({ data: undefined }),
}));
vi.mock("@/hooks/useDateNavigation", () => ({
  useDateNavigation: () => ({
    navigateToPreviousDay: vi.fn(),
    navigateToNextDay: vi.fn(),
    canNavigatePrevious: false,
    canNavigateNext: false,
    formatDate: (date: string) => date,
  }),
}));
vi.mock("@/hooks/useTopologyConfig", () => ({ useTopologyConfig: () => ({ hasMux: true }) }));

// The page's children are out of scope; the selector shows which chip the page uses.
vi.mock("@/components/selectors/ChipSelector", () => ({
  ChipSelector: ({ selectedChip }: { selectedChip: string }) => (
    <p data-testid="page-chip">{selectedChip || "none"}</p>
  ),
}));
vi.mock("@/components/selectors/CooldownSelector", () => ({ CooldownSelector: () => null }));
vi.mock("@/components/selectors/TaskSelector", () => ({ TaskSelector: () => null }));
vi.mock("@/components/ui/TimeRangeSelector", () => ({ TimeRangeSelector: () => null }));
vi.mock("@/components/ui/Skeleton/PageSkeletons", () => ({
  ChipPageSkeleton: () => <p data-testid="page-chip">loading</p>,
}));
vi.mock("@/components/features/chip/QubitGrid", () => ({ QubitGrid: () => null }));
vi.mock("@/components/features/chip/CouplingGrid", () => ({ CouplingGrid: () => null }));
vi.mock("@/components/features/chip/ChipManageModal", () => ({ ChipManageModal: () => null }));
vi.mock("@/components/features/chip/modals/CreateChipModal", () => ({
  CreateChipModal: () => null,
}));
vi.mock("@/components/features/chip/modals/TaskDetailModal", () => ({
  TaskDetailModal: () => null,
}));
vi.mock("@/components/charts/TaskFigure", () => ({ TaskFigure: () => null }));
vi.mock("@/components/features/evaluations/EvaluationRequestModal", () => ({
  EvaluationRequestModal: () => null,
  evaluationTargets: () => [],
}));

const PROJECT_2_CHIPS: Chip[] = [
  { chip_id: "older", installed_at: "2026-01-01T00:00:00Z" },
  { chip_id: "newest", installed_at: "2026-06-01T00:00:00Z" },
];

let urlUpdates: UrlUpdateEvent[] = [];

function renderPage(searchParams: string) {
  const tree = () => <ChipPageContent />;
  const wrapper = withNuqsTestingAdapter({
    searchParams,
    hasMemory: true,
    onUrlUpdate: (event) => urlUpdates.push(event),
  });
  const view = render(tree(), { wrapper });
  return { rerender: () => view.rerender(tree()) };
}

/** The chip param of the last URL update, or undefined when the page wrote none. */
function lastChipWritten(): string | null | undefined {
  const last = urlUpdates[urlUpdates.length - 1];
  return last ? last.searchParams.get("chip") : undefined;
}

function requestedChips(requests: { chipId: string; enabled: boolean }[]): string[] {
  return requests.filter((request) => request.enabled).map((request) => request.chipId);
}

async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("ChipPageContent chip of the current project", () => {
  beforeEach(() => {
    mocks.projectId = "project-2";
    mocks.search = "project=project-2";
    mocks.chips = PROJECT_2_CHIPS;
    mocks.chipsFetching = false;
    mocks.leavingForGuide = false;
    mocks.chipRequests = [];
    mocks.muxRequests = [];
    urlUpdates = [];
  });

  afterEach(() => {
    cleanup();
  });

  it("keeps a deep link to a chip of the project and loads it", async () => {
    renderPage("project=project-2&chip=older&date=20261101");
    await flush();
    expect(urlUpdates.some((event) => event.searchParams.has("chip"))).toBe(false);
    expect(screen.getByTestId("page-chip").textContent).toBe("older");
    expect(requestedChips(mocks.chipRequests)).toEqual(expect.arrayContaining(["older"]));
  });

  it("replaces a chip the project does not have with its most recent chip, never asking for the old one", async () => {
    renderPage("project=project-2&chip=from-project-1&view=2q");
    await flush();
    expect(lastChipWritten()).toBe("newest");
    // Only the chip param changes; other filters stay.
    expect(urlUpdates[urlUpdates.length - 1]?.searchParams.get("view")).toBe("2q");
    expect(screen.getByTestId("page-chip").textContent).toBe("newest");
    expect(requestedChips(mocks.chipRequests)).not.toContain("from-project-1");
    expect(requestedChips(mocks.muxRequests)).not.toContain("from-project-1");
    // An empty chip id is never sent either.
    expect(requestedChips(mocks.chipRequests)).not.toContain("");
    expect(requestedChips(mocks.muxRequests)).not.toContain("");
  });

  it("drops the chip param in a project without chips", async () => {
    mocks.chips = [];
    renderPage("project=project-2&chip=from-project-1");
    await flush();
    expect(lastChipWritten()).toBeNull();
    expect(requestedChips(mocks.chipRequests)).toEqual([]);
  });

  it("asks for a chip id both projects use only after the new project's list holds it", async () => {
    // Right after the switch the list of project 2 has not answered.
    mocks.chips = undefined;
    const page = renderPage("project=project-2&chip=shared");
    await flush();
    expect(requestedChips(mocks.chipRequests)).toEqual([]);
    expect(urlUpdates).toEqual([]);

    mocks.chips = [{ chip_id: "shared" }, ...PROJECT_2_CHIPS];
    page.rerender();
    await flush();
    expect(requestedChips(mocks.chipRequests)).toEqual(expect.arrayContaining(["shared"]));
    expect(urlUpdates.some((event) => event.searchParams.has("chip"))).toBe(false);
  });

  it("keeps a chip just created while the list refetches", async () => {
    mocks.chipsFetching = true;
    const page = renderPage("project=project-2&chip=created");
    await flush();
    expect(urlUpdates).toEqual([]);
    expect(requestedChips(mocks.chipRequests)).toEqual([]);

    mocks.chipsFetching = false;
    mocks.chips = [...PROJECT_2_CHIPS, { chip_id: "created" }];
    page.rerender();
    await flush();
    expect(urlUpdates).toEqual([]);
    expect(screen.getByTestId("page-chip").textContent).toBe("created");
  });

  it("leaves the chip alone while Back restores another project's entry", async () => {
    // The URL already names project 1 again; the list on screen is still project 2's.
    mocks.search = "project=project-1";
    renderPage("project=project-1&chip=from-project-1");
    await flush();
    expect(urlUpdates).toEqual([]);
    expect(requestedChips(mocks.chipRequests)).toEqual([]);
  });

  it("does not write the Chip page URL while the guide leaves for the editor", async () => {
    mocks.leavingForGuide = true;
    renderPage("project=project-2");
    await flush();
    expect(urlUpdates).toEqual([]);
  });

  it("selects the most recent chip when the URL names none", async () => {
    renderPage("project=project-2");
    await flush();
    expect(lastChipWritten()).toBe("newest");
  });
});
