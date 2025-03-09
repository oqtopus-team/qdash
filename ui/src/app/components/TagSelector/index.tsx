"use client";

import Select, { SingleValue } from "react-select";
import { Tag } from "@/schemas/tag";

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
  const options: TagOption[] = tags.map((tag) => ({
    value: tag.name,
    label: tag.name,
  }));

  const handleChange = (option: SingleValue<TagOption>) => {
    if (option) {
      onTagSelect(option.value);
    }
  };

  return (
    <div className="form-control">
      <label className="label font-medium">Tag</label>
      <Select<TagOption>
        options={options}
        value={options.find((option) => option.value === selectedTag)}
        onChange={handleChange}
        placeholder="Select tag"
        className="text-base-content"
        isDisabled={disabled}
      />
    </div>
  );
}
