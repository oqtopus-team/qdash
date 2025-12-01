"use client";

import Select from "react-select";

import type { SingleValue } from "react-select";

interface QIDOption {
  value: string;
  label: string;
}

interface QIDSelectorProps {
  qids: string[];
  selectedQid: string;
  onQidSelect: (qid: string) => void;
  disabled?: boolean;
}

export function QIDSelector({
  qids,
  selectedQid,
  onQidSelect,
  disabled = false,
}: QIDSelectorProps) {
  const options: QIDOption[] = qids.map((qid) => ({
    value: qid,
    label: `Q${qid}`,
  }));

  const handleChange = (option: SingleValue<QIDOption>) => {
    if (option) {
      onQidSelect(option.value);
    }
  };

  return (
    <Select<QIDOption>
      options={options}
      value={options.find((option) => option.value === selectedQid)}
      onChange={handleChange}
      placeholder="Select QID"
      className="text-base-content w-full"
      isDisabled={disabled}
    />
  );
}
