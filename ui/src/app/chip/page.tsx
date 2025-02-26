"use client";

import { useListQpu, useFetchQpuStatsByName } from "@/client/qpu/qpu";
import { QPUInfoResponse } from "@/schemas";
import { useEffect, useState } from "react";

import Select from "react-select";

type StatsProps = {
  average_gate_fidelity: number;
  t1: number;
  t2: number;
};

export const Stats = ({ average_gate_fidelity, t1, t2 }: StatsProps) => {
  return (
    <div className="w-full stats shadow bg-base-200 p-4 rounded-lg">
      <div className="stat">
        <div className="stat-figure text-base-content"></div>
        <div className="stat-title">Average Gate Fidelity</div>
        <div className="stat-value text-primary">{average_gate_fidelity}%</div>
        <div className="stat-desc">max value</div>
      </div>
      <div className="stat">
        <div className="stat-figure text-base-content"></div>
        <div className="stat-title">T1</div>
        <div className="stat-value text-primary">{t1} us</div>
        <div className="stat-desc">max value</div>
      </div>
      <div className="stat">
        <div className="stat-figure text-base-content"></div>
        <div className="stat-title">T2</div>
        <div className="stat-value text-primary">{t2} us</div>
        <div className="stat-desc">max value</div>
      </div>
    </div>
  );
};

const QubitCalibChartContainer = () => {
  const [selectedName, setSelectedName] = useState<string>("SAMPLE");

  const {
    data: qpuStats,
    isLoading,
    isError,
    refetch: refetchQpuStats, // refetch関数を取得
  } = useFetchQpuStatsByName(encodeURIComponent(selectedName));

  const {
    data: qpuData,
    isLoading: isQpuLoading,
    isError: isQpuError,
  } = useListQpu();

  const qpuOptions =
    qpuData?.data?.map((qpu: QPUInfoResponse) => ({
      value: qpu.name,
      label: qpu.name,
    })) || [];

  const nameOptions = qpuOptions;

  const handleQpuChange = (
    selectedOption: { value: string; label: string } | null
  ) => {
    const newValue = selectedOption ? selectedOption.value : "SAMPLE";
    setSelectedName(newValue);
  };

  useEffect(() => {
    console.log("refetch");
    console.log(selectedName);
    refetchQpuStats();
  }, [selectedName, refetchQpuStats]);

  if (isQpuLoading || isLoading) {
    return <div>Loading...</div>;
  }
  if (isQpuError || isError) {
    return <div>Error</div>;
  }

  return (
    <div>
      <Select
        options={nameOptions}
        value={nameOptions.find((option) => option.value === selectedName)}
        onChange={handleQpuChange}
        placeholder="Select QPU Name"
        className="w-1/3"
      />
      <div className="my-5">
        <Stats
          average_gate_fidelity={
            Math.round(
              (qpuStats?.data.average_gate_fidelity.max_value ?? 0) * 100 * 1000
            ) / 1000
          }
          t1={Math.round((qpuStats?.data.t1.max_value ?? 0) * 1000) / 1000}
          t2={Math.round((qpuStats?.data.t2_echo.max_value ?? 0) * 1000) / 1000}
        />
      </div>
      <div className="flex space-x-4 mb-4"></div>
      {qpuStats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Object.entries(qpuStats.data).map(([key, stats]) => (
            <div key={key} className="card bg-base-200 shadow p-4 rounded-lg">
              <div className="card-body text-left">
                <h2 className="card-title text-lg font-semibold">
                  {key.replace("_", " ")}
                </h2>
                <p>Average Value: {stats.average_value ?? "N/A"}</p>
                <p>Max Value: {stats.max_value ?? "N/A"}</p>
                <p>Min Value: {stats.min_value ?? "N/A"}</p>
                <div className="mt-2">
                  <img
                    src={`http://localhost:5715/qpu/figure?path=${encodeURIComponent(
                      stats.fig_path
                    )}`}
                    alt="Experiment Figure"
                    className="w-full h-auto max-h-[60vh] object-contain rounded border"
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

function QpuPage() {
  return (
    <div className="w-full px-4" style={{ width: "calc(100vw - 20rem)" }}>
      <h1 className="text-left text-3xl font-bold px-1 pb-3">QPU Summary</h1>
      <div className="w-full gap-6 px-2">
        <div className="w-full h-full">
          <QubitCalibChartContainer />
        </div>
      </div>
    </div>
  );
}

export default QpuPage;
