"use client";

import type { ReactNode } from "react";
import NumberFlow, { NumberFlowGroup } from "@number-flow/react";

// Pinned so server and client render the same digits, and so counts keep the plain
// `${n}` form they had before (no locale grouping or alternative numerals).
const LOCALE = "en-US";
const FORMAT = { useGrouping: false } as const;

interface AnimatedNumberProps {
  value: number;
  suffix?: string;
}

/**
 * A live progress or count number whose digits roll to the new value when it changes. Visual
 * only: render it inside `AnimatedText`, which supplies the accessible text. Not for measured
 * physical quantities, which stay static. Honors `prefers-reduced-motion` (NumberFlow default).
 */
export function AnimatedNumber({ value, suffix }: AnimatedNumberProps) {
  return <NumberFlow value={value} locales={LOCALE} format={FORMAT} suffix={suffix} />;
}

interface AnimatedTextProps {
  /** The same phrase as plain text, read by assistive technology and live regions. */
  label: string;
  children: ReactNode;
  className?: string;
}

/**
 * Pairs a phrase containing `AnimatedNumber`s with its plain-text equivalent. The animated copy is
 * hidden from assistive technology so a screen reader reads one coherent phrase, not split digits.
 */
export function AnimatedText({ label, children, className = "" }: AnimatedTextProps) {
  return (
    <span className={className}>
      <span className="sr-only">{label}</span>
      <span aria-hidden="true">
        <NumberFlowGroup>{children}</NumberFlowGroup>
      </span>
    </span>
  );
}
