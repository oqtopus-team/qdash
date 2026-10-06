"use client";

/**
 * Small loading indicators for chat surfaces.
 *
 * Adapted from prompt-kit's Loader (https://www.prompt-kit.com, MIT), with the
 * shadcn color variables replaced by DaisyUI theme tokens and the keyframes
 * kept in globals.css (`loader-*`). Variants are the ones chat products use:
 * three bouncing dots before the first token, a shimmering status label while
 * tools run, and small spinners for inline waits.
 */

import { twMerge } from "tailwind-merge";

type LoaderVariant =
  | "circular"
  | "pulse-dot"
  | "dots"
  | "typing"
  | "wave"
  | "text-shimmer"
  | "loading-dots";

type LoaderSize = "sm" | "md" | "lg";

export interface LoaderProps {
  variant?: LoaderVariant;
  size?: LoaderSize;
  /** Label for the text variants. */
  text?: string;
  className?: string;
}

const BOX: Record<LoaderSize, string> = { sm: "size-4", md: "size-5", lg: "size-6" };
const ROW: Record<LoaderSize, string> = { sm: "h-4", md: "h-5", lg: "h-6" };
const TEXT: Record<LoaderSize, string> = { sm: "text-xs", md: "text-sm", lg: "text-base" };

function CircularLoader({ className, size }: { className?: string; size: LoaderSize }) {
  return (
    <div
      className={twMerge(
        "animate-spin rounded-full border-2 border-primary border-t-transparent",
        BOX[size],
        className,
      )}
      role="status"
    >
      <span className="sr-only">Loading</span>
    </div>
  );
}

function PulseDotLoader({ className, size }: { className?: string; size: LoaderSize }) {
  const dot = { sm: "size-1", md: "size-2", lg: "size-3" }[size];
  return (
    <div
      className={twMerge(
        "rounded-full bg-primary animate-[loader-pulse-dot_1.2s_ease-in-out_infinite]",
        dot,
        className,
      )}
      role="status"
    >
      <span className="sr-only">Loading</span>
    </div>
  );
}

function DotsLoader({
  className,
  size,
  keyframes,
  delayMs,
}: {
  className?: string;
  size: LoaderSize;
  keyframes: string;
  delayMs: number;
}) {
  const dot = { sm: "size-1.5", md: "size-2", lg: "size-2.5" }[size];
  return (
    <div className={twMerge("flex items-center gap-1", ROW[size], className)} role="status">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className={twMerge("rounded-full bg-primary", dot)}
          style={{ animation: keyframes, animationDelay: `${i * delayMs}ms` }}
        />
      ))}
      <span className="sr-only">Loading</span>
    </div>
  );
}

function WaveLoader({ className, size }: { className?: string; size: LoaderSize }) {
  const heights = {
    sm: ["6px", "9px", "12px", "9px", "6px"],
    md: ["8px", "12px", "16px", "12px", "8px"],
    lg: ["10px", "15px", "20px", "15px", "10px"],
  }[size];
  const width = size === "lg" ? "w-1" : "w-0.5";
  return (
    <div className={twMerge("flex items-center gap-0.5", ROW[size], className)} role="status">
      {heights.map((height, i) => (
        <div
          key={i}
          className={twMerge("rounded-full bg-primary", width)}
          style={{
            height,
            animation: "loader-wave 1s ease-in-out infinite",
            animationDelay: `${i * 100}ms`,
          }}
        />
      ))}
      <span className="sr-only">Loading</span>
    </div>
  );
}

function TextShimmerLoader({
  text,
  className,
  size,
}: {
  text: string;
  className?: string;
  size: LoaderSize;
}) {
  return (
    <div className={twMerge("loader-text-shimmer font-medium", TEXT[size], className)}>{text}</div>
  );
}

function TextDotsLoader({
  text,
  className,
  size,
}: {
  text: string;
  className?: string;
  size: LoaderSize;
}) {
  return (
    <div className={twMerge("inline-flex items-center font-medium", TEXT[size], className)}>
      <span>{text}</span>
      <span className="inline-flex" aria-hidden="true">
        {[0.2, 0.4, 0.6].map((delay) => (
          <span key={delay} style={{ animation: `loader-blink 1.4s ${delay}s infinite` }}>
            .
          </span>
        ))}
      </span>
    </div>
  );
}

export function Loader({
  variant = "dots",
  size = "md",
  text = "Thinking",
  className,
}: LoaderProps) {
  switch (variant) {
    case "circular":
      return <CircularLoader size={size} className={className} />;
    case "pulse-dot":
      return <PulseDotLoader size={size} className={className} />;
    case "typing":
      return (
        <DotsLoader
          size={size}
          className={className}
          keyframes="loader-typing 1s infinite"
          delayMs={250}
        />
      );
    case "wave":
      return <WaveLoader size={size} className={className} />;
    case "text-shimmer":
      return <TextShimmerLoader text={text} size={size} className={className} />;
    case "loading-dots":
      return <TextDotsLoader text={text} size={size} className={className} />;
    case "dots":
    default:
      return (
        <DotsLoader
          size={size}
          className={className}
          keyframes="loader-bounce-dots 1.4s ease-in-out infinite"
          delayMs={160}
        />
      );
  }
}
