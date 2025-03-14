"use client";

import Select, { SingleValue } from "react-select";

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
    label: `QID: ${qid}`,
  }));

  const handleChange = (option: SingleValue<QIDOption>) => {
    if (option) {
      onQidSelect(option.value);
    }
  };

  return (
    <div className="form-control">
      <label className="label font-medium">QID</label>
      <Select<QIDOption>
        options={options}
        value={options.find((option) => option.value === selectedQid)}
        onChange={handleChange}
        placeholder="Select QID"
        className="text-base-content"
        isDisabled={disabled}
      />
    </div>
  );
}
