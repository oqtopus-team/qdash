"use client";

import React, { memo, useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Copy,
  ImageIcon,
  Pencil,
  RotateCcw,
  Square,
  XCircle,
} from "lucide-react";
import { ChatPlotlyChart } from "@/components/features/chat/ChatPlotlyChart";
import { ChatMarkdown } from "@/components/features/chat/ChatMarkdown";
import { ChatTraceSummary, LiveTrace } from "@/components/features/chat/ChatTrace";
import {
  ApprovalCard,
  AskCard,
  type InteractionState,
} from "@/components/features/chat/ChatInteractionCards";
import { ImagePreviewDialog } from "@/components/ui/ImagePreviewDialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { answerStartIndex } from "@/lib/copilotChatStream";
import type {
  BlocksResult,
  ChatMessage as CopilotMessage,
  CopilotBlocksResult,
  LiveTurn,
} from "@/types/copilotChat";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseBlocksContent(content: string): CopilotBlocksResult | null {
  if (!content.startsWith("{")) return null;
  try {
    const data = JSON.parse(content);
    if (data.blocks && Array.isArray(data.blocks)) {
      return data as CopilotBlocksResult;
    }
  } catch {
    // Not JSON
  }
  return null;
}

/** Plain text of an assistant message, for copying. */
function messageText(content: string): string {
  const parsed = parseBlocksContent(content);
  if (!parsed) return content;
  return parsed.blocks
    .filter((b) => b.type === "text" && b.content)
    .map((b) => b.content)
    .join("\n\n");
}

function isErrorMessage(message: CopilotMessage): boolean {
  return message.role === "assistant" && message.content.startsWith("Error: ");
}

// ---------------------------------------------------------------------------
// Small pieces
// ---------------------------------------------------------------------------

function ActionButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onClick}
          className="btn btn-ghost btn-xs btn-square text-base-content/45 hover:text-base-content"
          aria-label={label}
        >
          {children}
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(() => {
    navigator.clipboard.writeText(text).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      },
      () => {},
    );
  }, [text]);
  return (
    <ActionButton label={copied ? "Copied" : "Copy"} onClick={copy}>
      {copied ? <Check className="w-3.5 h-3.5 text-success" /> : <Copy className="w-3.5 h-3.5" />}
    </ActionButton>
  );
}

