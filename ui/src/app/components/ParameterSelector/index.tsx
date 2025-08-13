"use client";

import Select from "react-select";

import type { SingleValue } from "react-select";

interface ParameterOption {
  value: string;
  label: string;
  description?: string;
}

interface ParameterSelectorProps {
  label: string;
  parameters: string[];
  selectedParameter: string;
  onParameterSelect: (parameter: string) => void;
  description?: string;
  disabled?: boolean;
}

export function ParameterSelector({
  label,
  parameters,
  selectedParameter,
  onParameterSelect,
  description,
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
    <div className="form-control">
      <label className="label font-medium">{label}</label>
      <Select<ParameterOption>
        options={options}
        value={options.find((option) => option.value === selectedParameter)}
        onChange={handleChange}
        placeholder="Select parameter"
        className="text-base-content"
        isDisabled={disabled}
      />
      {description && (
        <label className="label">
          <span className="label-text-alt text-base-content/70">
            {description}
          </span>
        </label>
      )}
    </div>
  );
}
