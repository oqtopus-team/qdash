"use client";

import { Skeleton, SkeletonChart, SkeletonTable } from "./index";

/**
 * Skeleton for Execution page
 */
export function ExecutionPageSkeleton() {
  return (
    <div className="w-full min-h-screen bg-base-100/50 px-3 sm:px-6 py-4 sm:py-8">
      <div className="max-w-[1800px] mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <Skeleton variant="text" height={32} width={200} className="mb-2" />
            <Skeleton variant="text" height={16} width={300} />
          </div>
          <div className="flex gap-2">
            <Skeleton variant="rounded" height={40} width={120} />
            <Skeleton variant="rounded" height={40} width={120} />
          </div>
        </div>

        {/* Filters */}
        <div className="flex gap-4 mb-6">
          <Skeleton variant="rounded" height={40} width={200} />
          <Skeleton variant="rounded" height={40} width={150} />
          <Skeleton variant="rounded" height={40} width={150} />
        </div>

        {/* Table */}
        <SkeletonTable rows={8} columns={6} />
      </div>
    </div>
  );
}

/**
 * Skeleton for Metrics page
 */
export function MetricsPageSkeleton() {
  return (
    <div className="w-full min-h-screen bg-base-100/50 px-3 sm:px-6 py-4 sm:py-8">
      <div className="max-w-[1800px] mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <Skeleton variant="text" height={32} width={180} className="mb-2" />
            <Skeleton variant="text" height={16} width={250} />
          </div>
          <div className="flex gap-2">
            <Skeleton variant="rounded" height={40} width={100} />
            <Skeleton variant="rounded" height={40} width={100} />
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6">
          <Skeleton variant="rounded" height={36} width={80} />
          <Skeleton variant="rounded" height={36} width={80} />
        </div>

        {/* Metric Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="card bg-base-200 shadow-sm">
              <div className="card-body p-4">
                <Skeleton
                  variant="text"
                  height={20}
                  width="50%"
                  className="mb-3"
                />
                <Skeleton variant="rounded" height={200} className="w-full" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Skeleton for Chip page
 */
export function ChipPageSkeleton() {
  return (
    <div className="w-full min-h-screen bg-base-100/50 px-3 sm:px-6 py-4 sm:py-8">
      <div className="max-w-[1800px] mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <Skeleton variant="text" height={32} width={150} className="mb-2" />
            <Skeleton variant="text" height={16} width={200} />
          </div>
          <div className="flex gap-2">
            <Skeleton variant="rounded" height={40} width={120} />
          </div>
        </div>

        {/* View Mode Tabs */}
        <div className="flex gap-2 mb-6">
          <Skeleton variant="rounded" height={36} width={60} />
          <Skeleton variant="rounded" height={36} width={60} />
          <Skeleton variant="rounded" height={36} width={80} />
        </div>

        {/* Grid of cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="card bg-base-200 shadow-sm">
              <div className="card-body p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Skeleton variant="circular" width={24} height={24} />
                  <Skeleton variant="text" height={18} width="60%" />
                </div>
                <Skeleton
                  variant="text"
                  height={14}
                  width="80%"
                  className="mb-2"
                />
                <Skeleton variant="text" height={14} width="50%" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Skeleton for Analysis page
 */
export function AnalysisPageSkeleton() {
  return (
    <div className="w-full min-h-screen bg-base-100/50 px-3 sm:px-6 py-4 sm:py-8">
      <div className="max-w-[1400px] mx-auto space-y-4 sm:space-y-8">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <Skeleton variant="text" height={32} width={180} className="mb-2" />
            <Skeleton variant="text" height={16} width={280} />
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2">
          <Skeleton variant="rounded" height={40} width={100} />
          <Skeleton variant="rounded" height={40} width={100} />
          <Skeleton variant="rounded" height={40} width={80} />
          <Skeleton variant="rounded" height={40} width={100} />
        </div>

        {/* Parameter Selection */}
        <div className="card bg-base-200 shadow-sm p-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Skeleton variant="rounded" height={40} className="w-full" />
            <Skeleton variant="rounded" height={40} className="w-full" />
            <Skeleton variant="rounded" height={40} className="w-full" />
          </div>
        </div>

        {/* Chart */}
        <SkeletonChart height={400} />
      </div>
    </div>
  );
}

/**
 * Generic page skeleton
 */
export function GenericPageSkeleton() {
  return (
    <div className="w-full flex justify-center py-12">
      <div className="w-full max-w-4xl px-4 space-y-6">
        <Skeleton variant="text" height={32} width={200} className="mb-4" />
        <Skeleton variant="rounded" height={200} className="w-full" />
        <Skeleton variant="rounded" height={150} className="w-full" />
      </div>
    </div>
  );
}
