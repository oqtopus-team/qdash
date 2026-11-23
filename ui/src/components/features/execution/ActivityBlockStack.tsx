import type { CSSProperties } from "react";

import type { ActivityDayColumn, ActivityStatusKey } from "./executionActivityBlocks";

interface ActivityBlockStackProps {
  column: ActivityDayColumn;
  /** Grid height in blocks; rows above the column's blocks are drawn empty. */
  rows: number;
  /** Executions one full block stands for. */
  scale: number;
  blockStyle: (status: ActivityStatusKey) => CSSProperties;
  className?: string;
}

/**
 * One activity column as a stack of `rows` equal blocks, bottom up. Each block is split into
 * status segments whose heights are their execution counts over the scale, so the filled
 * height of the column is exactly its total over the scale and lines up with count guides.
 */
export function ActivityBlockStack({
  column,
  rows,
  scale,
  blockStyle,
  className = "",
}: ActivityBlockStackProps) {
  const empties = Math.max(0, rows - column.blocks.length);
  return (
    <span className={`flex h-full w-full flex-col-reverse gap-px ${className}`}>
      {column.blocks.map((block, blockIndex) => (
        <span
          key={blockIndex}
          data-block-executions={block.executions}
          className="flex min-h-0 flex-1 flex-col-reverse overflow-hidden rounded-xs bg-base-content/5"
        >
          {block.segments.map((segment, segmentIndex) => (
            <span
              key={segmentIndex}
              data-status={segment.status}
              data-executions={segment.executions}
              data-partial={segment.partial || undefined}
              className="shrink-0"
              style={{
                ...blockStyle(segment.status),
                height: `${(segment.executions / scale) * 100}%`,
              }}
            />
          ))}
        </span>
      ))}
      {Array.from({ length: empties }, (_, emptyIndex) => (
        <span key={`empty-${emptyIndex}`} className="min-h-0 flex-1 rounded-xs bg-base-content/5" />
      ))}
    </span>
  );
}
