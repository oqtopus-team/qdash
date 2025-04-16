import { useState, useEffect } from "react";
import type { CreateMenuRequestSchedule } from "@/schemas/createMenuRequestSchedule";

type Block = {
  type: "serial" | "batch";
  tasks: string;
};

type ScheduleInputProps = {
  value: CreateMenuRequestSchedule;
  onChange: (schedule: CreateMenuRequestSchedule) => void;
};

export function ScheduleInput({ onChange }: ScheduleInputProps) {
  const [isParallel, setIsParallel] = useState(false);
  const [blocks, setBlocks] = useState<Block[]>([
    { type: "serial", tasks: "" },
    { type: "serial", tasks: "" },
  ]);

  const createSchedule = (blocks: Block[]): CreateMenuRequestSchedule => {
    const validBlocks = blocks
      .map((block) => ({
        type: block.type,
        tasks: block.tasks
          .split(",")
          .map((task) => task.trim())
          .filter((task) => task !== ""),
      }))
      .filter((block) => block.tasks.length > 0);

    if (validBlocks.length === 0) {
      return { serial: [] };
    }

    const nodes = validBlocks.map((block) =>
      block.type === "serial" ? { serial: block.tasks } : { batch: block.tasks }
    );

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
    value: "serial" | "batch" | string
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
                <select
                  className="select select-bordered"
                  value={block.type}
                  onChange={(e) =>
                    handleBlockChange(
                      index,
                      "type",
                      e.target.value as "serial" | "batch"
                    )
                  }
                >
                  <option value="serial">Serial</option>
                  <option value="batch">Batch</option>
                </select>
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
