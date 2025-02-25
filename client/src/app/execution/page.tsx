'use client';

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  useAddExecutionTags,
  useRemoveExecutionTags,
} from "@/client/execution/execution";
import {
  useListChips,
  useListExecutionsByChipId,
  useFetchExecutionByChipId,
} from "@/client/chip/chip";
import { ChipResponse, ExecutionResponseSummary } from "@/schemas";
import JsonView from "react18-json-view";
import { FaExternalLinkAlt } from "react-icons/fa";
import Select, { SingleValue } from "react-select";

interface ChipOption {
  value: string;
  label: string;
}

export default function ExecutionPage() {
  const [selectedChipId, setSelectedChipId] = useState<string>("SAMPLE");
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [expandedTaskIndex, setExpandedTaskIndex] = useState<number | null>(null);
  const [newTag, setNewTag] = useState<string>("");
  const [cardData, setCardData] = useState<ExecutionResponseSummary[]>([]);

  // チップ一覧取得
  const { data: chipData } = useListChips();

  // chip_id による実行概要一覧の取得
  const {
    data: executionData,
    isError,
    isLoading,
    refetch,
  } = useListExecutionsByChipId(selectedChipId);

  // 選択された execution_id に対して、チップと実行IDでタスク一覧取得
  const {
    data: executionDetailData,
    isLoading: isDetailLoading,
    isError: isDetailError,
    refetch: refetchDetail,
  } = useFetchExecutionByChipId(
    selectedChipId,
    selectedExecutionId ? selectedExecutionId : ""
  );

  const addTagMutation = useAddExecutionTags({
    mutation: {
      onSuccess: () => {
        refetch();
        refetchDetail();
      },
      onError: (error: any) => {
        console.error("Error adding tag:", error);
      },
    },
  });

  const removeTagMutation = useRemoveExecutionTags({
    mutation: {
      onSuccess: () => {
        refetch();
        refetchDetail();
      },
      onError: (error: any) => {
        console.error("Error removing tag:", error);
      },
    },
  });

  // 実行データ取得時にカードデータをセット
  useEffect(() => {
    if (executionData) {
      setCardData(executionData.data);
    }
  }, [executionData]);

  // チップ選択の変更ハンドラ
  const handleChipChange = (selectedOption: SingleValue<ChipOption>) => {
    if (selectedOption) {
      setSelectedChipId(selectedOption.value);
      setSelectedExecutionId(null);
      setIsSidebarOpen(false);
      setCardData([]);
    }
  };

  if (isLoading) return <div>Loading...</div>;
  if (isError) return <div>Error</div>;

  // 一意キー生成
  const getExecutionKey = (execution: ExecutionResponseSummary) =>
    `${execution.execution_id}`;

  const handleCardClick = (execution: ExecutionResponseSummary) => {
    setSelectedExecutionId(execution.execution_id);
    setIsSidebarOpen(true);
    setExpandedTaskIndex(null);
  };

  const handleRemoveTag = (tagToRemove: string) => {
    if (selectedExecutionId) {
      removeTagMutation.mutate(
        {
          executionId: selectedExecutionId,
          data: [tagToRemove],
        },
        {
          onSuccess: () => refetch(),
        }
      );
    }
  };

  const handleAddTag = () => {
    if (newTag.trim() !== "" && selectedExecutionId) {
      addTagMutation.mutate(
        {
          executionId: selectedExecutionId,
          data: [newTag.trim()],
        },
        {
          onSuccess: () => {
            setNewTag("");
            refetch();
          },
        }
      );
    }
  };

  const handleCloseSidebar = () => {
    setIsSidebarOpen(false);
    setSelectedExecutionId(null);
    setExpandedTaskIndex(null);
  };

  // タスククリック時の展開トグル
  const handleTaskClick = (index: number) => {
    setExpandedTaskIndex(expandedTaskIndex === index ? null : index);
  };

  // ステータス別ボーダーカラー
  const getStatusBorderStyle = (status: string) => {
    switch (status) {
      case "running":
        return "border-l-4 border-blue-400";
      case "completed":
        return "border-l-4 border-teal-400";
      case "scheduled":
        return "border-l-4 border-yellow-400";
      case "failed":
        return "border-l-4 border-red-400";
      default:
        return "border-l-4 border-gray-400";
    }
  };

  const chipOptions: ChipOption[] =
    chipData?.data?.map((chip: ChipResponse) => ({
      value: chip.chip_id,
      label: chip.chip_id,
    })) || [];

  return (
    <div className="w-full px-4 relative" style={{ width: "calc(100vw - 20rem)" }}>
      <div className="px-10 pb-3">
        <h1 className="text-left text-3xl font-bold">Execution History</h1>
      </div>
      <div className="px-10 pb-6">
        <Select<ChipOption>
          options={chipOptions}
          value={chipOptions.find((option) => option.value === selectedChipId)}
          onChange={handleChipChange}
          placeholder="Select Chip"
        />
      </div>
      <div className="grid grid-cols-1 gap-2 mx-5">
        {cardData.map((execution) => {
          const executionKey = getExecutionKey(execution);
          const isSelected = selectedExecutionId === execution.execution_id;
          const statusBorderStyle = getStatusBorderStyle(execution.status);

          return (
            <div
              key={executionKey}
              className={`p-4 rounded-lg shadow-md flex cursor-pointer relative overflow-hidden transition-transform duration-200 bg-white ${
                isSelected ? "transform scale-100" : "transform scale-95"
              } ${statusBorderStyle}`}
              onClick={() => handleCardClick(execution)}
            >
              {isSelected && (
                <div className="absolute inset-0 bg-blue-200 opacity-20 pointer-events-none transition-opacity duration-500" />
              )}
              <div className="relative z-10">
                <h2 className="text-xl font-semibold mb-1">{execution.name}</h2>
                <div className="flex items-center mb-1">
                  <p className="text-sm text-gray-500 mr-4">
                    {new Date(execution.start_at).toLocaleString()}
                  </p>
                  <span
                    className={`text-sm font-semibold ${
                      execution.status === "running"
                        ? "text-blue-600"
                        : execution.status === "completed"
                        ? "text-teal-600"
                        : execution.status === "scheduled"
                        ? "text-yellow-600"
                        : "text-red-600"
                    }`}
                  >
                    {execution.status === "running"
                      ? "Running"
                      : execution.status === "completed"
                      ? "Completed"
                      : execution.status === "scheduled"
                      ? "Scheduled"
                      : "Failed"}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {/* サイドバー */}
      <div
        className={`fixed right-0 top-0 w-1/2 h-full bg-white shadow-xl border-l overflow-y-auto p-6 transition-transform duration-300 ${
          isSidebarOpen ? "transform translate-x-0" : "transform translate-x-full"
        }`}
        style={{ maxWidth: "40%" }}
      >
        <button
          onClick={handleCloseSidebar}
          className="text-gray-600 text-2xl font-bold absolute top-4 right-4"
        >
          ×
        </button>
        {selectedExecutionId && (
          <>
            <div className="p-4 bg-white mb-6">
              <h2 className="text-2xl font-bold">
                {
                  cardData.find(
                    (exec) => getExecutionKey(exec) === selectedExecutionId
                  )?.name
                }
              </h2>
              <div className="flex space-x-4 mt-4">
                <a
                  href={`/execution/${selectedExecutionId}/experiment`}
                  className="bg-neutral text-white px-4 py-2 rounded flex items-center hover:bg-neutral-dark transition-colors"
                >
                  <FaExternalLinkAlt className="mr-2" />
                  Go to Experiment
                </a>
                <a
                  href={
                    (cardData.find(
                      (exec) => getExecutionKey(exec) === selectedExecutionId
                    )?.note as { [key: string]: any })?.ui_url || '#'
                  }
                  className="bg-teal-500 text-white px-4 py-2 rounded flex items-center hover:bg-teal-600 transition-colors"
                >
                  <FaExternalLinkAlt className="mr-2" />
                  Go to Flow
                </a>
              </div>
            </div>
            <div className="bg-white">
              <div className="flex flex-wrap mb-4">
                {cardData
                  .find((exec) => getExecutionKey(exec) === selectedExecutionId)
                  ?.tags?.map((tag, tagIndex) => (
                    <span
                      key={tagIndex}
                      className="inline-block bg-gray-200 rounded-full px-3 py-1 text-sm font-semibold text-gray-700 mr-2 mb-1"
                    >
                      {tag}
                      <button
                        type="button"
                        className="ml-2 text-red-500"
                        onClick={() => handleRemoveTag(tag)}
                      >
                        ×
                      </button>
                    </span>
                  ))}
              </div>
              <div className="flex my-4">
                <input
                  type="text"
                  value={newTag}
                  onChange={(e) => setNewTag(e.target.value)}
                  placeholder="Enter tag and press Add"
                  className="input input-bordered w-full max-w-xs"
                />
                <button
                  type="button"
                  className="btn ml-2"
                  onClick={handleAddTag}
                >
                  Add
                </button>
              </div>
            </div>
            <div>
              <h3 className="text-xl font-bold mb-4">Execution Details</h3>
              {isDetailLoading && <div>Loading details...</div>}
              {isDetailError && <div>Error loading details.</div>}
              {executionDetailData &&
                executionDetailData.data.task &&
                executionDetailData.data.task.map((detailTask, idx) => {
                  const taskBorderStyle = (() => {
                    switch (detailTask.status) {
                      case "running":
                        return "border-l-4 border-blue-400";
                      case "completed":
                        return "border-l-4 border-teal-400";
                      case "failed":
                        return "border-l-4 border-red-400";
                      case "scheduled":
                        return "border-l-4 border-yellow-400";
                      default:
                        return "border-l-4 border-gray-400";
                    }
                  })();

                  return (
                    <div
                      key={idx}
                      className={`mb-4 p-4 rounded-lg shadow-md bg-white cursor-pointer hover:shadow-lg transition-shadow ${taskBorderStyle}`}
                      onClick={() => handleTaskClick(idx)}
                    >
                      <h4 className="text-lg font-semibold text-left">
                        {detailTask.name}
                      </h4>
                      <p className="text-left">
                        Start at: {detailTask.start_at ? new Date(detailTask.start_at).toLocaleString() : 'N/A'}
                      </p>
                      <p className="text-left">
                        Elapsed time: {detailTask.elapsed_time}
                      </p>
                      <p
                        className={`text-left text-sm font-semibold ${
                          detailTask.status === "running"
                            ? "text-blue-600"
                            : detailTask.status === "completed"
                            ? "text-teal-600"
                            : detailTask.status === "scheduled"
                            ? "text-yellow-600"
                            : "text-red-600"
                        }`}
                      >
                        {detailTask.status === "running"
                          ? "Running"
                          : detailTask.status === "completed"
                          ? "Completed"
                          : detailTask.status === "scheduled"
                          ? "Scheduled"
                          : "Failed"}
                      </p>
                      {expandedTaskIndex === idx && (
                        <div className="mt-2">
                          {Array.isArray(detailTask.figure_path) ? (
                            detailTask.figure_path.map((path, i) => (
                              <div key={i} className="mt-2">
                                <h5 className="text-md font-semibold mb-1 text-left">
                                  Figure {i + 1}
                                </h5>
                                <img
                                  src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                                    path
                                  )}`}
                                  alt={`Task Figure ${i + 1}`}
                                  className="w-full h-auto max-h-[60vh] object-contain rounded border"
                                />
                              </div>
                            ))
                          ) : detailTask.figure_path ? (
                            <div className="mt-2">
                              <h5 className="text-md font-semibold mb-1 text-left">
                                Figure
                              </h5>
                              <img
                                src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                                  detailTask.figure_path
                                )}`}
                                alt="Task Figure"
                                className="w-full h-auto max-h-[60vh] object-contain rounded border"
                              />
                            </div>
                          ) : null}
                        </div>
                      )}
                      {expandedTaskIndex === idx && (
                        <div className="mt-2">
                          <h5 className="text-md font-semibold mb-1 text-left">
                            Input Parameters
                          </h5>
                          <div className="bg-gray-100 p-2 rounded">
                            <JsonView
                              src={detailTask.input_parameters}
                              theme="vscode"
                              collapsed={1}
                            />
                          </div>
                        </div>
                      )}
                      {expandedTaskIndex === idx && (
                        <div className="mt-2">
                          <h5 className="text-md font-semibold mb-1 text-left">
                            Output Parameters
                          </h5>
                          <div className="bg-gray-100 p-2 rounded">
                            <JsonView
                              src={detailTask.output_parameters}
                              theme="vscode"
                              collapsed={2}
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
