import { SkeletonChart, SkeletonTable } from "./index";

/**
 * Skeleton for Execution page (list view)
 */
export function ExecutionPageSkeleton() {
  return (
    <div className="w-full min-h-screen bg-base-100/50 px-3 sm:px-6 py-4 sm:py-8">
      <div className="max-w-[1800px] mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <div className="skeleton h-8 w-48 mb-2" />
            <div className="skeleton h-4 w-72" />
          </div>
          <div className="flex gap-2">
            <div className="skeleton h-10 w-28 rounded-lg" />
            <div className="skeleton h-10 w-28 rounded-lg" />
          </div>
        </div>

        {/* Filters */}
        <div className="flex gap-4 mb-6">
          <div className="skeleton h-10 w-48 rounded-lg" />
          <div className="skeleton h-10 w-36 rounded-lg" />
          <div className="skeleton h-10 w-36 rounded-lg" />
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
            <div className="skeleton h-8 w-44 mb-2" />
            <div className="skeleton h-4 w-60" />
          </div>
          <div className="flex gap-2">
            <div className="skeleton h-10 w-24 rounded-lg" />
            <div className="skeleton h-10 w-24 rounded-lg" />
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6">
          <div className="skeleton h-9 w-20 rounded-lg" />
          <div className="skeleton h-9 w-20 rounded-lg" />
        </div>

        {/* Metric Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="card bg-base-200 shadow-sm">
              <div className="card-body p-4">
                <div className="skeleton h-5 w-1/2 mb-3" />
                <div className="skeleton h-48 w-full rounded-lg" />
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
            <div className="skeleton h-8 w-36 mb-2" />
            <div className="skeleton h-4 w-48" />
          </div>
          <div className="flex gap-2">
            <div className="skeleton h-10 w-28 rounded-lg" />
          </div>
        </div>

        {/* View Mode Tabs */}
        <div className="flex gap-2 mb-6">
          <div className="skeleton h-9 w-14 rounded-lg" />
          <div className="skeleton h-9 w-14 rounded-lg" />
          <div className="skeleton h-9 w-20 rounded-lg" />
        </div>

        {/* Grid of cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="card bg-base-200 shadow-sm">
              <div className="card-body p-4">
                <div className="flex items-center gap-2 mb-3">
                  <div className="skeleton h-6 w-6 rounded-full" />
                  <div className="skeleton h-4 w-3/5" />
                </div>
                <div className="skeleton h-3.5 w-4/5 mb-2" />
                <div className="skeleton h-3.5 w-1/2" />
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
            <div className="skeleton h-8 w-44 mb-2" />
            <div className="skeleton h-4 w-68" />
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2">
          <div className="skeleton h-10 w-24 rounded-lg" />
          <div className="skeleton h-10 w-24 rounded-lg" />
          <div className="skeleton h-10 w-20 rounded-lg" />
          <div className="skeleton h-10 w-24 rounded-lg" />
        </div>

        {/* Parameter Selection */}
        <div className="card bg-base-200 shadow-sm p-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="skeleton h-10 w-full rounded-lg" />
            <div className="skeleton h-10 w-full rounded-lg" />
            <div className="skeleton h-10 w-full rounded-lg" />
          </div>
        </div>

        {/* Chart */}
        <SkeletonChart height={400} />
      </div>
    </div>
  );
}

/**
 * Skeleton for Workflow list page
 */
