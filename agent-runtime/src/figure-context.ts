/**
 * Figures already in a conversation, for tools that evaluate them.
 *
 * A figure enters the transcript either as a user attachment or inside a tool
 * result (`qdash_get_figure` and friends return PNG blocks). A tool such as
 * `qcal_evaluate` declares an `images` parameter, but the model cannot be
 * trusted to copy image bytes into its arguments, so the runtime fills the
 * parameter from the newest figure instead.
 *
 * Pure functions only, so they can be tested without a running agent.
 */

import type { TSchema } from "typebox";

export interface ImageBlock {
  type: "image";
  data: string;
  mimeType: string;
}

/** The wire shape of one image in a tool's `images` argument. */
export interface ImageArgument {
  data: string;
  mimeType: string;
}

type MessageLike = { content?: unknown };
type EntryLike = { model?: readonly MessageLike[] };

/** Whether a tool declares an `images` parameter the runtime may fill. */
export function acceptsImages(parameters: TSchema): boolean {
  const properties = (parameters as { properties?: Record<string, unknown> }).properties;
  return properties !== undefined && "images" in properties;
}

/** Most figures a tool may ask the runtime to supply. */
export const MAX_SUPPLIED_IMAGES = 4;

/**
 * How many of the newest figures the tool asked for via `max_images`
 * (default 1); the tool's own limit still applies downstream.
 */
export function requestedImageCount(args: unknown, limit = MAX_SUPPLIED_IMAGES): number {
  const value = (args as { max_images?: unknown } | null)?.max_images;
  if (typeof value !== "number" || !Number.isFinite(value)) return 1;
  return Math.min(Math.max(Math.floor(value), 1), limit);
}

/**
 * Shortest payload accepted as image bytes. A model that invents an `images`
 * argument writes placeholders such as "<image 1>" or "see attached", never a
 * base64 string of a real PNG, whose header alone is longer than this.
 */
const MIN_IMAGE_BASE64_LENGTH = 64;
const BASE64 = /^[A-Za-z0-9+/]+={0,2}$/;

/**
 * Whether the model passed image bytes of its own. Placeholders are ignored
 * so the transcript's real figures are used instead.
 */
export function hasImages(args: unknown): boolean {
  const images = (args as { images?: unknown } | null)?.images;
  if (!Array.isArray(images) || images.length === 0) return false;
  return images.every((image) => {
    const data = (image as { data?: unknown } | null)?.data;
    return (
      typeof data === "string" && data.length >= MIN_IMAGE_BASE64_LENGTH && BASE64.test(data)
    );
  });
}

/**
 * Image blocks of the newest message that carries any.
 *
 * `entries` must be newest-first, as pi-durable's `scanEntries` returns them;
 * the messages of one entry are in order, so they are read from the end. When
 * a message holds several figures (expected figure first, measured last), the
 * last `max` are kept.
 */
export function latestImages(entries: ReadonlyArray<EntryLike>, max = 1): ImageBlock[] {
  for (const entry of entries) {
    for (const message of [...(entry.model ?? [])].reverse()) {
      const images = imageBlocks(message.content);
      if (images.length) return images.slice(-max);
    }
  }
  return [];
}

function imageBlocks(content: unknown): ImageBlock[] {
  if (!Array.isArray(content)) return [];
  const out: ImageBlock[] = [];
  for (const block of content) {
    if (
      typeof block === "object" &&
      block !== null &&
      (block as { type?: unknown }).type === "image" &&
      typeof (block as { data?: unknown }).data === "string" &&
      typeof (block as { mimeType?: unknown }).mimeType === "string"
    ) {
      const { data, mimeType } = block as ImageBlock;
      out.push({ type: "image", data, mimeType });
    }
  }
  return out;
}

/**
 * The model's arguments with `images` filled in when it passed none (or only
 * placeholders). Without transcript figures the placeholders are dropped, so
 * the tool reports a missing plot instead of sending junk to its model.
 */
export function withImages<T extends object>(
  args: T,
  images: ReadonlyArray<ImageBlock>,
): T | (T & { images?: ImageArgument[] }) {
  if (hasImages(args)) return args;
  if (images.length === 0) {
    if (!("images" in args)) return args;
    const { images: _placeholders, ...rest } = args as T & { images?: unknown };
    return rest as T;
  }
  return { ...args, images: images.map(({ data, mimeType }) => ({ data, mimeType })) };
}
