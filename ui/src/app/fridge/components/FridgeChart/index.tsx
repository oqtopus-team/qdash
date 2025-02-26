import { useEffect, useState } from "react";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

import type { ListFridgeResponse } from "@/schemas";

import { useFridgesGetFridgeTemperature } from "@/client/fridges/fridges";
import { LoadingSpinner } from "@/components/LoadingSpinner";

type FridgeChartProps = {
  channel: number;
  hours?: number;
  name: string;
};

export function FridgeChart({ channel, hours, name }: FridgeChartProps) {
  const [chartData, setChartData] = useState<ListFridgeResponse[]>([]);

  const { data, isError, isLoading } = useFridgesGetFridgeTemperature(channel, {
    h: hours,
  });

  useEffect(() => {
    if (data) {
      setChartData(data.data);
    }
  }, [data]);

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (isError) {
    return <div>Error</div>;
  }

  // 温度のフォーマット関数
  const formatTemperature = (temp: number) => {
    if (temp < 0.1) {
      return `${(temp * 1000).toFixed(2)} mK`; // 0.1K未満はmKに変換
    }
    return `${temp.toFixed(2)} K`; // それ以外はK表示
  };

  // 最後の配列データを取得
  const lastDataPoint =
    chartData.length > 0 ? chartData[chartData.length - 1] : null;
  const lastTemperature = lastDataPoint
    ? formatTemperature(lastDataPoint.temperature)
    : "N/A";
  const yAxisDomain =
    name === "MXC-FLANGE"
      ? [0, 0.03]
      : name === "4K-FLANGE"
      ? [0, 10]
      : ["auto", "auto"];
  return (
    <div className="h-full">
      <div className="flex justify-between">
        <h2 className="text-left text-3xl font-bold my-4">
          C{channel}:{name}
        </h2>
        <div className="flex justify-end items-center my-4"></div>
      </div>

      <div className="text-3xl font-semibold">{lastTemperature}</div>

      <div className="h-96">
        <div className="h-full w-full">
          <div className="card bg-base-200 w-full h-full">
            <div className="card-body bg-base-200 h-full w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  width={500}
                  height={300}
                  data={chartData}
                  margin={{
                    top: 5,
                    right: 30,
                    left: 20,
                    bottom: 5,
                  }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <defs>
                    <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#8884d8" stopOpacity={0.8} />
                      <stop offset="95%" stopColor="#8884d8" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="timestamp" />
                  <YAxis domain={yAxisDomain} />
                  <Tooltip
                    formatter={(value: number) => formatTemperature(value)} // TooltipにもmK/Kのフォーマットを適用
                  />
                  {name === "MXC-FLANGE" && (
                    <ReferenceLine y={0.02} stroke="red" label="20mK" />
                  )}
                  {name === "4K-FLANGE" && (
                    <ReferenceLine y={5} stroke="blue" label="5K" />
                  )}
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey={"temperature"}
                    animationEasing="linear"
                    stroke="#8884d8"
                    strokeWidth={2}
                    activeDot={{ r: 8 }}
                    fillOpacity={1}
                    fill="url(#grad)"
                  />
                  <CartesianGrid stroke="#ccc" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
