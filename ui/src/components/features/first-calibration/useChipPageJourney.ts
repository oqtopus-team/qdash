"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { JOURNEY_CREATE_CHIP_QUERY_VALUE } from "@/lib/firstCalibrationJourney";

import { journeyNewFlowHref } from "./journeyProgress";
import { useFirstCalibrationJourney, type JourneyContext } from "./useFirstCalibrationJourney";
import { useFirstCalibrationProgress } from "./useFirstCalibrationProgress";

/**
 * What the Chip page knew when Create Chip was submitted. The answer is checked against it, so a
 * chip created after the user paused the guide, switched project or signed out moves nothing.
 */
export interface ChipCreateSubmission {
  context: JourneyContext;
  /** The guide adopts the chip created by this submission. */
  adopts: boolean;
}

/** What the page does after a chip was created: stay, or leave for the guide's next page. */
export type ChipCreatedOutcome = "stay" | "navigate";

interface ChipPageJourneyOptions {
  selectedChip: string | null;
  openCreateChip: () => void;
}

/**
 * The Chip page's part in the first calibration journey.
 *
 * - `?journey=create-chip` opens the Create Chip dialog once and adopts the chip created there.
 * - `?tutorial=create-chip`, the link of the retired chip setup tour, starts or resumes the
 *   journey instead.
 * - Showing the journey's chip after one of its results was inspected finishes the journey.
 * - `adoptsCreatedChip` tells the Create Chip dialog that the guide takes the user on from the
 *   created chip, so it does not offer its own shortcut to the template.
 * - On a preset deployment (fake or qibocal), creating the guide's chip opens the New Flow editor on
 *   the preset's template
 *   for that chip, once, as the answer to that submission. `leavingForGuide` then tells the page
 *   to stop writing its URL state, because a Chip page URL written after the push cancels it. On hardware the user stays on the page,
 *   where the guide asks them to confirm the chip's configuration before the editor.
 */
export function useChipPageJourney({ selectedChip, openCreateChip }: ChipPageJourneyOptions) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { state, enabled, record, capture } = useFirstCalibrationJourney();
  const active = state?.status === "active" ? state : null;
  const { setup } = useFirstCalibrationProgress(active);
  const createChipRequested =
    enabled && searchParams.get("journey") === JOURNEY_CREATE_CHIP_QUERY_VALUE;
  const legacyTutorial = searchParams.get("tutorial") === "create-chip";

  const replaceQuery = useCallback(
    (update: (params: URLSearchParams) => void) => {
      const params = new URLSearchParams(searchParams.toString());
      update(params);
      const query = params.toString();
      router.replace(query ? `/chip?${query}` : "/chip", { scroll: false });
    },
    [router, searchParams],
  );

  useEffect(() => {
    if (!legacyTutorial) return;
    if (!enabled) {
      replaceQuery((params) => params.delete("tutorial"));
      return;
    }
    if (!state) record({ type: "start", chipId: null });
    else if (state.status === "paused") record({ type: "resume" });
    const needsChip = !state?.chipId;
    replaceQuery((params) => {
      params.delete("tutorial");
      if (needsChip) params.set("journey", JOURNEY_CREATE_CHIP_QUERY_VALUE);
    });
  }, [legacyTutorial, enabled, state, record, replaceQuery]);

  // Opening a form is all the link does; creating the chip stays the user's choice.
  const dialogOpened = useRef(false);
  useEffect(() => {
    if (!createChipRequested) {
      dialogOpened.current = false;
      return;
    }
    if (dialogOpened.current) return;
    dialogOpened.current = true;
    openCreateChip();
  }, [createChipRequested, openCreateChip]);

  useEffect(() => {
    if (
      state?.status === "active" &&
      state.chipId !== null &&
      state.inspectedTaskId !== null &&
      !state.chipOverviewSeen &&
      selectedChip === state.chipId
    ) {
      record({ type: "chipOverviewSeen", chipId: state.chipId });
    }
  }, [state, selectedChip, record]);

  // Adopt the chip when the journey sent the user here, or when it has no chip yet.
  const adoptsCreatedChip =
    state?.status === "active" && (createChipRequested || state.chipId === null);

  const captureCreateSubmission = useCallback(
    (): ChipCreateSubmission => ({
      context: capture(),
      adopts: adoptsCreatedChip,
    }),
    [capture, adoptsCreatedChip],
  );

  // Set once the page leaves for the editor, so the dialog closing after the answer does not
  // replace the new route with a Chip page URL.
  const leaving = useRef(false);
  // The same, for the page: it stops writing its own URL state, which would cancel the push.
  const [leavingForGuide, setLeavingForGuide] = useState(false);
  const handledChips = useRef(new Set<string>());

  const onChipCreated = useCallback(
    (chipId: string, submission?: ChipCreateSubmission): ChipCreatedOutcome => {
      if (!submission?.adopts || handledChips.current.has(chipId)) return "stay";
      const { context } = submission;
      // The guide may have been paused, restarted or left while the chip was being created.
      if (!context.followsSubmittedJourney()) return "stay";
      if (context.record({ type: "chipSelected", chipId })?.chipId !== chipId) return "stay";
      handledChips.current.add(chipId);
      const href = setup.kind === "preset" ? journeyNewFlowHref(setup, chipId) : null;
      if (!href) return "stay";
      // Back returns to the Chip page showing the new chip, not to the reopened dialog.
      const params = new URLSearchParams(window.location.search);
      params.delete("journey");
      params.set("chip", chipId);
      window.history.replaceState(null, "", `/chip?${params.toString()}`);
      leaving.current = true;
      setLeavingForGuide(true);
      router.push(href);
      return "navigate";
    },
    [router, setup],
  );

  const onCreateChipClosed = useCallback(() => {
    if (leaving.current) return;
    if (createChipRequested) replaceQuery((params) => params.delete("journey"));
  }, [createChipRequested, replaceQuery]);

  return {
    adoptsCreatedChip,
    leavingForGuide,
    captureCreateSubmission,
    onChipCreated,
    onCreateChipClosed,
  };
}
