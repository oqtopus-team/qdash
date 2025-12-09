"use client";

import dynamic from "next/dynamic";
import { useState, useEffect } from "react";

import {
  useListFlowHelperFiles,
  useGetFlowHelperFile,
} from "@/client/flow/flow";

// Monaco Editor for viewing helper files (read-only)
const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

export function FlowImportsPanel() {
  const [selectedFile, setSelectedFile] = useState<string | null>(null);

  // Fetch list of helper files using generated client
  const { data: files, isLoading: isLoadingFiles } = useListFlowHelperFiles({
    query: {
      staleTime: 1000 * 60 * 60, // Cache for 1 hour
    },
  });

  // Auto-select first file when files are loaded
  useEffect(() => {
    if (files?.data && files.data.length > 0 && !selectedFile) {
      setSelectedFile(files.data[0]);
    }
  }, [files, selectedFile]);

  // Fetch selected file content using generated client
  const { data: fileContent, isLoading: isLoadingContent } =
    useGetFlowHelperFile(selectedFile || "", {
      query: {
        enabled: !!selectedFile,
        staleTime: 1000 * 60 * 60, // Cache for 1 hour
      },
    });

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-base-300">
      {/* File Tabs */}
      <div className="flex items-center bg-base-200 border-b border-base-300 overflow-x-auto">
        <div className="flex items-center px-3 py-1 border-r border-base-300">
          <span className="text-[10px] text-base-content/50 uppercase tracking-wider">
            qdash.workflow.flow
          </span>
        </div>
        {isLoadingFiles ? (
          <div className="px-3 py-2 text-xs text-base-content/50">
            Loading...
          </div>
        ) : (
          <div className="flex">
            {files?.data?.map((file) => (
              <button
                key={file}
                onClick={() => setSelectedFile(file)}
                className={`px-3 py-1.5 text-xs font-mono border-r border-base-300 flex items-center gap-1.5 transition-colors ${
                  selectedFile === file
                    ? "bg-base-300 text-base-content border-t-2 border-t-primary"
                    : "bg-base-200 text-base-content/60 hover:bg-base-300/50 border-t-2 border-t-transparent"
                }`}
              >
                <span className="text-info">py</span>
                {file}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* File Content Viewer */}
      <div className="flex-1 flex overflow-hidden">
        {selectedFile ? (
          <div className="flex-1 relative">
            {isLoadingContent ? (
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="loading loading-spinner loading-md text-base-content/50"></span>
              </div>
            ) : (
              <Editor
                height="100%"
                language="python"
                theme="vs-dark"
                value={fileContent?.data || ""}
                options={{
                  readOnly: true,
                  minimap: { enabled: true },
                  fontSize: 14,
                  lineNumbers: "on",
                  scrollBeyondLastLine: true,
                  wordWrap: "on",
                  folding: true,
                  padding: { top: 16, bottom: 16 },
                  renderLineHighlight: "all",
                }}
              />
            )}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-sm text-base-content/50">
            Select a file to view the implementation
          </div>
        )}
      </div>

      {/* Footer hint */}
      <div className="px-4 py-2 bg-base-200 border-t border-base-300 text-xs text-base-content/50">
        <code className="text-secondary">
          from qdash.workflow.flow import ...
        </code>
        <span className="ml-4 text-base-content/30">Read-only reference</span>
      </div>
    </div>
  );
}
