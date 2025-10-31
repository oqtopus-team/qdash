import { useEffect, useMemo, useState } from "react";

import Select, { type SingleValue, type StylesConfig } from "react-select";

import type { BatchNode } from "@/schemas/batchNode";
import type { CreateMenuRequestSchedule } from "@/schemas/createMenuRequestSchedule";
import type { ParallelNode } from "@/schemas/parallelNode";
import type { SerialNode } from "@/schemas/serialNode";

type Block = {
  type: "serial" | "batch";
  tasks: string;
};

type BlockTypeOption = {
  value: "serial" | "batch";
  label: string;
};

const isSerialNode = (node: any): node is SerialNode =>
  typeof node === "object" && "serial" in node;

const isBatchNode = (node: any): node is BatchNode =>
  typeof node === "object" && "batch" in node;

const parseNode = (
  node: SerialNode | ParallelNode | BatchNode | string,
): Block => {
  if (typeof node === "string") {
    return { type: "serial", tasks: node };
  }
  if (isSerialNode(node)) {
    return { type: "serial", tasks: node.serial.join(", ") };
  }
  if (isBatchNode(node)) {
    return { type: "batch", tasks: node.batch.join(", ") };
  }
  return { type: "serial", tasks: "" };
};

type ScheduleInputProps = {
  value: CreateMenuRequestSchedule;
  onChange: (schedule: CreateMenuRequestSchedule) => void;
};

export function ScheduleInput({ value, onChange }: ScheduleInputProps) {
  const [isParallel, setIsParallel] = useState(() => "parallel" in value);
  const [blocks, setBlocks] = useState<Block[]>(() => {
    if ("parallel" in value) {
      return value.parallel.map(parseNode);
    } else if ("serial" in value) {
      return value.serial.map(parseNode);
    }
    return [{ type: "serial", tasks: "" }];
  });

  // Memoize the value to detect changes
  const valueKey = useMemo(() => {
    if ("parallel" in value) {
      return `parallel-${JSON.stringify(value.parallel)}`;
    }
    if ("serial" in value) {
      return `serial-${JSON.stringify(value.serial)}`;
    }
    return "empty";
  }, [value]);

  // Update blocks when value changes
  useEffect(() => {
    const isParallelValue = "parallel" in value;
    let nodes: (SerialNode | ParallelNode | BatchNode | string)[];

    if (isParallelValue && "parallel" in value) {
      nodes = value.parallel;
    } else if ("serial" in value) {
      nodes = value.serial;
    } else {
      nodes = [];
    }

    setIsParallel(isParallelValue);
    setBlocks(nodes.map(parseNode));
  }, [valueKey]);

  const createSchedule = (blocks: Block[]): CreateMenuRequestSchedule => {
    const nodes = blocks
      .filter((block) => block.tasks.trim() !== "")
      .map((block) => {
        const tasks = block.tasks
          .split(",")
          .map((task: string) => task.trim())
          .filter((task: string) => task !== "");
        return block.type === "serial" ? { serial: tasks } : { batch: tasks };
      })
      .filter((node): node is { serial: string[] } | { batch: string[] } => {
        if ("serial" in node) {
          return (node as { serial: string[] }).serial.length > 0;
        }
        if ("batch" in node) {
          return (node as { batch: string[] }).batch.length > 0;
        }
        return false;
      });

    if (nodes.length === 0) {
      return { serial: [{ serial: [] }] };
    }

    return isParallel ? { parallel: nodes } : { serial: nodes };
  };

  const handleExecutionTypeChange = (parallel: boolean) => {
    setIsParallel(parallel);
    const newSchedule = createSchedule(blocks);
    onChange(newSchedule);
  };

  const handleBlockChange = (
    index: number,
    field: keyof Block,
    value: "serial" | "batch" | string,
  ) => {
    setBlocks((prev) => {
      const newBlocks = [...prev];
      newBlocks[index] = {
        ...newBlocks[index],
        [field]: field === "type" ? (value as "serial" | "batch") : value,
      };
      return newBlocks;
    });
  };

  useEffect(() => {
    const newSchedule = createSchedule(blocks);
    onChange(newSchedule);
  }, [blocks, isParallel]);

  const handleAddBlock = () => {
    setBlocks((prev) => {
      const newBlock: Block = { type: "serial", tasks: "" };
      return [...prev, newBlock];
    });
  };

  const handleRemoveBlock = (index: number) => {
    if (blocks.length <= 2) return; // Keep at least 2 blocks
    setBlocks((prev) => prev.filter((_, i) => i !== index));
  };

  const blockTypeOptions: BlockTypeOption[] = useMemo(
    () => [
      { value: "serial", label: "Serial" },
      { value: "batch", label: "Batch" },
    ],
    [],
  );

  const blockTypeSelectStyles = useMemo<StylesConfig<BlockTypeOption, false>>(
    () => ({
      container: (provided) => ({
        ...provided,
        width: 160,
        minWidth: 160,
        flex: "none",
      }),
      control: (provided) => ({
        ...provided,
        minHeight: 40,
      }),
      valueContainer: (provided) => ({
        ...provided,
        padding: "2px 8px",
      }),
    }),
    [],
  );

  return (
    <div className="space-y-4">
      <div className="form-control">
        <label className="label">
          <span className="label-text">Execution Type</span>
        </label>
        <div className="flex gap-2">
          <label className="label cursor-pointer">
            <input
              type="radio"
              name="execution-type"
              className="radio"
              checked={!isParallel}
              onChange={() => handleExecutionTypeChange(false)}
            />
            <span className="label-text ml-2">Serial</span>
          </label>
          <label className="label cursor-pointer">
            <input
              type="radio"
              name="execution-type"
              className="radio"
              checked={isParallel}
              onChange={() => handleExecutionTypeChange(true)}
            />
            <span className="label-text ml-2">Parallel</span>
          </label>
        </div>
      </div>

      <>
        <div className="grid grid-cols-1 gap-4">
          {blocks.map((block, index) => (
            <div key={index} className="form-control">
              <label className="label">
                <span className="label-text">Block {index + 1} Tasks</span>
                {blocks.length > 2 && (
                  <button
                    className="btn btn-ghost btn-xs"
                    onClick={() => handleRemoveBlock(index)}
                  >
                    Remove
                  </button>
                )}
              </label>
              <div className="flex gap-2">
                <Select<BlockTypeOption, false>
                  className="text-base-content"
                  classNamePrefix="react-select"
                  options={blockTypeOptions}
                  value={blockTypeOptions.find(
                    (option) => option.value === block.type,
                  )}
                  onChange={(option: SingleValue<BlockTypeOption>) => {
                    if (option) {
                      handleBlockChange(index, "type", option.value);
                    }
                  }}
                  isSearchable={false}
                  styles={blockTypeSelectStyles}
                />
                <input
                  type="text"
                  className="input input-bordered flex-1"
                  value={block.tasks}
                  onChange={(e) =>
                    handleBlockChange(index, "tasks", e.target.value)
                  }
                  placeholder={index === 0 ? "0, 1" : "4, 5"}
                />
              </div>
            </div>
          ))}
        </div>
        <div className="flex justify-end">
          <button className="btn btn-ghost btn-sm" onClick={handleAddBlock}>
            Add Block
          </button>
        </div>
      </>
    </div>
  );
}
