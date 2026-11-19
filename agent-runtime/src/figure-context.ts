/**
 * Figures already in a conversation, for tools that evaluate them.
 *
 * A figure enters the transcript either as a user attachment or inside a tool
 * result (`qdash_get_figure` and friends return PNG blocks). A tool such as
 * `qcal_evaluate` declares an `images` parameter, but the model cannot be
 * trusted to copy image bytes into its arguments, so the runtime fills the
 * parameter from the newest figure of the requested task instead.
 *
 * The selection rules are shared with the pi CLI and live in pi-qdash
 * (extensions/lib/qcal-hydration.ts); this module reads them from the durable
 * transcript's entry shape.
 */

import {
  selectEvaluationFigures,
  type FigureMessage,
  type ImageBlock,
} from "@oqtopus-team/pi-qdash/extensions/lib/qcal-hydration.ts";

export {
  acceptsImages,
  hasImages,
  isImageData,
  MAX_SUPPLIED_IMAGES,
  requestedImageCount,
  selectEvaluationFigures,
  withImages,
} from "@oqtopus-team/pi-qdash/extensions/lib/qcal-hydration.ts";
export type {
  FigureMessage,
  ImageArgument,
  ImageBlock,
  SelectedFigures,
} from "@oqtopus-team/pi-qdash/extensions/lib/qcal-hydration.ts";

type EntryLike = { model?: readonly FigureMessage[] };

/** The newest figures of a conversation and, when a tool fetched them, the task result they belong to. */
export interface LatestFigures {
  images: ImageBlock[];
  /** `details.taskId` of the tool result that carried the figures (pi-qdash figure tools set it). */
  taskId?: string;
  /** The task name that result recorded. */
  taskName?: string;
}

/**
 * The messages of transcript entries, newest first. `entries` must be
 * newest-first, as pi-durable's `scanEntries` returns them; the messages of
 * one entry are in order, so they are read from the end.
 */
export function* newestMessages(entries: ReadonlyArray<EntryLike>): Generator<FigureMessage> {
  for (const entry of entries) {
    const messages = entry.model ?? [];
    for (let index = messages.length - 1; index >= 0; index -= 1) yield messages[index]!;
  }
}

/** Image blocks of the newest message that carries any; see `latestFigures`. */
export function latestImages(entries: ReadonlyArray<EntryLike>, max = 1): ImageBlock[] {
  return latestFigures(entries, max).images;
}

/**
 * The newest figures in `entries`, with the task result they came from when
 * known. With `taskName`, figures recorded for another task are skipped (see
 * `selectEvaluationFigures`). When a message holds several figures (expected
 * figure first, measured last), the last `max` are kept.
 */
export function latestFigures(entries: ReadonlyArray<EntryLike>, max = 1, taskName?: string): LatestFigures {
  return selectEvaluationFigures(newestMessages(entries), { max, ...(taskName ? { taskName } : {}) });
}
