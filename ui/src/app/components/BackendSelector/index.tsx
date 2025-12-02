"use client";

import { useMemo } from "react";

import Select from "react-select";

import type { SingleValue } from "react-select";

import { useListBackends } from "@/client/backend/backend";

interface BackendOption {
  value: string;
  label: string;
}

interface BackendSelectorProps {
  selectedBackend: string | null;
  onBackendSelect: (backend: string | null) => void;
}

export function BackendSelector({
  selectedBackend,
  onBackendSelect,
}: BackendSelectorProps) {
  const { data: backends, isLoading, isError } = useListBackends();

  const options = useMemo(() => {
    if (!backends?.data?.backends) return [];

    return [
      { value: "", label: "All Backends" },
      ...backends.data.backends.map((backend) => ({
        value: backend.name,
        label: backend.name,
      })),
    ];
  }, [backends]);

  if (isLoading) {
    return (
      <div className="w-48 animate-pulse">
        <div className="h-8 bg-base-300 rounded-lg"></div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="alert alert-error w-48">
        <span>Failed to load backends</span>
      </div>
    );
  }

  const handleChange = (option: SingleValue<BackendOption>) => {
    onBackendSelect(option?.value || null);
  };

  return (
    <Select<BackendOption>
      options={options}
      value={options.find((option) => option.value === (selectedBackend || ""))}
      onChange={handleChange}
      placeholder="Select a backend"
      className="w-48 text-base-content"
      classNamePrefix="backend-select"
      isSearchable={true}
      isClearable={false}
    />
  );
}
