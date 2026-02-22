"use client";

type QuantumLoaderProps = {
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
  label?: string;
};

/**
 * Quantum-themed loading spinner that visualizes quantum superposition
 * with orbiting particles around a pulsing core.
 */
export function QuantumLoader({
  size = "md",
  showLabel = false,
  label = "Loading...",
}: QuantumLoaderProps) {
  const sizeClasses = {
    sm: "w-10 h-10",
    md: "w-16 h-16",
    lg: "w-24 h-24",
  };

  const coreSize = {
    sm: "w-3 h-3 -ml-1.5 -mt-1.5",
    md: "w-4 h-4 -ml-2 -mt-2",
    lg: "w-6 h-6 -ml-3 -mt-3",
  };

  const orbitSize = {
    sm: "w-1.5 h-1.5 -ml-[3px] -mt-[3px]",
    md: "w-2 h-2 -ml-1 -mt-1",
    lg: "w-3 h-3 -ml-1.5 -mt-1.5",
  };

  return (
    <div className="flex flex-col items-center justify-center gap-3">
      <div className={`quantum-loader ${sizeClasses[size]}`}>
        {/* Outer rings */}
        <div className="quantum-loader-ring" />
        <div className="quantum-loader-ring" />

        {/* Central core with pulse */}
        <div className={`quantum-loader-core ${coreSize[size]}`} />

        {/* Orbiting particles */}
        <div
          className={`quantum-loader-orbit quantum-loader-orbit-1 ${orbitSize[size]}`}
        />
        <div
          className={`quantum-loader-orbit quantum-loader-orbit-2 ${orbitSize[size]}`}
        />
        <div
          className={`quantum-loader-orbit quantum-loader-orbit-3 ${orbitSize[size]}`}
        />
      </div>

      {showLabel && (
        <span className="text-sm text-base-content/70 animate-pulse">
          {label}
        </span>
      )}
    </div>
  );
}
