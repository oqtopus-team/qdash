"use client";

import { useQuery } from "@tanstack/react-query";
import { ImageOff } from "lucide-react";

import { getGetTaskKnowledgeQueryKey, getTaskKnowledge } from "@/client/task/task";
import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";
import type { EvaluationInputModel } from "@/schemas";

/** One image slot of the user turn, in the order the model received it. */
type FigureSlot =
  | {
      kind: "example";
      exampleIndex: number;
      exampleTitle: string;
      outcome: string;
      path: string | null;
      sha256: string;
      mimeType: string;
    }
  | { kind: "query"; index: number; path: string | null; sha256: string; mimeType: string };

export type InputPart =
  | { type: "text"; text: string }
  | { type: "figure"; slot: FigureSlot | null };

/** The marker the evaluator writes into the recorded prompt where an image block was. */
const FIGURE_MARKER = "[figure]";

/**
 * Rebuild the user turn as the model received it: the recorded prompt's text
 * with each `[figure]` marker replaced by the image that stood there. The
 * evaluator lays images out as the labeled examples' figures first, in order,
 * then the figures to judge; a marker without a matching record stays an
 * unnamed slot. A prompt without markers (recorded before the evaluator wrote
 * them) had its figures after the text.
 */
export function modelInputParts(
  input: Pick<EvaluationInputModel, "prompt" | "figures" | "examples">,
  figurePaths: readonly string[] = [],
): InputPart[] {
  const slots: FigureSlot[] = [];
  (input.examples ?? []).forEach((example, exampleIndex) => {
    for (const figure of example.figures ?? []) {
      slots.push({
        kind: "example",
        exampleIndex,
        exampleTitle: example.title ?? "",
        outcome: example.outcome ?? "",
        path: figure.path ?? null,
        sha256: figure.sha256,
        mimeType: figure.mime_type,
      });
    }
  });
  (input.figures ?? []).forEach((figure, index) => {
    slots.push({
      kind: "query",
      index,
      path: figurePaths[index] ?? null,
      sha256: figure.sha256,
      mimeType: figure.mime_type,
    });
  });

  const parts: InputPart[] = [];
  let text: string[] = [];
  let next = 0;
  const flush = () => {
    const joined = text.join("\n").trim();
    if (joined) parts.push({ type: "text", text: joined });
    text = [];
  };
  for (const line of (input.prompt ?? "").split("\n")) {
    if (line.trim() === FIGURE_MARKER) {
      flush();
      parts.push({ type: "figure", slot: slots[next] ?? null });
      next += 1;
    } else {
      text.push(line);
    }
  }
  flush();
  // Records from before the evaluator marked figures: the images followed the text.
  if (next === 0) {
    for (const slot of slots) parts.push({ type: "figure", slot });
  }
  return parts;
}

