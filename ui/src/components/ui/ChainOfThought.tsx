"use client";

/**
 * Vertical timeline of agent steps, each one a collapsible row: a marker on
 * the left joined to the next step by a thin line, a one-line trigger, and
 * content that unfolds beneath it.
 *
 * Adapted from prompt-kit's ChainOfThought (https://www.prompt-kit.com, MIT).
 * The collapsible is the Reasoning block from this directory instead of Radix
 * Collapsible, so a step held open by `isStreaming` folds up by itself when
 * the stream ends.
 */

import { Children, isValidElement, cloneElement, type ReactElement, type ReactNode } from "react";
import { twMerge } from "tailwind-merge";

import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
  type ReasoningContentProps,
  type ReasoningProps,
  type ReasoningTriggerProps,
} from "@/components/ui/Reasoning";

export type ChainOfThoughtStepProps = Omit<ReasoningProps, "className"> & {
  /** What sits on the timeline: an icon, a dot, a spinner. */
  marker: ReactNode;
  /** Colors the marker; see `.chain-marker[data-status]` in globals.css. */
  status?: "idle" | "running" | "done" | "error";
  /** Set by ChainOfThought; the last step has no connecting line. */
  isLast?: boolean;
  className?: string;
};

export function ChainOfThoughtStep({
  marker,
  status = "idle",
  isLast = false,
  className,
  children,
  ...reasoning
}: ChainOfThoughtStepProps) {
  return (
    <div className={twMerge("relative flex gap-2.5", className)} data-last={isLast}>
      <div className="flex shrink-0 flex-col items-center">
        <span className="chain-marker" data-status={status}>
          {marker}
        </span>
        {!isLast && <span className="mt-1 w-px flex-1 bg-base-content/12" aria-hidden="true" />}
      </div>
      <Reasoning className={twMerge("min-w-0 flex-1", isLast ? "" : "pb-2")} {...reasoning}>
        {children}
      </Reasoning>
    </div>
  );
}

export function ChainOfThoughtTrigger({ className, ...props }: ReasoningTriggerProps) {
  return <ReasoningTrigger className={twMerge("w-full text-xs", className)} {...props} />;
}

export function ChainOfThoughtContent({ className, ...props }: ReasoningContentProps) {
  return <ReasoningContent className={twMerge("mt-1", className)} {...props} />;
}

/** Lays out its ChainOfThoughtStep children and tells the last one it is last. */
export function ChainOfThought({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const steps = Children.toArray(children).filter(isValidElement);
  return (
    <ol className={twMerge("flex flex-col", className)}>
      {steps.map((step, index) => (
        <li key={step.key ?? index}>
          {cloneElement(step as ReactElement<ChainOfThoughtStepProps>, {
            isLast: index === steps.length - 1,
          })}
        </li>
      ))}
    </ol>
  );
}
