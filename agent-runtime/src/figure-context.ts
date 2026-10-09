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

/** Whether the model already passed at least one image. */
export function hasImages(args: unknown): boolean {
  const images = (args as { images?: unknown } | null)?.images;
  return Array.isArray(images) && images.length > 0;
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

/** The model's arguments with `images` filled in when it passed none. */
export function withImages<T extends object>(
  args: T,
  images: ReadonlyArray<ImageBlock>,
): T | (T & { images: ImageArgument[] }) {
  if (hasImages(args) || images.length === 0) return args;
  return { ...args, images: images.map(({ data, mimeType }) => ({ data, mimeType })) };
}
