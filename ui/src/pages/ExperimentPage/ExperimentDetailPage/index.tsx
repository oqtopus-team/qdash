// import { useParams } from "react-router-dom";
// import { useFetchExecutionDetail } from "@/client/execution/execution";
// import JsonView from "react18-json-view";

// function ExecutionDetailPage() {
//   const { experiment_name, timestamp } = useParams<{
//     experiment_name: string;
//     timestamp: string;
//   }>();

//   const {
//     data: executionDetail,
//     isError,
//     isLoading,
//   } = useFetchExecutionDetail({
//     experiment_name,
//     timestamp,
//   });

//   if (isLoading) {
//     return <div>Loading...</div>;
//   }
//   if (isError) {
//     return <div>Error</div>;
//   }

//   return (
//     <div className="w-full px-4">
//       <h1 className="text-left text-3xl font-bold px-1 pb-3">
//         Execution Detail
//       </h1>
//       <div className="mb-6">
//         <h3 className="text-xl font-semibold mb-2">Figure</h3>
//         <img
//           src={`http://localhost:5715/executions/figure?path=${encodeURIComponent(
//             executionDetail.fig_path
//           )}`}
//           alt="Execution Figure"
//           className="w-full h-auto max-h-[60vh] object-contain rounded border"
//         />
//       </div>
//       <div className="mb-6">
//         <h3 className="text-xl font-semibold mb-2">Output Parameters</h3>
//         <div className="bg-gray-50 p-4 rounded-lg">
//           <JsonView src={executionDetail.output_parameter} theme="vscode" />
//         </div>
//       </div>
//       <div className="mb-6">
//         <h3 className="text-xl font-semibold mb-2">Input Parameters</h3>
//         <div className="bg-gray-50 p-4 rounded-lg">
//           <JsonView src={executionDetail.input_parameter} theme="vscode" />
//         </div>
//       </div>
//     </div>
//   );
// }

// export default ExecutionDetailPage;
