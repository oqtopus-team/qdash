"use client";

import { useMemo, useState } from "react";

import { ChevronRight } from "lucide-react";

import { entityIdFor, publishedParameters } from "@/lib/provenanceTarget";

import { ParameterLineagePanel } from "./ParameterLineagePanel";

interface TaskLineageSectionProps {
  taskId: string;
  executionId: string;
  qid: string;
  outputParameters: Record<string, unknown> | null | undefined;
  className?: string;
}

/**
 * Lineage of the values one task result published, folded under a heading on the result itself;
 * nothing is fetched until it is opened. Renders nothing for a task without outputs. With several
 * outputs, a selector switches between them.
 */
export function TaskLineageSection({
  taskId,
  executionId,
  qid,
  outputParameters,
  className,
}: TaskLineageSectionProps) {
  const targets = useMemo(
    () => publishedParameters(qid, outputParameters),
    [qid, outputParameters],
  );
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const target = targets[Math.min(index, targets.length - 1)];
  if (!target) return null;

  return (
    <details id="lineage" className={`group ${className ?? ""}`} open={open}>
      <summary
        className="flex cursor-pointer list-none items-center justify-between gap-2"
        onClick={(event) => {
          // Controlled so the panel (and its requests) exist only while open.
          event.preventDefault();
          setOpen((current) => !current);
        }}
      >
        <span className="flex items-center gap-1.5 text-xs font-medium text-base-content/60">
          <ChevronRight className="h-3.5 w-3.5 transition-transform group-open:rotate-90" />
          Lineage
          <span className="font-normal">
            · {targets.length} published value{targets.length === 1 ? "" : "s"}
          </span>
        </span>
        {open && targets.length > 1 && (
          <select
            aria-label="Published parameter"
            className="select select-bordered select-xs"
            value={Math.min(index, targets.length - 1)}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => setIndex(Number(event.target.value))}
          >
            {targets.map((candidate, candidateIndex) => (
              <option key={`${candidate.parameterName}:${candidate.qid}`} value={candidateIndex}>
                {candidate.parameterName} ({candidate.qid})
              </option>
            ))}
          </select>
        )}
      </summary>
      {open && (
        <div className="mt-3">
          <ParameterLineagePanel
            key={`${target.parameterName}:${target.qid}:${taskId}`}
            parameterName={target.parameterName}
            qid={target.qid}
            entityId={entityIdFor(target, executionId, taskId)}
            hideInputs
            currentTaskId={taskId}
          />
        </div>
      )}
    </details>
  );
}
