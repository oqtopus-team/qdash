import { useQuery } from "@tanstack/react-query";

interface Task {
  task_id: string;
  name: string;
  status: string;
  message: string;
  input_parameters: Record<string, any>;
  output_parameters: Record<string, any>;
  output_parameter_names: string[];
  note: string;
  figure_path: string;
  raw_data_path: string;
  start_at: string;
  end_at: string;
  elapsed_time: number;
  task_type: string;
}

interface QubitDetail {
  result: {
    [key: string]: Task;
  };
}

interface MuxData {
  qubits: {
    [key: string]: QubitDetail;
  };
}

export const useListMuxes = (chipId: string) => {
  return useQuery<MuxData>({
    queryKey: ["muxes", chipId],
    queryFn: async () => {
      if (!chipId) return { qubits: {} };
      const response = await fetch(`/api/chips/${chipId}/muxes`);
      if (!response.ok) {
        throw new Error("Failed to fetch mux data");
      }
      return response.json();
    },
    enabled: !!chipId,
  });
};
