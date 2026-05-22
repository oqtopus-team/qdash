"use client";

import { useEffect, useMemo, useState } from "react";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { useListChips } from "@/client/chip/chip";
import { useListExecutions } from "@/client/execution/execution";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { DateSelector } from "@/components/selectors/DateSelector";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";
import { PageHeader } from "@/components/ui/PageHeader";
import { ExecutionPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useDateNavigation } from "@/hooks/useDateNavigation";
import { useExecutionUrlState } from "@/hooks/useUrlState";
import { formatDate } from "@/lib/utils/datetime";

import { ExecutionDurationBreakdown } from "./ExecutionDurationBreakdown";

function PaginationControls({
  currentPage,
  setCurrentPage,
  hasMore,
}: {
  currentPage: number;
  setCurrentPage: React.Dispatch<React.SetStateAction<number>>;
  hasMore: boolean;
}) {
  return (
    <div className="flex items-center justify-center gap-2 sm:gap-4">
      <button
        onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
        disabled={currentPage === 1}
        className="btn btn-sm btn-outline"
      >
        Prev
      </button>
      <span className="text-sm text-base-content/70">Execution page {currentPage}</span>
      <button
        onClick={() => setCurrentPage((prev) => prev + 1)}
        disabled={!hasMore}
        className="btn btn-sm btn-outline"
      >
        Next
      </button>
    </div>
  );
}

export function ExecutionDurationBreakdownPageContent() {
  const { selectedChip, setSelectedChip, isInitialized } = useExecutionUrlState();
  const [selectedDate, setSelectedDate] = useState<string>("latest");
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 100;

  useDateNavigation(selectedChip || "", selectedDate, setSelectedDate);

  const { data: chipsData } = useListChips();

  const sortedChips = useMemo(() => {
    if (!chipsData?.data?.chips) return [];
    return [...chipsData.data.chips].sort((a, b) => {
      const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
      const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
      return dateB - dateA;
    });
  }, [chipsData?.data?.chips]);

  useEffect(() => {
    if (isInitialized && !selectedChip && sortedChips.length > 0) {
      setSelectedChip(sortedChips[0].chip_id);
    }
  }, [isInitialized, selectedChip, sortedChips, setSelectedChip]);

  const {
    data: executionData,
    isError,
    isLoading,
  } = useListExecutions(
    {
      chip_id: selectedChip || "",
      skip: (currentPage - 1) * itemsPerPage,
      limit: itemsPerPage,
    },
    {
      query: {
        refetchInterval: 5000,
        refetchIntervalInBackground: true,
        enabled: !!selectedChip,
      },
    },
  );

  const analyzedExecutions = useMemo(() => {
    if (!executionData?.data?.executions) return [];
    if (selectedDate === "latest") return executionData.data.executions;
    return executionData.data.executions.filter((exec) => {
      if (!exec.start_at) return false;
      const execDateStr = formatDate(exec.start_at).replace(/-/g, "");
      return execDateStr === selectedDate;
    });
  }, [executionData, selectedDate]);

  const handleChipChange = (chipId: string) => {
    setSelectedChip(chipId || null);
    setCurrentPage(1);
  };

  const handleDateChange = (date: string) => {
    setSelectedDate(date);
    setCurrentPage(1);
  };

  const hasMorePages =
    !!executionData?.data?.executions && executionData.data.executions.length >= itemsPerPage;

  if (isLoading) return <ExecutionPageSkeleton />;

  return (
    <PageContainer>
      <PageHeader
        title="Task Duration Breakdown"
        description="Analyze which tasks consume execution time across the selected executions."
        actions={
          <Link href="/execution" className="btn btn-ghost btn-sm w-full gap-2 sm:w-auto">
            <ArrowLeft className="h-4 w-4" />
            Back to Executions
          </Link>
        }
      />

      <PageFiltersBar className="mb-4 sm:mb-6">
        <PageFiltersBar.Group>
          <PageFiltersBar.Item>
            <ChipSelector selectedChip={selectedChip || ""} onChipSelect={handleChipChange} />
          </PageFiltersBar.Item>
          <PageFiltersBar.Item>
            <DateSelector
              chipId={selectedChip || ""}
              selectedDate={selectedDate}
              onDateSelect={handleDateChange}
              disabled={!selectedChip}
            />
          </PageFiltersBar.Item>
        </PageFiltersBar.Group>
      </PageFiltersBar>

      {isError ? (
        <div className="rounded-lg border border-error/30 bg-error/5 p-4 text-sm text-error">
          Failed to load executions.
        </div>
      ) : (
        <>
          <ExecutionDurationBreakdown
            executions={analyzedExecutions}
            selectedTag={selectedTag}
            onTagSelect={setSelectedTag}
            maxItems={0}
            padded={false}
          />
          <PaginationControls
            currentPage={currentPage}
            setCurrentPage={setCurrentPage}
            hasMore={hasMorePages}
          />
        </>
      )}
    </PageContainer>
  );
}
