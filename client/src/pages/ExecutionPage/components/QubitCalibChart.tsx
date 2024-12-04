import React, { useEffect, useState } from "react";
import { useFetchOneQubitCalibHistoryByParamName } from "@/client/qpu/qpu";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { useNavigate } from "react-router-dom";

const parameterOptions = ["t1", "t2_echo", "average_gate_fidelity"];

type QubitCalibChartProps = {
  name: string;
};

const QubitCalibChart = ({ name }: QubitCalibChartProps) => {
  const [tags, setTags] = useState<string[]>(["t1-test"]);
  const [inputTag, setInputTag] = useState<string>("");
  const [paramName, setParamName] = useState<string>("t1");
  const navigate = useNavigate();

  const encodedName = encodeURIComponent(name);
  const encodedParamName = encodeURIComponent(paramName);
  const encodedTags = tags.map((tag) => encodeURIComponent(tag));

  const { data, isLoading, isError } = useFetchOneQubitCalibHistoryByParamName(
    encodedName,
    encodedParamName,
    { tags: tags },
  );

  const [chartData, setChartData] = useState([]);

  useEffect(() => {
    if (data) {
      setChartData(data.data.data);
      console.log(data.data);
    }
  }, [data]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && inputTag.trim() !== "") {
      setTags([...tags, inputTag.trim()]);
      setInputTag("");
    }
  };

  const handleRemoveTag = (tagToRemove: string) => {
    setTags(tags.filter((tag) => tag !== tagToRemove));
  };

  const handleLineClick = (data: any) => {
    const id = data.activePayload[0].payload.event;
    console.log(id);
    navigate(`/execution/${id}/experiment`);
  };

  if (isLoading) {
    return <div>Loading...</div>;
  }

  if (isError) {
    return <div>Error loading data</div>;
  }

  // ラインの色を設定するカラーパレット
  const colors = ["#8884d8", "#82ca9d", "#ff7300", "#00c49f", "#ffbb28"];

  const getLines = () => {
    // 全てのデータを走査して、`event` 以外のユニークなキーを取得
    const keys = Array.from(
      new Set(
        chartData.flatMap((item) =>
          Object.keys(item).filter((key) => key !== "event"),
        ),
      ),
    );

    // 各キーに基づいて <Line /> を生成
    return keys.map((key, index) => (
      <Line
        key={key}
        type="monotone"
        dataKey={key}
        stroke={colors[index % colors.length]} // 色を順番に設定
        activeDot={{ r: 8 }}
        strokeWidth={3}
      />
    ));
  };

  return (
    <div className="w-full h-96 my-8">
      <h2 className="text-2xl font-bold mb-4">Qubit Calibration Data</h2>
      <div className="mb-4">
        <select
          value={paramName}
          onChange={(e) => setParamName(e.target.value)}
          className="select max-w-xs select-bordered mx-4"
        >
          {parameterOptions.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <input
          type="text"
          value={inputTag}
          onChange={(e) => setInputTag(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Enter tag and press Enter"
          className="input input-bordered w-full max-w-xs"
        />
        <div className="mt-2">
          {tags.map((tag, index) => (
            <span
              key={index}
              className="inline-block bg-gray-200 rounded-full px-3 py-1 text-sm font-semibold text-gray-700 mr-2 mb-2"
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
      </div>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} onClick={handleLineClick}>
          <CartesianGrid strokeDasharray="5 5" />
          <XAxis dataKey="event" />
          <YAxis domain={["auto", "auto"]} />
          <Tooltip />
          <Legend />
          {getLines()}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

export default QubitCalibChart;
