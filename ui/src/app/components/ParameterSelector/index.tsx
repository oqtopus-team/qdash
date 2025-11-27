"use client";

import Select from "react-select";

import type { SingleValue } from "react-select";

interface ParameterOption {
  value: string;
  label: string;
}

interface ParameterSelectorProps {
  parameters: string[];
  selectedParameter: string;
  onParameterSelect: (parameter: string) => void;
  disabled?: boolean;
}

export function ParameterSelector({
  parameters,
  selectedParameter,
  onParameterSelect,
  disabled = false,
}: ParameterSelectorProps) {
  const options: ParameterOption[] = parameters.map((param) => ({
    value: param,
    label: param,
  }));

  const handleChange = (option: SingleValue<ParameterOption>) => {
    if (option) {
      onParameterSelect(option.value);
    }
  };

  return (
    <Select<ParameterOption>
      options={options}
      value={options.find((option) => option.value === selectedParameter)}
      onChange={handleChange}
      placeholder="Select parameter"
      className="text-base-content w-full"
      isDisabled={disabled}
    />
  );
}