function AssessmentBadge({ assessment }: { assessment: string | null }) {
  const styles = {
    good: {
      cls: "bg-success/10 text-success border-success/20",
      Icon: CheckCircle2,
      label: "Good",
    },
    warning: {
      cls: "bg-warning/10 text-warning border-warning/20",
      Icon: AlertTriangle,
      label: "Warning",
    },
    bad: { cls: "bg-error/10 text-error border-error/20", Icon: XCircle, label: "Bad" },
  } as const;
  const style = assessment ? styles[assessment as keyof typeof styles] : undefined;
  if (!style) return null;
  const { cls, Icon, label } = style;
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full border ${cls}`}
    >
      <Icon className="w-3.5 h-3.5" />
      {label}
    </span>
  );
}

function ImageSentBadge({ imagesSent }: { imagesSent: BlocksResult["images_sent"] }) {
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);

  if (!imagesSent) return null;
  const { experiment_figure, experiment_figure_paths, expected_images, task_name } = imagesSent;
  if (!experiment_figure && expected_images.length === 0) return null;

  const parts: string[] = [];
  if (experiment_figure) parts.push("実験結果画像");
  if (expected_images.length > 0) parts.push(`参照画像${expected_images.length}枚`);

  const baseURL = process.env.NEXT_PUBLIC_API_URL || "/api";
  const sources = [
    ...(experiment_figure
      ? experiment_figure_paths.map((fp) => ({
          key: fp,
          alt: "実験結果",
          src: `${baseURL}/executions/figure?path=${encodeURIComponent(fp)}`,
        }))
      : []),
    ...expected_images.map((img) => ({
      key: `expected-${img.index}`,
      alt: img.alt_text,
      src: `${baseURL}/copilot/expected-image?task_name=${encodeURIComponent(task_name)}&index=${img.index}`,
    })),
  ];

  return (
    <div className="mb-2">
      <div className="flex items-center gap-1.5 text-xs text-base-content/50 mb-2">
        <ImageIcon className="w-3.5 h-3.5" />
        <span>{parts.join(" + ")}を送信</span>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {sources.map(({ key, alt, src }) => (
          <button
            key={key}
            type="button"
            onClick={() => setPreviewSrc(src)}
            className="flex-shrink-0 rounded-lg border border-base-300 overflow-hidden hover:border-primary/50 hover:shadow-md transition-all cursor-pointer"
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- runtime-generated API preview */}
            <img
              src={src}
              alt={alt}
              className="h-16 w-auto object-contain bg-base-200"
              loading="lazy"
            />
          </button>
        ))}
      </div>
      <ImagePreviewDialog src={previewSrc} onClose={() => setPreviewSrc(null)} />
    </div>
  );
}

function BlocksContent({
  blocks,
  interaction,
}: {
  blocks: CopilotBlocksResult;
  interaction: InteractionState;
}) {
  return (
    <>
      {blocks.trace && <ChatTraceSummary trace={blocks.trace} />}
      <ImageSentBadge imagesSent={blocks.images_sent} />
      {blocks.assessment && (
        <div className="mb-2">
          <AssessmentBadge assessment={blocks.assessment} />
        </div>
      )}
      {blocks.blocks.map((block, i) => {
        if (block.type === "text" && block.content) {
          return <ChatMarkdown key={i}>{block.content}</ChatMarkdown>;
        }
        if (block.type === "ask" && block.ask) {
          return <AskCard key={i} ask={block.ask} state={interaction} />;
        }
        if (block.type === "approval" && block.approval) {
          return <ApprovalCard key={i} approval={block.approval} state={interaction} />;
        }
        if (block.type === "chart" && block.chart) {
          return (
            <div key={i} className="my-3 rounded-xl border border-base-300/60 overflow-hidden">
              <ChatPlotlyChart
                data={block.chart.data as Record<string, unknown>[]}
                layout={block.chart.layout as Record<string, unknown>}
              />
            </div>
          );
        }
        return null;
      })}
      {blocks.stopped && (
        <div className="mt-2 inline-flex items-center gap-1.5 text-xs text-base-content/45">
          <Square className="w-3 h-3" />
          Stopped
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Messages
// ---------------------------------------------------------------------------

export const UserMessage = memo(function UserMessage({
  message,
  canEdit,
  onEdit,
}: {
  message: CopilotMessage;
  /** Nothing is streaming, so the message can be edited and resent. */
  canEdit: boolean;
  onEdit: (text: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.content);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const startEdit = useCallback(() => {
    setDraft(message.content);
    setEditing(true);
  }, [message.content]);

  const cancelEdit = useCallback(() => setEditing(false), []);

  const submitEdit = useCallback(() => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    setEditing(false);
    if (trimmed !== message.content) onEdit(trimmed);
  }, [draft, message.content, onEdit]);

  useEffect(() => {
    if (!editing) return;
    const el = textareaRef.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 320)}px`;
  }, [editing, draft]);

  if (editing) {
    return (
      <div className="chat-user-edit animate-fade-in-up">
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.nativeEvent.isComposing) return;
            if (e.key === "Escape") {
              e.preventDefault();
              cancelEdit();
            } else if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submitEdit();
            }
          }}
          rows={1}
          aria-label="Edit message"
          className="w-full resize-none bg-transparent border-none outline-none focus:ring-0 text-[15px] leading-6"
        />
        <div className="flex items-center justify-end gap-2 mt-2">
          <button type="button" onClick={cancelEdit} className="btn btn-ghost btn-sm rounded-full">
            Cancel
          </button>
          <button
            type="button"
            onClick={submitEdit}
            disabled={!draft.trim()}
            className="btn btn-primary btn-sm rounded-full"
          >
            Send
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="group flex flex-col items-end gap-1 animate-fade-in-up">
      {message.attachedImage && (
        <span className="inline-flex items-center gap-1 text-[11px] text-base-content/45">
          <ImageIcon className="w-3 h-3" />
          Result figures attached
        </span>
      )}
      <div className="chat-bubble-user-soft rounded-3xl px-4 py-2.5 max-w-[85%] text-[15px] leading-relaxed whitespace-pre-wrap break-words">
        {message.content}
      </div>
      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
        <CopyButton text={message.content} />
        {canEdit && (
          <ActionButton label="Edit message" onClick={startEdit}>
            <Pencil className="w-3.5 h-3.5" />
          </ActionButton>
        )}
      </div>
    </div>
  );
});

