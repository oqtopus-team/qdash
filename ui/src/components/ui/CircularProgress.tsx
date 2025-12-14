"use client";

import { useEffect, useState } from "react";
import { FluentEmoji } from "./FluentEmoji";

interface CircularProgressProps {
  value: number; // 0-100
  size?: number;
  strokeWidth?: number;
  showLabel?: boolean;
  label?: string;
  sublabel?: string;
  duration?: number;
  className?: string;
}

export function CircularProgress({
  value,
  size = 120,
  strokeWidth = 8,
  showLabel = true,
  label,
  sublabel,
  duration = 800,
  className = "",
}: CircularProgressProps) {
  const [animatedValue, setAnimatedValue] = useState(0);

  // Animate value on change
  useEffect(() => {
    const startValue = animatedValue;
    const endValue = Math.min(100, Math.max(0, value));
    const startTime = performance.now();

    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);

      // Easing function (ease-out)
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = startValue + (endValue - startValue) * eased;

      setAnimatedValue(current);

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };

    requestAnimationFrame(animate);
  }, [value, duration]);

  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (animatedValue / 100) * circumference;

  // Color based on value
  const getColor = (val: number) => {
    if (val >= 95) return "stroke-success";
    if (val >= 80) return "stroke-info";
    if (val >= 50) return "stroke-warning";
    return "stroke-error";
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

  return (
    <div className={`flex flex-col items-center ${className}`}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg className="transform -rotate-90" width={size} height={size}>
          {/* Background circle */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            className="text-base-300"
          />
          {/* Progress circle */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            className={`${getColor(animatedValue)} transition-colors duration-300`}
            style={{
              strokeDasharray: circumference,
              strokeDashoffset: offset,
              transition: "stroke-dashoffset 0.1s ease-out",
            }}
          />
        </svg>

        {/* Center content */}
        {showLabel && (
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span
              className={`text-2xl font-bold ${getTextColor(animatedValue)}`}
            >
              {animatedValue.toFixed(1)}%
            </span>
            {label && (
              <span className="text-xs text-base-content/60">{label}</span>
            )}
          </div>
        )}
      </div>

      {/* Badge */}
      {badge && (
        <div className="mt-2 flex items-center gap-1">
          <FluentEmoji name={badge.emoji} size={20} />
          <span className="text-xs font-medium text-base-content/70">
            {badge.text}
          </span>
        </div>
      )}

      {/* Sublabel */}
      {sublabel && (
        <span className="text-xs text-base-content/60 mt-1">{sublabel}</span>
      )}
    </div>
  );
}