export function WorkflowListPageSkeleton() {
  return (
    <div className="container mx-auto p-3 sm:p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-4 sm:mb-6">
        <div className="skeleton h-8 w-40" />
        <div className="skeleton h-10 w-28 rounded-lg" />
      </div>

      {/* Grid of cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="card bg-base-100 shadow-xl">
            <div className="card-body p-4 sm:p-6">
              <div className="skeleton h-6 w-3/4 mb-2" />
              <div className="skeleton h-4 w-full mb-4" />
              <div className="divider my-2" />
              <div className="space-y-2">
                <div className="skeleton h-3 w-2/3" />
                <div className="skeleton h-3 w-1/2" />
                <div className="skeleton h-3 w-3/4" />
              </div>
              <div className="flex gap-1 mt-2">
                <div className="skeleton h-5 w-12 rounded-full" />
                <div className="skeleton h-5 w-16 rounded-full" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Skeleton for Workflow editor page (edit/new)
 */
export function WorkflowEditorPageSkeleton() {
  return (
    <div className="h-screen flex flex-col bg-base-300">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between px-2 sm:px-4 py-2 bg-base-200 border-b border-base-300 gap-2">
        <div className="flex items-center gap-2 sm:gap-4">
          <div className="skeleton h-8 w-8 rounded" />
          <div className="skeleton h-5 w-32" />
        </div>
        <div className="flex items-center gap-2">
          <div className="skeleton h-8 w-16 rounded-lg" />
          <div className="skeleton h-8 w-20 rounded-lg" />
          <div className="skeleton h-8 w-20 rounded-lg" />
        </div>
      </div>

      {/* Main Editor Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Editor */}
        <div className="flex-1 flex flex-col">
          {/* Tab Bar */}
          <div className="flex bg-base-200 border-b border-base-300">
            <div className="skeleton h-10 w-32 m-1 rounded" />
            <div className="skeleton h-10 w-36 m-1 rounded" />
          </div>
          {/* Editor Area */}
          <div className="flex-1 skeleton rounded-none" />
        </div>
      </div>

      {/* Status Bar */}
      <div className="h-6 bg-primary" />
    </div>
  );
}

/**
 * Skeleton for Admin page
 */
export function AdminPageSkeleton() {
  return (
    <div className="w-full px-3 sm:px-6">
      {/* Header */}
      <div className="skeleton h-8 w-48 mb-6" />

      {/* Tabs */}
      <div className="tabs tabs-boxed mb-6 w-fit">
        <div className="skeleton h-10 w-20 mx-1 rounded" />
        <div className="skeleton h-10 w-20 mx-1 rounded" />
        <div className="skeleton h-10 w-20 mx-1 rounded" />
      </div>

      {/* Content Card */}
      <div className="card bg-base-200 shadow-lg">
        <div className="card-body">
          <div className="flex justify-between items-center mb-4">
            <div className="skeleton h-6 w-32" />
            <div className="skeleton h-10 w-28 rounded-lg" />
          </div>
          <SkeletonTable rows={6} columns={5} />
        </div>
      </div>
    </div>
  );
}

/**
 * Skeleton for Editor pages (tasks/files)
 */
export function EditorPageSkeleton() {
  return (
    <div className="h-screen flex flex-col bg-base-300">
      {/* Header */}
      <div className="flex items-center justify-between px-2 sm:px-4 py-2 bg-base-200 border-b border-base-300">
        <div className="flex items-center gap-2 sm:gap-4">
          <div className="skeleton h-8 w-8 rounded" />
          <div className="skeleton h-5 w-40" />
        </div>
        <div className="flex items-center gap-2">
          <div className="skeleton h-8 w-20 rounded-lg" />
          <div className="skeleton h-8 w-20 rounded-lg" />
        </div>
      </div>

      {/* Main Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <div className="w-64 bg-base-100 border-r border-base-300 p-4 hidden sm:block">
          <div className="skeleton h-5 w-24 mb-4" />
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex items-center gap-2">
                <div className="skeleton h-4 w-4" />
                <div
                  className="skeleton h-4"
                  style={{ width: `${60 + Math.random() * 40}%` }}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Editor */}
        <div className="flex-1 skeleton rounded-none" />
      </div>

      {/* Status Bar */}
      <div className="h-6 bg-primary" />
    </div>
  );
}

/**
 * Skeleton for Settings page
 */
export function SettingPageSkeleton() {
  return (
    <div className="w-full px-3 sm:px-6">
      {/* Header */}
      <div className="skeleton h-8 w-32 mb-6" />

      {/* Tabs */}
      <div className="tabs tabs-boxed mb-6 w-fit">
        <div className="skeleton h-10 w-24 mx-1 rounded" />
        <div className="skeleton h-10 w-20 mx-1 rounded" />
        <div className="skeleton h-10 w-24 mx-1 rounded" />
      </div>

      {/* Content Card */}
      <div className="card bg-base-200 shadow-lg">
        <div className="card-body">
          <div className="skeleton h-6 w-36 mb-4" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="skeleton h-10 w-full rounded-lg" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Skeleton for Qubit detail page
 */
export function QubitDetailPageSkeleton() {
  return (
    <div className="w-full px-6 py-6">
      <div className="space-y-6">
        {/* Back navigation */}
        <div className="skeleton h-8 w-36 rounded-lg" />

        {/* Header Section */}
        <div className="flex flex-col lg:flex-row justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="skeleton h-12 w-12 rounded-full" />
            <div>
              <div className="skeleton h-8 w-48 mb-2" />
              <div className="skeleton h-4 w-32" />
            </div>
          </div>
          <div className="flex gap-2">
            <div className="skeleton h-10 w-32 rounded-lg" />
            <div className="skeleton h-10 w-32 rounded-lg" />
          </div>
        </div>

        {/* View Mode Tabs */}
        <div className="flex gap-2">
          <div className="skeleton h-10 w-28 rounded-lg" />
          <div className="skeleton h-10 w-28 rounded-lg" />
          <div className="skeleton h-10 w-20 rounded-lg" />
          <div className="skeleton h-10 w-24 rounded-lg" />
        </div>

        {/* Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card bg-base-200 shadow-sm">
              <div className="card-body p-4">
                <div className="skeleton h-5 w-1/3 mb-3" />
                <div className="skeleton h-48 w-full rounded-lg" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Skeleton for Execution detail page
 */
export function ExecutionDetailPageSkeleton() {
  return (
    <div className="w-full min-h-screen bg-base-100/50 px-3 sm:px-6 py-4 sm:py-8">
      <div className="max-w-[1800px] mx-auto">
        {/* Back navigation */}
        <div className="skeleton h-8 w-36 rounded-lg mb-6" />

        {/* Header */}
        <div className="flex flex-col lg:flex-row justify-between gap-4 mb-6">
          <div>
            <div className="skeleton h-8 w-64 mb-2" />
            <div className="flex gap-4">
              <div className="skeleton h-5 w-32" />
              <div className="skeleton h-5 w-40" />
            </div>
          </div>
          <div className="flex gap-2">
            <div className="skeleton h-10 w-24 rounded-lg" />
            <div className="skeleton h-10 w-24 rounded-lg" />
          </div>
        </div>

        {/* Status Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card bg-base-200 shadow-sm p-4">
              <div className="skeleton h-4 w-20 mb-2" />
              <div className="skeleton h-6 w-16" />
            </div>
          ))}
        </div>

        {/* DAG / Task List */}
        <div className="card bg-base-200 shadow-sm">
          <div className="card-body p-4">
            <div className="flex justify-between items-center mb-4">
              <div className="skeleton h-6 w-32" />
              <div className="flex gap-2">
                <div className="skeleton h-8 w-24 rounded-lg" />
                <div className="skeleton h-8 w-24 rounded-lg" />
              </div>
            </div>
            <div className="skeleton h-96 w-full rounded-lg" />
          </div>
        </div>
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
        <div className="skeleton h-8 w-48 mb-4" />
        <div className="skeleton h-48 w-full rounded-lg" />
        <div className="skeleton h-36 w-full rounded-lg" />
      </div>
    </div>
  );
}