export const AssistantMessage = memo(function AssistantMessage({
  message,
  isLast,
  canRetry,
  onRetry,
  answer,
  onAnswer,
  onDecide,
  onOther,
}: {
  message: CopilotMessage;
  isLast: boolean;
  canRetry: boolean;
  onRetry: () => void;
  /** The user message that follows this answer, if any. */
  answer?: string;
  onAnswer: InteractionState["onAnswer"];
  onDecide: InteractionState["onDecide"];
  onOther: InteractionState["onOther"];
}) {
  if (isErrorMessage(message)) {
    return (
      <div className="chat-assistant-row animate-fade-in-up">
        <div className="flex items-start gap-2 text-sm text-error bg-error/5 rounded-xl px-4 py-3 border border-error/20">
          <XCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span className="break-words min-w-0">{message.content.slice("Error: ".length)}</span>
        </div>
        {isLast && canRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="btn btn-ghost btn-sm gap-1.5 mt-2 rounded-full"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Retry
          </button>
        )}
      </div>
    );
  }

  const blocks = parseBlocksContent(message.content);
  return (
    <div className="group chat-assistant-row">
      {blocks ? (
        <BlocksContent
          blocks={blocks}
          interaction={{ active: isLast && canRetry, answer, onAnswer, onDecide, onOther }}
        />
      ) : (
        <ChatMarkdown>{message.content}</ChatMarkdown>
      )}
      <div
        className={`mt-1.5 -ml-1.5 flex items-center gap-0.5 transition-opacity ${
          isLast ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus-within:opacity-100"
        }`}
      >
        <CopyButton text={messageText(message.content)} />
        {isLast && canRetry && (
          <ActionButton label="Regenerate" onClick={onRetry}>
            <RotateCcw className="w-3.5 h-3.5" />
          </ActionButton>
        )}
      </div>
    </div>
  );
});

/** The answer that is still streaming. */
export function LiveAssistantMessage({
  turn,
  statusMessage,
}: {
  turn: LiveTurn;
  statusMessage: string | null;
}) {
  const split = answerStartIndex(turn.steps);
  const work = turn.steps.slice(0, split);
  const answer = turn.steps
    .slice(split)
    .map((s) => (s.kind === "text" ? s.text : ""))
    .join("");
  const busy = turn.steps.some(
    (s) =>
      (s.kind === "tool" && s.status === "running") ||
      (s.kind === "thinking" && s.endedAt === undefined),
  );

  return (
    <div className="chat-assistant-row animate-fade-in-up" aria-live="polite" aria-busy="true">
      <LiveTrace steps={work} />
      {answer ? (
        <ChatMarkdown className="chat-streaming">{answer}</ChatMarkdown>
      ) : (
        !busy && (
          <div className="flex items-center gap-2 h-7 text-sm">
            <span className="chat-pulse-dot" aria-hidden="true" />
            <span className="chat-shimmer-text">{statusMessage || "Thinking"}</span>
          </div>
        )
      )}
    </div>
  );
}
