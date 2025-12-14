"use client";

import { useEffect, useState } from "react";
import { FluentEmoji } from "./FluentEmoji";

interface LinearGaugeProps {
  value: number; // 0-100
  current: number;
  total: number;
  duration?: number;
  className?: string;
  label?: string;
}

export function LinearGauge({
  value,
  current,
  total,
  duration = 800,
  className = "",
  label = "Data Coverage",
}: LinearGaugeProps) {
  const [animatedValue, setAnimatedValue] = useState(0);

  useEffect(() => {
    const startValue = animatedValue;
    const endValue = Math.min(100, Math.max(0, value));
    const startTime = performance.now();

    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const currentVal = startValue + (endValue - startValue) * eased;

      setAnimatedValue(currentVal);

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };

    requestAnimationFrame(animate);
  }, [value, duration]);

  // Color based on value
  const getBarColor = (val: number) => {
    if (val >= 95) return "bg-success";
    if (val >= 80) return "bg-info";
    if (val >= 50) return "bg-warning";
    return "bg-error";
  };

  const getTextColor = (val: number) => {
    if (val >= 95) return "text-success";
    if (val >= 80) return "text-info";
    if (val >= 50) return "text-warning";
    return "text-error";
  };

  const getBadge = (val: number): { emoji: string; text: string } | null => {
    if (val >= 100) return { emoji: "crystal", text: "Perfect" };
    if (val >= 95) return { emoji: "medal-gold", text: "Gold" };
    if (val >= 80) return { emoji: "medal-silver", text: "Silver" };
    if (val >= 50) return { emoji: "medal-bronze", text: "Bronze" };
    return null;
  };

  const badge = getBadge(animatedValue);
  const remaining = total - current;

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <span className="text-xs text-base-content/60 whitespace-nowrap">
        {label}
      </span>

      {/* Gauge bar */}
      <div className="flex-1 h-2 bg-base-300 rounded-full overflow-hidden min-w-24 max-w-32">
        <div
          className={`h-full rounded-full transition-all duration-100 ${getBarColor(animatedValue)}`}
          style={{ width: `${animatedValue}%` }}
        />
      </div>

      {/* Percentage and count */}
      <span
        className={`text-sm font-bold whitespace-nowrap ${getTextColor(animatedValue)}`}
      >
        {animatedValue.toFixed(1)}%
      </span>
      <span className="text-xs text-base-content/50 whitespace-nowrap">
        ({current}/{total})
      </span>

      {/* Badge or remaining */}
      {current === 0 ? (
        <span className="text-xs text-base-content/40 whitespace-nowrap">
          No data
        </span>
      ) : badge ? (
        <span className="flex items-center gap-1">
          <FluentEmoji name={badge.emoji} size={16} />
        </span>
      ) : (
        <span className="flex items-center gap-1 text-xs text-base-content/50 whitespace-nowrap">
          <FluentEmoji name="target" size={14} />
          {remaining} to go
        </span>
      )}
    </div>
  );
}
