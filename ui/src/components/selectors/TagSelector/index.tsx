"use client";

import Select from "react-select";

import { useSelectStyles } from "@/hooks/useSelectStyles";

import type { Tag } from "@/schemas/tag";
import type { SingleValue } from "react-select";

interface TagOption {
  value: string;
  label: string;
}

interface TagSelectorProps {
  tags: Tag[];
  selectedTag: string;
  onTagSelect: (tagId: string) => void;
  disabled?: boolean;
}

export function TagSelector({
  tags,
  selectedTag,
  onTagSelect,
  disabled = false,
}: TagSelectorProps) {
  const styles = useSelectStyles<TagOption>();
  const options: TagOption[] = tags.map((tag) => ({
    value: tag.name,
    label: tag.name,
  }));

  const handleChange = (option: SingleValue<TagOption>) => {
    onTagSelect(option ? option.value : "");
  };

  return (
    <Select<TagOption>
      styles={styles}
      isClearable
      options={options}
      value={options.find((option) => option.value === selectedTag) ?? null}
      onChange={handleChange}
      placeholder="Select tag"
      className="text-base-content w-full"
      isDisabled={disabled}
    />
  );
}