async function sha256Hex(bytes: ArrayBuffer): Promise<string | null> {
  if (typeof crypto === "undefined" || !crypto.subtle) return null;
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

function base64Bytes(data: string): ArrayBuffer {
  const binary = atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

interface LoadedFigure {
  src: string;
  /** Whether the bytes shown are the bytes the model saw; null when it cannot be checked. */
  matches: boolean | null;
}

function useSlotFigure(slot: FigureSlot, taskName: string) {
  const knowledge = useQuery({
    queryKey: getGetTaskKnowledgeQueryKey(taskName),
    queryFn: () => getTaskKnowledge(taskName).then((response) => response.data),
    enabled: slot.kind === "example" && !!taskName,
    staleTime: 60_000,
  });
  const query = useQuery({
    queryKey: ["evaluation-query-figure", slot.kind === "query" ? slot.path : null],
    queryFn: async (): Promise<ArrayBuffer> => {
      const response = await AXIOS_INSTANCE.get<ArrayBuffer>("/executions/figure", {
        params: { path: slot.path },
        responseType: "arraybuffer",
      });
      return response.data;
    },
    enabled: slot.kind === "query" && !!slot.path,
    staleTime: Infinity,
  });
  const loaded = useQuery({
    queryKey: [
      "evaluation-figure-check",
      slot.kind,
      slot.path,
      slot.sha256,
      !!knowledge.data,
      !!query.data,
    ],
    queryFn: async (): Promise<LoadedFigure | null> => {
      if (slot.kind === "example") {
        const figure = knowledge.data?.examples
          ?.flatMap((example) => example.figures ?? [])
          .find((candidate) => candidate.path === slot.path);
        if (!figure?.base64_data) return null;
        const hash = await sha256Hex(base64Bytes(figure.base64_data));
        return {
          src: `data:${figure.mime_type || slot.mimeType};base64,${figure.base64_data}`,
          matches: hash === null ? null : hash === slot.sha256,
        };
      }
      if (!query.data) return null;
      const hash = await sha256Hex(query.data);
      const blob = new Blob([query.data], { type: slot.mimeType });
      return {
        src: URL.createObjectURL(blob),
        matches: hash === null ? null : hash === slot.sha256,
      };
    },
    enabled:
      (slot.kind === "example" && !!knowledge.data) || (slot.kind === "query" && !!query.data),
    staleTime: Infinity,
  });
  const pending =
    (slot.kind === "example" ? knowledge.isLoading : query.isLoading) || loaded.isLoading;
  return { figure: loaded.data ?? null, pending };
}

function slotCaption(slot: FigureSlot): string {
  if (slot.kind === "example") {
    return `Example ${slot.exampleIndex + 1}: ${slot.exampleTitle || "untitled"} (${slot.outcome})`;
  }
  return slot.index === 0 ? "Figure to judge" : `Figure to judge ${slot.index + 1}`;
}

function FigureSlotView({ slot, taskName }: { slot: FigureSlot | null; taskName: string }) {
  if (!slot) {
    return (
      <div className="rounded-lg border border-dashed border-base-300 px-3 py-4 text-center text-xs text-base-content/50">
        A figure the record does not identify
      </div>
    );
  }
  return <KnownFigureSlot slot={slot} taskName={taskName} />;
}

function KnownFigureSlot({ slot, taskName }: { slot: FigureSlot; taskName: string }) {
  const { figure, pending } = useSlotFigure(slot, taskName);
  return (
    <figure className="rounded-lg border border-base-300 bg-base-100 p-2">
      <div className="flex h-48 items-center justify-center overflow-hidden rounded bg-white p-1">
        {pending ? (
          <span className="loading loading-spinner loading-sm" />
        ) : figure ? (
          /* eslint-disable-next-line @next/next/no-img-element -- figure bytes loaded for the record */
          <img src={figure.src} alt={slotCaption(slot)} className="h-full w-full object-contain" />
        ) : (
          <span className="flex flex-col items-center gap-1 text-xs text-base-content/50">
            <ImageOff className="h-5 w-5" />
            No longer available
          </span>
        )}
      </div>
      <figcaption className="mt-1 flex flex-wrap items-center gap-2 text-xs text-base-content/60">
        <span>{slotCaption(slot)}</span>
        {slot.path && <span className="font-mono text-base-content/40">{slot.path}</span>}
        {figure?.matches === false && (
          <span
            className="badge badge-warning badge-xs"
            title="The file has changed since this evaluation; the model saw an earlier version"
          >
            changed since
          </span>
        )}
      </figcaption>
    </figure>
  );
}

/**
 * Everything the evaluation model was sent for one evaluation, in order: the
 * system prompt, then the user turn with its figures where they stood (the
 * reference, each labeled example's figure and diagnosis, the context, the
 * figure to judge). Figures are loaded only when this is rendered.
 */
export function ModelInputView({
  input,
  taskName,
  figurePaths,
}: {
  input: EvaluationInputModel;
  taskName: string;
  figurePaths: readonly string[];
}) {
  const parts = modelInputParts(input, figurePaths);
  return (
    <div className="mt-2 space-y-3 rounded-lg border border-base-300 bg-base-200/40 p-3">
      <section>
        <div className="mb-1 text-xs uppercase text-base-content/50">System prompt</div>
        {input.system_prompt ? (
          <pre className="whitespace-pre-wrap rounded bg-base-100 p-2 text-xs">
            {input.system_prompt}
          </pre>
        ) : (
          <p className="text-xs text-base-content/50">
            Not recorded (the evaluator that ran this did not report it).
          </p>
        )}
      </section>
      <section className="space-y-2">
        <div className="text-xs uppercase text-base-content/50">User turn</div>
        {parts.map((part, index) =>
          part.type === "text" ? (
            <pre
              key={index}
              className="max-h-80 overflow-auto whitespace-pre-wrap rounded bg-base-100 p-2 text-xs"
            >
              {part.text}
            </pre>
          ) : (
            <FigureSlotView key={index} slot={part.slot} taskName={taskName} />
          ),
        )}
      </section>
    </div>
  );
}
