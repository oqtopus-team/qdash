import { useState, useEffect } from "react";
import {
  useFetchExperimentsById,
  useAddExecutionTags,
  useRemoveExecutionTags,
} from "@/client/execution/execution";
import {
  ExecutionRunResponse,
  ExecutionResponse,
} from "@/schemas/execution/execution";
import JsonView from "react18-json-view";
import { FaExternalLinkAlt } from "react-icons/fa";
import QubitCalibChart from "../components/QubitCalibChart"; // 新しく作成したコンポーネントをインポート
import Select from "react-select";
import { useFetchAllExecutionsByQpuName, useListQpu } from "@/client/qpu/qpu";

const ExecutionPage = () => {
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(
    null,
  );
  const [selectedQpuName, setSelectedQpuName] = useState<string>("");
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [expandedExperimentIndex, setExpandedExperimentIndex] = useState<
    number | null
  >(null);
  const [newTag, setNewTag] = useState<string>("");

  const { data: qpuListData } = useListQpu();
  const {
    data: executionData,
    isError,
    isLoading,
    refetch,
  } = useFetchAllExecutionsByQpuName(
    selectedQpuName ? encodeURIComponent(selectedQpuName) : "",
  );
  const { data: experimentsByIdData } = useFetchExperimentsById(
    selectedExecutionId ? encodeURIComponent(selectedExecutionId) : "",
  );

  const addTagMutation = useAddExecutionTags({
    onSuccess: () => {
      refetch();
    },
    onError: (error) => {
      console.error("Error adding tag:", error);
    },
  });

  const removeTagMutation = useRemoveExecutionTags({
    onSuccess: () => {
      refetch();
    },
    onError: (error) => {
      console.error("Error removing tag:", error);
    },
  });

  const [cardData, setCardData] = useState<ExecutionRunResponse[]>([]);

  // Set up initial data fetch
  useEffect(() => {
    if (executionData) {
      setCardData(executionData.data);
    }
  }, [executionData]);

  // Set default QPU name
  useEffect(() => {
    if (qpuListData && qpuListData.data.length > 0) {
      setSelectedQpuName(qpuListData.data[0].name);
    }
  }, [qpuListData]);

  // Log query and results
  useEffect(() => {
    console.log("Query Params:", { executionId: selectedExecutionId });
    console.log("Execution Data:", executionData);
    console.log("Experiments By ID Data:", experimentsByIdData);
  }, [selectedExecutionId, executionData, experimentsByIdData]);

  if (isLoading) {
    return <div>Loading...</div>;
  }
  if (isError) {
    return <div>Error</div>;
  }

  // Generate a unique key for each execution
  const getExecutionKey = (execution) => `${execution.execution_id}`;

  const handleCardClick = (execution) => {
    setSelectedExecutionId(execution.execution_id);
    setIsSidebarOpen(true);
  };

  const handleRemoveTag = (tagToRemove: string) => {
    if (selectedExecutionId) {
      console.log("Removing tag:", tagToRemove);
      console.log("Selected Execution ID:", selectedExecutionId);

      removeTagMutation.mutate(
        {
          executionId: selectedExecutionId,
          data: [tagToRemove],
        },
        {
          onSuccess: () => {
            refetch();
          },
        },
      );
    } else {
      console.error("selectedExecutionId is undefined");
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
        },
      );
    }
  };

  const handleCloseSidebar = () => {
    setIsSidebarOpen(false);
    setSelectedExecutionId(null);
    setExpandedExperimentIndex(null);
  };

  const handleExperimentClick = (index: number) => {
    setExpandedExperimentIndex(
      expandedExperimentIndex === index ? null : index,
    );
  };

  // Function to determine the left border color based on status
  const getStatusBorderStyle = (status) => {
    switch (status) {
      case "running":
        return "border-l-4 border-blue-400"; // running: blue
      case "success":
        return "border-l-4 border-teal-400"; // success: teal
      case "failed":
        return "border-l-4 border-red-400"; // failed: red
      default:
        return "border-l-4 border-gray-400"; // fallback: gray
    }
  };

  // QPU options for the dropdown
  const qpuOptions = qpuListData?.data?.map((qpu) => ({
    value: qpu.name,
    label: qpu.name,
  }));

  return (
    <div
      className="w-full px-4 relative"
      style={{ width: "calc(100vw - 20rem)" }}
    >
      <div className="px-10 pb-3">
        <h1 className="text-left text-3xl font-bold">Execution History</h1>
        <div className="flex justify-start w-full mt-4 mx-10">
          <Select
            value={qpuOptions?.find(
              (option) => option.value === selectedQpuName,
            )}
            options={qpuOptions}
            onChange={(selectedOption) =>
              setSelectedQpuName(selectedOption?.value)
            }
            placeholder="Select QPU"
            className="w-64"
          />
        </div>
      </div>
      <div className="rounded-lg bg-white flex justify-center mx-20 my-5">
        <div className="w-full mx-20 h-[600px]">
          <QubitCalibChart name={selectedQpuName} />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-2 mx-5">
        {cardData.map((execution, index) => {
          const executionKey = getExecutionKey(execution);
          const isSelected = selectedExecutionId === execution.execution_id;
          const statusBorderStyle = getStatusBorderStyle(execution.status);

          return (
            <div
              key={index}
              className={`p-4 rounded-lg shadow-md flex cursor-pointer relative overflow-hidden transition-transform duration-200 bg-white ${
                isSelected ? "transform scale-100" : "transform scale-95"
              } ${statusBorderStyle}`}
              onClick={() => handleCardClick(execution)}
            >
              {/* Overlay for selected card to add blue highlight */}
              {isSelected && (
                <div className="absolute inset-0 bg-blue-200 opacity-20 pointer-events-none transition-opacity duration-500" />
              )}
              <div className="relative z-10">
                <h2 className="text-xl font-semibold mb-1">
                  {execution.menu.name} - {execution.execution_id}
                </h2>
                <div className="flex items-center mb-1">
                  <p className="text-sm text-gray-500 mr-4">
                    {new Date(execution.timestamp).toLocaleString()}
                  </p>
                  <span
                    className={`text-sm font-semibold ${
                      execution.status === "running"
                        ? "text-blue-600"
                        : execution.status === "success"
                          ? "text-teal-600"
                          : "text-red-600"
                    }`}
                  >
                    {execution.status === "running"
                      ? "Running"
                      : execution.status === "success"
                        ? "Success"
                        : "Failed"}
                  </span>
                  <div className="flex flex-wrap ml-4">
                    {execution.tags?.map((tag, tagIndex) => (
                      <span
                        key={tagIndex}
                        className="inline-block bg-gray-200 rounded-full px-3 py-1 text-sm font-semibold text-gray-700 mr-2 mb-1"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {/* Sidebar */}
      <div
        className={`fixed right-0 top-0 w-1/2 h-full bg-white shadow-lg border-l overflow-y-auto p-6 transition-transform duration-300 ${
          isSidebarOpen
            ? "transform translate-x-0"
            : "transform translate-x-full"
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
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-2xl font-bold">
                {
                  cardData.find(
                    (exec) => getExecutionKey(exec) === selectedExecutionId,
                  )?.menu.name
                }{" "}
                - {selectedExecutionId}{" "}
              </h2>
              <div className="flex space-x-4 mx-8">
                <a
                  href={`http://localhost:5714/execution/${selectedExecutionId}/experiment`}
                  className="bg-neutral text-white  px-4 py-2 rounded flex items-center"
                >
                  <FaExternalLinkAlt className="mr-2" />
                  Go to Experiment
                </a>
                <a
                  href={
                    cardData.find(
                      (exec) => getExecutionKey(exec) === selectedExecutionId,
                    )?.flow_url
                  }
                  className="bg-teal-500 text-white px-4 py-2 rounded flex items-center"
                >
                  <FaExternalLinkAlt className="mr-2" />
                  Go to Flow
                </a>
              </div>
            </div>
            <div className="text-left mb-6">
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
              <div className="my-2">
                <h3 className="text-xl font-semibold mb-2">QPU</h3>
                <div className="bg-gray-50 p-4 rounded-lg font-semibold">
                  {
                    cardData.find(
                      (exec) => getExecutionKey(exec) === selectedExecutionId,
                    ).qpu_name
                  }
                </div>
              </div>
              <div className="my-2">
                <h3 className="text-xl font-semibold mb-2">
                  Fridge Temperature
                </h3>
                <div className="bg-gray-50 p-4 rounded-lg font-semibold">
                  {
                    cardData.find(
                      (exec) => getExecutionKey(exec) === selectedExecutionId,
                    ).fridge_temperature
                  }
                </div>
              </div>
              <h3 className="text-xl font-semibold mb-2">Menu</h3>
              <div className="bg-gray-50 p-4 rounded-lg">
                <JsonView
                  src={
                    cardData.find(
                      (exec) => getExecutionKey(exec) === selectedExecutionId,
                    ).menu
                  }
                  collapsed={1}
                  theme="vscode"
                />
              </div>
            </div>
            {experimentsByIdData?.data?.map(
              (experiment: ExecutionResponse, index: number) => (
                <div
                  key={index}
                  className={`p-4 rounded-lg shadow-md bg-white mb-4 ${getStatusBorderStyle(
                    experiment.status,
                  )}`}
                  onClick={() => handleExperimentClick(index)}
                >
                  <h3 className="text-xl font-semibold mb-1 text-left">
                    {experiment.label} - {experiment.experiment_name}
                  </h3>
                  <div className="flex items-center mb-1">
                    <p className="text-sm text-gray-500 mr-4">
                      {new Date(experiment.timestamp).toLocaleString()}
                    </p>
                    <span
                      className={`text-sm font-semibold ${
                        experiment.status === "running"
                          ? "text-blue-600"
                          : experiment.status === "success"
                            ? "text-teal-600"
                            : "text-red-600"
                      }`}
                    >
                      {experiment.status === "running"
                        ? "Running"
                        : experiment.status === "success"
                          ? "Success"
                          : "Failed"}
                    </span>
                  </div>
                  {expandedExperimentIndex === index && (
                    <div className="mt-2">
                      {experiment.fig_path && (
                        <div className="mt-2">
                          <h4 className="text-lg font-semibold mb-1 text-left">
                            Figure
                          </h4>
                          <img
                            src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
                              experiment.fig_path,
                            )}`}
                            alt="Experiment Figure"
                            className="w-full h-auto max-h-[60vh] object-contain rounded border"
                          />
                        </div>
                      )}
                      {experiment.input_parameter && (
                        <div className="mt-2">
                          <h4 className="text-lg font-semibold mb-1 text-left">
                            Input Parameters
                          </h4>
                          <div className="bg-gray-100 p-2 rounded">
                            <JsonView
                              src={experiment.input_parameter}
                              theme="vscode"
                            />
                          </div>
                        </div>
                      )}
                      {experiment.output_parameter && (
                        <div className="mt-2">
                          <h4 className="text-lg font-semibold mb-1 text-left">
                            Output Parameters
                          </h4>
                          <div className="bg-gray-100 p-2 rounded">
                            <JsonView
                              src={experiment.output_parameter}
                              theme="vscode"
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ),
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default ExecutionPage;
