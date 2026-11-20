"use client";

import { MarkdownContent } from "@/components/ui/MarkdownContent";

import { PanelMessage } from "./PanelStates";

export function MarkdownPanel({ content }: { content: string }) {
  if (!content.trim()) return <PanelMessage>This note is empty</PanelMessage>;
  return (
    <div className="h-full overflow-y-auto pr-1">
      <MarkdownContent content={content} />
    </div>
  );
}
