"use client";

import { useRouter } from "next/navigation";
import Editor from "@monaco-editor/react";
import { BsPlay } from "react-icons/bs";
import type { GetMenuResponse } from "@/schemas";

interface MenuPreviewModalProps {
  selectedItem: GetMenuResponse;
  onClose: () => void;
}

export function MenuPreviewModal({
  selectedItem,
  onClose,
}: MenuPreviewModalProps) {
  const router = useRouter();

  const handleEdit = () => {
    router.push(`/menu/editor?name=${selectedItem.name}`);
  };

  const menuContent = JSON.stringify(
    {
      ...selectedItem,
      task_details: undefined,
    },
    null,
    2
  );

  const taskDetailsContent = JSON.stringify(
    selectedItem.task_details || {},
    null,
    2
  );

  return (
    <dialog id="menuPreview" className="modal">
      <form
        method="dialog"
        className="modal-backdrop bg-base-100/30 backdrop-blur-sm"
      >
        <button>close</button>
      </form>
      <div className="fixed inset-0 bg-base-100/80 backdrop-blur supports-[backdrop-filter]:bg-base-100/60">
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="sticky top-0 px-6 py-4 border-b border-base-300 flex items-center justify-between bg-base-200/50 backdrop-blur-sm supports-[backdrop-filter]:bg-base-200/30 z-50">
            <h2 className="text-2xl font-bold">Menu Preview</h2>
            <div className="flex items-center gap-2">
              <button className="btn btn-primary" onClick={handleEdit}>
                <span>Edit in Menu Editor</span>
              </button>
              <button
                onClick={onClose}
                className="btn btn-ghost btn-sm btn-square hover:rotate-90 transition-transform"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 flex overflow-hidden h-[calc(100vh-4rem)]">
            {/* Menu Editor */}
            <div className="flex-1 flex flex-col min-w-0 border-r border-base-300">
              <div className="px-4 py-2 border-b border-base-300 flex items-center justify-between bg-base-200/50 backdrop-blur-sm supports-[backdrop-filter]:bg-base-200/30">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">
                    {selectedItem.name}
                  </span>
                  <div className="badge badge-sm badge-ghost">json</div>
                </div>
              </div>
              <div className="flex-1 overflow-auto p-3">
                <div className="h-full rounded-lg overflow-hidden bg-base-300/30 shadow-inner">
                  <Editor
                    defaultLanguage="json"
                    value={menuContent}
                    options={{
                      minimap: { enabled: false },
                      scrollBeyondLastLine: false,
                      fontSize: 14,
                      lineNumbers: "on",
                      renderLineHighlight: "all",
                      automaticLayout: true,
                      tabSize: 2,
                      wordWrap: "on",
                      theme: "vs-dark",
                      readOnly: true,
                    }}
                    className="h-full"
                  />
                </div>
              </div>
            </div>

            {/* Task Details Editor */}
            <div className="flex-1 flex flex-col min-w-0">
              <div className="px-4 py-2 border-b border-base-300 flex items-center justify-between bg-base-200/50 backdrop-blur-sm supports-[backdrop-filter]:bg-base-200/30">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">Task Details</span>
                  <div className="badge badge-sm badge-ghost">json</div>
                </div>
              </div>
              <div className="flex-1 overflow-auto p-3">
                <div className="h-full rounded-lg overflow-hidden bg-base-300/30 shadow-inner">
                  <Editor
                    defaultLanguage="json"
                    value={taskDetailsContent}
                    options={{
                      minimap: { enabled: false },
                      scrollBeyondLastLine: false,
                      fontSize: 14,
                      lineNumbers: "on",
                      renderLineHighlight: "all",
                      automaticLayout: true,
                      tabSize: 2,
                      wordWrap: "on",
                      theme: "vs-dark",
                      readOnly: true,
                    }}
                    className="h-full"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </dialog>
  );
}
