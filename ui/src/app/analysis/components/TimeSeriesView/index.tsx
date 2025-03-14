"use client";

import { useFetchAllParameters } from "@/client/parameter/parameter";
import { useListAllTag } from "@/client/tag/tag";
import { useFetchTimeseriesTaskResultByTagAndParameter } from "@/client/chip/chip";
import { useMemo, useState, useEffect, useCallback } from "react";
import { ParameterSelector } from "@/app/components/ParameterSelector";
import { TagSelector } from "@/app/components/TagSelector";
import { ChipSelector } from "@/app/components/ChipSelector";
import { DateTimePicker } from "@/app/components/DateTimePicker";
import dynamic from "next/dynamic";
import { Layout } from "plotly.js";
import { OutputParameterModel } from "@/schemas";

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => <div>Loading Plot...</div>,
});

export function TimeSeriesView() {
  const [selectedChip, setSelectedChip] = useState<string>("");
  const [selectedParameter, setSelectedParameter] = useState<string>("t1");
  const [selectedTag, setSelectedTag] = useState<string>("daily");
  // Format date with JST timezone
  const formatJSTDate = (date: Date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    const seconds = String(date.getSeconds()).padStart(2, "0");
    const milliseconds = String(date.getMilliseconds()).padStart(3, "0");
    return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}.${milliseconds}+09:00`;
  };

  const [endAt, setEndAt] = useState<string>(formatJSTDate(new Date()));
  const [startAt, setStartAt] = useState<string>(
    formatJSTDate(new Date(Date.now() - 7 * 24 * 60 * 60 * 1000))
  );
  const [isStartAtLocked, setIsStartAtLocked] = useState(false);
  const [isEndAtLocked, setIsEndAtLocked] = useState(false);
  const [filter, setFilter] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [sortField, setSortField] = useState<"time" | "qid">("time");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const REFRESH_INTERVAL = 30; // 30 seconds fixed
  const ROWS_PER_PAGE = 50;

  // Handle sort
  const handleSort = useCallback(
    (field: "time" | "qid") => {
      if (sortField === field) {
        setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      } else {
        setSortField(field);
        setSortDirection("desc");
      }
    },
    [sortField]
  );

  // Update current time every 30 seconds
  useEffect(() => {
    const timer = setInterval(() => {
      if (!isEndAtLocked) {
        setEndAt(formatJSTDate(new Date()));
      }
      if (!isStartAtLocked && !isEndAtLocked) {
        setStartAt(
          formatJSTDate(new Date(Date.now() - 7 * 24 * 60 * 60 * 1000))
        );
      }
    }, REFRESH_INTERVAL * 1000);
    return () => clearInterval(timer);
  }, [isStartAtLocked, isEndAtLocked]);

  // Reset page when filter changes
  useEffect(() => {
    setCurrentPage(1);
  }, [filter]);

  // Handle time range changes
  const handleStartAtChange = useCallback(
    (value: string) => {
      setStartAt(value);
      if (!isStartAtLocked) {
        setIsStartAtLocked(true);
      }
    },
    [isStartAtLocked]
  );

  const handleEndAtChange = useCallback(
    (value: string) => {
      setEndAt(value);
      if (!isEndAtLocked) {
        setIsEndAtLocked(true);
      }
    },
    [isEndAtLocked]
  );

  // Toggle lock functions
  const toggleStartAtLock = useCallback(() => {
    if (isStartAtLocked) {
      setStartAt(formatJSTDate(new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)));
    }
    setIsStartAtLocked(!isStartAtLocked);
  }, [isStartAtLocked]);

  const toggleEndAtLock = useCallback(() => {
    if (isEndAtLocked) {
      setEndAt(formatJSTDate(new Date()));
    }
    setIsEndAtLocked(!isEndAtLocked);
  }, [isEndAtLocked]);

  // Fetch parameters and tags
  const { data: parametersResponse, isLoading: isLoadingParameters } =
    useFetchAllParameters();
  const { data: tagsResponse, isLoading: isLoadingTags } = useListAllTag();

  // Fetch time series data
  const { data: timeseriesResponse, isLoading: isLoadingTimeseries } =
    useFetchTimeseriesTaskResultByTagAndParameter(
      selectedChip,
      selectedParameter,
      {
        tag: selectedTag,
        start_at: startAt,
        end_at: endAt,
      },
      {
        query: {
          enabled: Boolean(selectedChip && selectedParameter && selectedTag),
          refetchInterval: REFRESH_INTERVAL * 1000,
        },
      }
    );

  // Table data
  const tableData = useMemo(() => {
    if (!timeseriesResponse?.data?.data) return [];
    const rows: {
      qid: string;
      time: string;
      value: number | string;
      error?: number;
      unit: string;
    }[] = [];

    Object.entries(timeseriesResponse.data.data).forEach(
      ([qid, dataPoints]) => {
        if (Array.isArray(dataPoints)) {
          dataPoints.forEach((point: OutputParameterModel) => {
            rows.push({
              qid,
              time: point.calibrated_at || "",
              value: point.value || 0,
              error: point.error,
              unit: point.unit || "a.u.",
            });
          });
        }
      }
    );

    // Sort by QID and time
    return rows.sort((a, b) => {
      const qidCompare = parseInt(a.qid) - parseInt(b.qid);
      if (qidCompare !== 0) return qidCompare;
      return a.time.localeCompare(b.time);
    });
  }, [timeseriesResponse]);

  // Filtered and sorted data
  const filteredData = useMemo(() => {
    const filtered = tableData.filter((row) => row.qid.includes(filter));
    return filtered.sort((a, b) => {
      const direction = sortDirection === "asc" ? 1 : -1;
      if (sortField === "time") {
        return direction * a.time.localeCompare(b.time);
      } else {
        return direction * (parseInt(a.qid) - parseInt(b.qid));
      }
    });
  }, [tableData, filter, sortField, sortDirection]);

  // Prepare plot data
  const plotData = useMemo(() => {
    if (!timeseriesResponse?.data?.data) return [];

    try {
      // Organize data by QID
      const qidData: {
        [key: string]: {
          x: string[];
          y: number[];
          error: number[];
        };
      } = {};
      const data = timeseriesResponse.data.data;

      // Validate data structure
      if (typeof data === "object" && data !== null) {
        Object.entries(data).forEach(([qid, dataPoints]) => {
          if (Array.isArray(dataPoints)) {
            qidData[qid] = {
              x: dataPoints.map(
                (point: OutputParameterModel) => point.calibrated_at || ""
              ),
              y: dataPoints.map((point: OutputParameterModel) => {
                if (point.value && selectedParameter) {
                  const value = point.value;
                  if (typeof value === "number") {
                    return value;
                  }
                  if (typeof value === "string") {
                    return Number(value) || 0;
                  }
                }
                return 0;
              }),
              error: dataPoints.map(
                (point: OutputParameterModel) => point.error || 0
              ),
            };
          }
        });
      }

      // Sort QIDs numerically
      const sortedQids = Object.keys(qidData).sort((a, b) => {
        const numA = parseInt(a);
        const numB = parseInt(b);
        return numA - numB;
      });

      // Create trace data for Plotly
      return sortedQids.map((qid) => ({
        x: qidData[qid].x,
        y: qidData[qid].y,
        error_y: {
          type: "data" as const,
          array: qidData[qid].error as Plotly.Datum[],
          visible: true,
        },
        type: "scatter" as const,
        mode: "lines+markers" as const,
        name: `QID: ${qid}`,
        line: {
          shape: "linear" as const,
          width: 2,
        },
        marker: {
          size: 8,
          symbol: "circle",
        },
        hovertemplate:
          "Time: %{x}<br>" +
          "Value: %{y:.8f}" +
          (qidData[qid].error[0] ? "<br>Error: ±%{error_y.array:.8f}" : "") +
          "<br>QID: " +
          qid +
          "<extra></extra>",
      }));
    } catch (error) {
      console.error("Error processing plot data:", error);
      return [];
    }
  }, [timeseriesResponse, selectedParameter]);

  const layout = useMemo<Partial<Layout>>(() => {
    const data = timeseriesResponse?.data?.data;
    let unit = "Value";
    let description = "";

    if (typeof data === "object" && data !== null) {
      const entries = Object.entries(data);
      if (entries.length > 0) {
        const [, firstDataPoints] = entries[0];
        if (Array.isArray(firstDataPoints) && firstDataPoints.length > 0) {
          const firstPoint = firstDataPoints[0] as OutputParameterModel;
          if (firstPoint.unit) {
            unit = firstPoint.unit || "a.u.";
          }
          if (firstPoint.description) {
            description = firstPoint.description;
          }
        }
      }
    }

    return {
      title: {
        text: `${selectedParameter} Time Series by QID`,
        font: {
          size: 24,
        },
      },
      xaxis: {
        title: "Time",
        type: "date",
        tickformat: "%Y-%m-%d %H:%M",
        gridcolor: "#eee",
        zeroline: false,
      },
      yaxis: {
        title: `${description} [${unit}]`,
        type: "linear",
        gridcolor: "#eee",
        zeroline: false,
        exponentformat: "e" as const,
      },
      showlegend: true,
      legend: {
        x: 1.05,
        y: 1,
        xanchor: "left",
        yanchor: "top",
        bgcolor: "rgba(255, 255, 255, 0.8)",
      },
      autosize: true,
      margin: {
        l: 80,
        r: 150,
        t: 100,
        b: 80,
      },
      plot_bgcolor: "white",
      paper_bgcolor: "white",
      hovermode: "closest",
    };
  }, [selectedParameter, timeseriesResponse]);

  const parameters = parametersResponse?.data?.parameters || [];
  const tags = tagsResponse?.data?.tags || [];

  // Convert data to CSV format
  const handleDownloadCSV = useCallback(() => {
    if (!timeseriesResponse?.data?.data) return;

    // Prepare CSV header
    const headers = ["QID", "Time", "Parameter", "Value", "Error", "Unit"];
    const rows: string[][] = [];

    // Convert data to rows
    Object.entries(timeseriesResponse.data.data).forEach(
      ([qid, dataPoints]) => {
        if (Array.isArray(dataPoints)) {
          dataPoints.forEach((point: OutputParameterModel) => {
            rows.push([
              qid,
              point.calibrated_at || "",
              selectedParameter,
              String(point.value || ""),
              String(point.error || ""),
              point.unit || "a.u.",
            ]);
          });
        }
      }
    );

    // Sort rows by QID and time
    rows.sort((a, b) => {
      const qidCompare = parseInt(a[0]) - parseInt(b[0]);
      if (qidCompare !== 0) return qidCompare;
      return a[1].localeCompare(b[1]);
    });

    // Create CSV content
    const csvContent = [
      headers.join(","),
      ...rows.map((row) => row.map((cell) => `"${cell}"`).join(",")),
    ].join("\n");

    // Create and trigger download
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.setAttribute(
      "download",
      `timeseries_${selectedChip}_${selectedParameter}_${selectedTag}_${new Date()
        .toISOString()
        .slice(0, 19)
        .replace(/[:-]/g, "")}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, [timeseriesResponse, selectedChip, selectedParameter, selectedTag]);

  return (
    <div className="grid grid-cols-3 gap-8">
      {/* Parameter Selection Card */}
      <div className="col-span-3 card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
        <div className="text-xs text-base-content/70 mb-2">
          Auto refresh every {REFRESH_INTERVAL} seconds
        </div>
        <h2 className="text-xl font-semibold mb-6 flex items-center gap-2">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-5 h-5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M3 3v18h18"></path>
            <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"></path>
          </svg>
          Parameter Selection
        </h2>
        <div className="grid grid-cols-3 gap-12">
          <ChipSelector
            selectedChip={selectedChip}
            onChipSelect={setSelectedChip}
          />
          <ParameterSelector
            label="Parameter"
            parameters={parameters.map((p) => p.name)}
            selectedParameter={selectedParameter}
            onParameterSelect={setSelectedParameter}
            disabled={isLoadingParameters}
          />
          <TagSelector
            tags={tags}
            selectedTag={selectedTag}
            onTagSelect={setSelectedTag}
            disabled={isLoadingTags}
          />
        </div>
        <div className="mt-4">
          <span className="text-sm font-medium mb-2 block">Time Range</span>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <DateTimePicker
                  label="From"
                  value={startAt}
                  onChange={handleStartAtChange}
                  disabled={isLoadingTags}
                />
              </div>
              <button
                className={`btn btn-sm mt-8 gap-2 ${
                  isStartAtLocked ? "btn-primary" : "btn-ghost"
                }`}
                onClick={toggleStartAtLock}
                title={
                  isStartAtLocked ? "Unlock start time" : "Lock start time"
                }
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-4 h-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  {isStartAtLocked ? (
                    <>
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </>
                  ) : (
                    <>
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 9.9-1" />
                    </>
                  )}
                </svg>
                {isStartAtLocked ? "Fixed" : "Auto"}
              </button>
            </div>
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <DateTimePicker
                  label="To"
                  value={endAt}
                  onChange={handleEndAtChange}
                  disabled={isLoadingTags}
                />
              </div>
              <button
                className={`btn btn-sm mt-8 gap-2 ${
                  isEndAtLocked ? "btn-primary" : "btn-ghost"
                }`}
                onClick={toggleEndAtLock}
                title={isEndAtLocked ? "Unlock end time" : "Lock end time"}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-4 h-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  {isEndAtLocked ? (
                    <>
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </>
                  ) : (
                    <>
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 9.9-1" />
                    </>
                  )}
                </svg>
                {isEndAtLocked ? "Fixed" : "Auto"}
              </button>
            </div>
          </div>
          <div className="mt-2 text-xs text-base-content/70 flex items-center gap-1">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-4 h-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12" y2="8" />
            </svg>
            {!isStartAtLocked && !isEndAtLocked
              ? "Both times auto-update every 30 seconds"
              : isStartAtLocked && isEndAtLocked
              ? "Both times are fixed"
              : isStartAtLocked
              ? "Start time is fixed, end time auto-updates"
              : "End time is fixed, start time auto-updates"}
          </div>
        </div>
      </div>

      {/* Plot Area */}
      <div className="col-span-3 card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
        <h2 className="text-2xl font-semibold mb-6 text-center flex items-center justify-center gap-2">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-6 h-6"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M3 3v18h18"></path>
            <path d="M3 12h18"></path>
            <path d="M12 3v18"></path>
          </svg>
          Time Series Plot
        </h2>
        <div
          className="w-full bg-base-200/50 rounded-xl p-4"
          style={{ height: "550px" }}
        >
          {/* Loading state */}
          {isLoadingTimeseries && (
            <div className="flex items-center justify-center h-full">
              <div className="loading loading-spinner loading-lg text-primary"></div>
            </div>
          )}

          {/* Error state */}
          {!isLoadingTimeseries &&
            selectedChip &&
            selectedParameter &&
            selectedTag &&
            !timeseriesResponse?.data?.data && (
              <div className="flex items-center justify-center h-full text-error">
                <span>No data available for the selected parameters</span>
              </div>
            )}

          {/* Plot area */}
          {plotData.length > 0 && (
            <Plot
              data={plotData}
              layout={layout}
              config={{
                displaylogo: false,
                responsive: true,
                toImageButtonOptions: {
                  format: "svg",
                  filename: "time_series",
                  height: 600,
                  width: 800,
                  scale: 2,
                },
              }}
              style={{ width: "100%", height: "100%" }}
              useResizeHandler={true}
            />
          )}

          {/* Unselected state */}
          {!selectedChip || !selectedParameter || !selectedTag ? (
            <div className="flex items-center justify-center h-full text-base-content/70">
              <div className="text-center">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-12 h-12 mx-auto mb-4 opacity-50"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M3 3v18h18"></path>
                  <path d="M3 12h18"></path>
                  <path d="M12 3v18"></path>
                </svg>
                <p className="text-lg">
                  Select chip and parameters to visualize data
                </p>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* Data Table */}
      <div className="col-span-3 card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-4">
            <h2 className="text-2xl font-semibold">Data Table</h2>
            <button
              className="btn btn-sm btn-outline gap-2"
              onClick={handleDownloadCSV}
              disabled={!timeseriesResponse?.data?.data}
              title="Download all data as CSV"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="w-4 h-4"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Download CSV
            </button>
          </div>
          <div className="flex items-center gap-2">
            <div className="form-control w-64">
              <input
                type="text"
                placeholder="Filter by QID..."
                className="input input-bordered input-sm"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
            </div>
            <div className="text-sm text-base-content/70">
              {filter ? `Filtered ${filteredData.length} entries` : ""}
            </div>
          </div>
        </div>
        <div className="overflow-x-auto" style={{ minHeight: "400px" }}>
          <table className="table table-compact table-zebra w-full border border-base-300 bg-base-100">
            <thead>
              <tr>
                <th
                  className="text-left bg-base-200 cursor-pointer hover:bg-base-300"
                  onClick={() => handleSort("qid")}
                >
                  <div className="flex items-center gap-1">
                    QID
                    {sortField === "qid" && (
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className={`w-4 h-4 transition-transform ${
                          sortDirection === "desc" ? "rotate-180" : ""
                        }`}
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M18 15l-6-6-6 6" />
                      </svg>
                    )}
                  </div>
                </th>
                <th
                  className="text-left bg-base-200 cursor-pointer hover:bg-base-300"
                  onClick={() => handleSort("time")}
                >
                  <div className="flex items-center gap-1">
                    Time
                    {sortField === "time" && (
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className={`w-4 h-4 transition-transform ${
                          sortDirection === "desc" ? "rotate-180" : ""
                        }`}
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M18 15l-6-6-6 6" />
                      </svg>
                    )}
                  </div>
                </th>
                <th className="text-center bg-base-200">Value</th>
                <th className="text-center bg-base-200">Error</th>
                <th className="text-center bg-base-200">Unit</th>
              </tr>
            </thead>
            <tbody>
              {filteredData
                .slice(
                  (currentPage - 1) * ROWS_PER_PAGE,
                  currentPage * ROWS_PER_PAGE
                )
                .map((row, index) => (
                  <tr key={index}>
                    <td className="text-left">{row.qid}</td>
                    <td className="text-left">{row.time}</td>
                    <td className="text-center">
                      {typeof row.value === "number"
                        ? row.value.toFixed(4)
                        : row.value}
                    </td>
                    <td className="text-center">
                      {row.error !== undefined
                        ? `±${row.error.toFixed(4)}`
                        : "-"}
                    </td>
                    <td className="text-center">{row.unit}</td>
                  </tr>
                ))}
            </tbody>
          </table>
          <div className="flex justify-between items-center mt-4">
            <div className="text-sm text-base-content/70">
              Showing {Math.min(ROWS_PER_PAGE, filteredData.length)} of{" "}
              {filteredData.length} entries
            </div>
            <div className="join">
              <button
                className="join-item btn btn-sm"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
              >
                Previous
              </button>
              <button className="join-item btn btn-sm btn-disabled">
                Page {currentPage} of{" "}
                {Math.ceil(filteredData.length / ROWS_PER_PAGE)}
              </button>
              <button
                className="join-item btn btn-sm"
                onClick={() =>
                  setCurrentPage((p) =>
                    Math.min(
                      Math.ceil(filteredData.length / ROWS_PER_PAGE),
                      p + 1
                    )
                  )
                }
                disabled={
                  currentPage === Math.ceil(filteredData.length / ROWS_PER_PAGE)
                }
              >
                Next
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
