"use client";

import { useEffect, useRef, useState } from "react";

interface AnimatedCounterProps {
  /** Target value to count to */
  value: number;
  /** Duration of animation in ms (default: 1000) */
  duration?: number;
  /** Decimal places to show (default: 0) */
  decimals?: number;
  /** Prefix string (e.g., "$") */
  prefix?: string;
  /** Suffix string (e.g., "%") */
  suffix?: string;
  /** Format number with locale (default: true) */
  useLocale?: boolean;
  /** Additional CSS classes */
  className?: string;
  /** Easing function */
  easing?: "linear" | "easeOut" | "easeInOut";
}

// Easing functions
const easingFunctions = {
  linear: (t: number) => t,
  easeOut: (t: number) => 1 - Math.pow(1 - t, 3),
  easeInOut: (t: number) =>
    t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2,
};

/**
 * Animated counter that counts up to a target value
 */
export function AnimatedCounter({
  value,
  duration = 1000,
  decimals = 0,
  prefix = "",
  suffix = "",
  useLocale = true,
  className = "",
  easing = "easeOut",
}: AnimatedCounterProps) {
  const [displayValue, setDisplayValue] = useState(0);
  const previousValueRef = useRef(0);
  const animationRef = useRef<number>();
  const startTimeRef = useRef<number>();

  useEffect(() => {
    const startValue = previousValueRef.current;
    const endValue = value;
    const easingFn = easingFunctions[easing];

    const animate = (timestamp: number) => {
      if (!startTimeRef.current) {
        startTimeRef.current = timestamp;
      }

      const elapsed = timestamp - startTimeRef.current;
      const progress = Math.min(elapsed / duration, 1);
      const easedProgress = easingFn(progress);

      const currentValue = startValue + (endValue - startValue) * easedProgress;
      setDisplayValue(currentValue);

      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate);
      } else {
        previousValueRef.current = endValue;
      }
    };

    // Reset start time for new animation
    startTimeRef.current = undefined;
    animationRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [value, duration, easing]);

  const formatNumber = (num: number): string => {
    const fixed = num.toFixed(decimals);
    if (useLocale) {
      return parseFloat(fixed).toLocaleString(undefined, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      });
    }
    return fixed;
  };

  return (
    <span className={`tabular-nums ${className}`}>
      {prefix}
      {formatNumber(displayValue)}
      {suffix}
    </span>
  );
}

/**
 * Animated percentage display
 */
export function AnimatedPercentage({
  value,
  duration = 1000,
  decimals = 1,
  className = "",
}: Omit<AnimatedCounterProps, "prefix" | "suffix">) {
  return (
    <AnimatedCounter
      value={value}
      duration={duration}
      decimals={decimals}
      suffix="%"
      className={className}
    />
  );
}
