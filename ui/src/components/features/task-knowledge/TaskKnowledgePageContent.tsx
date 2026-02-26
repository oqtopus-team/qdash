"use client";

import React, { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  X,
  AlertTriangle,
  BookOpen,
  Image as ImageIcon,
  FileText,
} from "lucide-react";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { useListTaskKnowledge } from "@/client/task/task";
import type { TaskKnowledgeSummaryResponse } from "@/schemas";

// Category order for display
const CATEGORY_ORDER = [
  "box-setup",
  "system",
  "cw-characterization",
  "td-characterization",
  "one-qubit-gate-calibration",
  "two-qubit-gate-calibration",
  "benchmarking",
];

function TaskCard({ item }: { item: TaskKnowledgeSummaryResponse }) {
  const router = useRouter();

  return (
    <div
      onClick={() => router.push(`/task-knowledge/${item.name}`)}
      className="bg-base-100 rounded-lg border border-base-300 cursor-pointer hover:border-primary/50 transition-colors"
    >
      <div className="p-4">
        <h3 className="text-sm font-semibold font-mono text-primary mb-1">
          {item.name}
        </h3>
        <p className="text-sm text-base-content/70 line-clamp-2 mb-2">
          {item.summary}
        </p>
        <div className="flex items-center gap-3 text-xs text-base-content/50">
          {(item.failure_mode_count ?? 0) > 0 && (
            <span className="flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" />
              {item.failure_mode_count} failure modes
            </span>
          )}
          {(item.case_count ?? 0) > 0 && (
            <span className="flex items-center gap-1">
              <FileText className="h-3 w-3" />
              {item.case_count} cases
            </span>
          )}
          {(item.image_count ?? 0) > 0 && (
            <span className="flex items-center gap-1">
              <ImageIcon className="h-3 w-3" />
              {item.image_count} images
            </span>
          )}
          {item.has_analysis_guide && (
            <span className="flex items-center gap-1">
              <BookOpen className="h-3 w-3" />
              Guide
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function TaskKnowledgePageContent() {
  const { data: resp, isLoading } = useListTaskKnowledge();
  const [searchInput, setSearchInput] = useState("");

  const categories = resp?.data?.categories ?? {};

  const filtered = useMemo(() => {
    const items = resp?.data?.items ?? [];
    if (!searchInput.trim()) return items;
    const q = searchInput.toLowerCase();
    return items.filter(
      (item) =>
        item.name.toLowerCase().includes(q) ||
        item.summary.toLowerCase().includes(q),
    );
  }, [resp?.data?.items, searchInput]);

  // Group by category
  const grouped = useMemo(() => {
    const map = new Map<string, TaskKnowledgeSummaryResponse[]>();
    for (const item of filtered) {
      const cat = item.category ?? "";
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(item);
    }
    // Sort by predefined order
    const sorted = new Map<string, TaskKnowledgeSummaryResponse[]>();
    for (const cat of CATEGORY_ORDER) {
      if (map.has(cat)) {
        sorted.set(cat, map.get(cat)!);
        map.delete(cat);
      }
    }
    // Append any remaining categories
    for (const [cat, catItems] of map) {
      sorted.set(cat, catItems);
    }
    return sorted;
  }, [filtered]);

  return (
    <PageContainer maxWidth>
      <PageHeader
        title="Task Knowledge"
        description="Calibration task knowledge base — physics, expected results, failure patterns, and analysis guides"
      />

      {/* Search bar */}
      <div className="mb-6">
        <div className="relative max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-base-content/40" />
          <input
            type="text"
            className="input input-bordered input-sm w-full pl-9 pr-8"
            placeholder="Search tasks..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
          {searchInput && (
            <button
              type="button"
              onClick={() => setSearchInput("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 btn btn-ghost btn-xs p-0 h-auto min-h-0"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex justify-center py-16">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No task knowledge found"
          description={
            searchInput
              ? "No tasks match your search."
              : "No task knowledge entries available. Run 'task knowledge-pull' to fetch."
          }
          emoji="brain"
        />
      ) : (
        <div className="space-y-8">
          {Array.from(grouped.entries()).map(([category, catItems]) => (
            <div key={category}>
              <h2 className="text-base font-semibold mb-3">
                {categories[category] || category || "Other"}
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {catItems.map((item) => (
                  <TaskCard key={item.name} item={item} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </PageContainer>
  );
}
