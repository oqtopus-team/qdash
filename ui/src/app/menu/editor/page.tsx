"use client";

import { useListMenu, useUpdateMenu, useDeleteMenu } from "@/client/menu/menu";
import { useFetchAllTasks } from "@/client/task/task";
import { GetMenuResponse, TaskResponse } from "@/schemas";
import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import Editor from "@monaco-editor/react";
import {
  BsPlus,
  BsFileEarmarkText,
  BsTrash,
  BsPlay,
  BsFileEarmarkPlus,
  BsDownload,
} from "react-icons/bs";
import TaskDetailList from "./TaskDetailList";

interface TaskSelectModalProps {
  onClose: () => void;
  onSelect: (task: TaskResponse) => void;
}

const TaskSelectModal: React.FC<TaskSelectModalProps> = ({
  onClose,
  onSelect,
}) => {
  const { data: tasksData } = useFetchAllTasks();
  const [selectedTask, setSelectedTask] = useState<TaskResponse | null>(null);

  // タスクをタイプごとにグループ化
  const groupedTasks =
    tasksData?.data?.tasks?.reduce(
      (acc: { [key: string]: TaskResponse[] }, task: TaskResponse) => {
        const type = task.task_type || "other";
        if (!acc[type]) {
          acc[type] = [];
        }
        acc[type].push(task);
        return acc;
      },
      {}
    ) || {};

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-base-100 rounded-xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-base-300 flex items-center justify-between bg-base-100/80 backdrop-blur supports-[backdrop-filter]:bg-base-100/60">
          <h2 className="text-2xl font-bold">Select Task</h2>
          <button
            onClick={onClose}
            className="btn btn-ghost btn-sm btn-square hover:rotate-90 transition-transform"
          >
            <BsPlus className="text-xl rotate-45" />
          </button>
        </div>
        <div className="p-8 overflow-y-auto">
          {Object.entries(groupedTasks).map(([type, tasks]) => (
            <div key={type} className="mb-8 last:mb-0">
              <h3 className="text-lg font-semibold mb-4 capitalize">{type}</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {tasks.map((task) => (
                  <div
                    key={task.name}
                    className={`p-4 rounded-lg border cursor-pointer hover:border-primary transition-colors ${
                      selectedTask?.name === task.name
                        ? "border-primary bg-primary/5"
                        : "border-base-300"
                    }`}
                    onClick={() => setSelectedTask(task)}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <h4 className="font-medium">{task.name}</h4>
                      <div className="badge badge-primary badge-outline">
                        {task.task_type}
                      </div>
                    </div>
                    {task.description && (
                      <p className="text-sm text-base-content/70 line-clamp-2">
                        {task.description}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="px-6 py-4 border-t border-base-300 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={() => selectedTask && onSelect(selectedTask)}
            disabled={!selectedTask}
          >
            Select
          </button>
        </div>
      </div>
    </div>
  );
};

import { ExecuteConfirmModal } from "./ExecuteConfirmModal";
import { DeleteConfirmModal } from "./DeleteConfirmModal";
import { CreateFromTemplateModal } from "./CreateFromTemplateModal";

export default function MenuEditorPage() {
  const searchParams = useSearchParams();
  const [showExecuteModal, setShowExecuteModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const { data: menusData, refetch: refetchMenus } = useListMenu();

  const updateMenu = useUpdateMenu();
  const deleteMutation = useDeleteMenu();
  const [selectedMenu, setSelectedMenu] = useState<GetMenuResponse | null>(
    null
  );
  const [selectedTaskDetail, setSelectedTaskDetail] = useState<string | null>(
    null
  );
  const [menuContent, setMenuContent] = useState<string>("");
  const [taskDetailContent, setTaskDetailContent] = useState<string>("");
  const [isTaskSelectOpen, setIsTaskSelectOpen] = useState(false);
  const [showCreateFromTemplate, setShowCreateFromTemplate] = useState(false);

  // task_detailが選択された時の処理
  const handleTaskDetailSelect = useCallback(
    (taskName: string, content: any) => {
      setSelectedTaskDetail(taskName);
      setTaskDetailContent(JSON.stringify(content, null, 2));
    },
    []
  );

  // メニューが選択された時の処理
  const handleMenuSelect = useCallback(
    (menu: GetMenuResponse) => {
      setSelectedMenu(menu);
      setMenuContent(
        JSON.stringify(
          {
            ...menu,
            task_details: undefined, // task_detailsは左側のエディターには表示しない
          },
          null,
          2
        )
      );
      // 最初のtask_detailを選択
      const firstTask = Object.keys(menu.task_details || {})[0];
      handleTaskDetailSelect(firstTask, menu.task_details?.[firstTask]);
    },
    [handleTaskDetailSelect]
  );

  useEffect(() => {
    if (menusData?.data?.menus && menusData.data.menus.length > 0) {
      const menuName = searchParams.get("name");
      if (menuName) {
        // URLパラメータで指定されたメニューを開く
        const menu = menusData.data.menus.find((m) => m.name === menuName);
        if (menu) {
          handleMenuSelect(menu);
        }
      } else if (!selectedMenu) {
        // メニューが選択されていない場合は最初のメニューを開く
        handleMenuSelect(menusData.data.menus[0]);
      }
    }
  }, [menusData, searchParams, selectedMenu, handleMenuSelect]);

  const handleSave = () => {
    if (!selectedMenu) return;
    try {
      const menuData = JSON.parse(menuContent);
      let updatedTaskDetails = selectedMenu.task_details || {};

      // 選択中のtask_detailがある場合は更新
      if (selectedTaskDetail) {
        try {
          const taskDetailData = JSON.parse(taskDetailContent);
          updatedTaskDetails = {
            ...updatedTaskDetails,
            [selectedTaskDetail]: taskDetailData,
          };
        } catch (e) {
          // task_detailのJSONが不正な場合は更新しない
          console.error("Invalid task detail JSON:", e);
          return;
        }
      }

      // メニュー全体を更新
      updateMenu.mutate(
        {
          name: selectedMenu.name,
          data: {
            ...menuData,
            task_details: updatedTaskDetails,
          },
        },
        {
          onSuccess: () => {
            // 保存成功
            setSelectedMenu({
              ...selectedMenu,
              ...menuData,
              task_details: updatedTaskDetails,
            });
          },
        }
      );
    } catch (e) {
      // メニューのJSONが不正な場合
      console.error("Invalid menu JSON:", e);
    }
  };

  // 新しいtask_detailを追加（最下部に追加）
  const handleAddTaskDetail = (task: TaskResponse) => {
    if (!selectedMenu) return;

    try {
      // 現在のmenuContentからtasksを取得
      const menuData = JSON.parse(menuContent);
      const currentTasks = menuData.tasks || [];

      // tasksの最後にタスクを追加
      const updatedTasks = [...currentTasks, task.name];
      const updatedTaskDetails = {
        ...selectedMenu.task_details,
        [task.name]: {
          input_parameters: task.input_parameters || {},
          output_parameters: task.output_parameters || {},
        },
      };

      // menuContentを更新
      setMenuContent(
        JSON.stringify(
          {
            ...menuData,
            tasks: updatedTasks,
          },
          null,
          2
        )
      );

      // task_detailsを更新
      updateMenu.mutate(
        {
          name: selectedMenu.name,
          data: {
            ...selectedMenu,
            tasks: updatedTasks,
            task_details: updatedTaskDetails,
          },
        },
        {
          onSuccess: () => {
            setSelectedTaskDetail(task.name);
            setTaskDetailContent(
              JSON.stringify(
                {
                  input_parameters: task.input_parameters || {},
                  output_parameters: task.output_parameters || {},
                },
                null,
                2
              )
            );
            setSelectedMenu({
              ...selectedMenu,
              tasks: updatedTasks,
              task_details: updatedTaskDetails,
            });
            setIsTaskSelectOpen(false);
          },
        }
      );
    } catch (e) {
      // JSON解析エラー
      console.error("Invalid JSON:", e);
    }
  };

  // ドラッグアンドドロップの処理
  const handleDragEnd = (result: any) => {
    if (!result.destination || !selectedMenu) return;

    try {
      const menuData = JSON.parse(menuContent);
      const currentTasks = menuData.tasks || [];
      const currentTaskDetails = selectedMenu.task_details || {};

      // task_detailsの順序を変更
      const taskEntries = Object.entries(currentTaskDetails);
      const [reorderedTask] = taskEntries.splice(result.source.index, 1);
      taskEntries.splice(result.destination.index, 0, reorderedTask);

      // tasksの順序も同期
      const [movedTask] = currentTasks.splice(result.source.index, 1);
      currentTasks.splice(result.destination.index, 0, movedTask);

      // 新しい順序でオブジェクトを再構築
      const updatedTaskDetails = Object.fromEntries(taskEntries);

      // menuContentを更新
      setMenuContent(
        JSON.stringify(
          {
            ...menuData,
            tasks: currentTasks,
          },
          null,
          2
        )
      );

      // task_detailsを更新
      updateMenu.mutate(
        {
          name: selectedMenu.name,
          data: {
            ...selectedMenu,
            tasks: currentTasks,
            task_details: updatedTaskDetails,
          },
        },
        {
          onSuccess: () => {
            setSelectedMenu({
              ...selectedMenu,
              tasks: currentTasks,
              task_details: updatedTaskDetails,
            });
          },
        }
      );
    } catch (e) {
      // JSON解析エラー
      console.error("Invalid JSON:", e);
    }
  };

  return (
    <div className="container mx-auto h-[calc(100vh-4rem)] max-w-[3000px] p-4">
      <div className="flex flex-col md:flex-row bg-base-200/50 backdrop-blur-sm rounded-lg shadow-xl overflow-hidden border border-base-300 h-full">
        {/* Menu Editor */}
        <div className="flex-1 md:w-[45%] flex flex-col md:flex-row h-full min-w-0">
          {/* File explorer */}
          <div className="w-full md:w-[25%] h-48 md:h-full bg-base-200/80 border-r border-base-300 flex flex-col shrink-0">
            <div className="px-4 py-3 border-b border-base-300 flex justify-between items-center shrink-0 bg-base-200/90">
              <h2 className="font-bold text-sm uppercase tracking-wide">
                Menus
              </h2>
              <div className="flex gap-1">
                <button
                  className="btn btn-ghost btn-sm btn-square"
                  onClick={() => setShowCreateFromTemplate(true)}
                  title="Create from template"
                >
                  <BsFileEarmarkPlus className="text-lg" />
                </button>
                <button
                  className="btn btn-ghost btn-sm btn-square"
                  onClick={() => {
                    setSelectedMenu(null);
                    setSelectedTaskDetail(null);
                    setMenuContent("");
                    setTaskDetailContent("");
                  }}
                  title="Create new"
                >
                  <BsPlus className="text-lg" />
                </button>
              </div>
            </div>
            <div className="overflow-y-auto flex-1 p-2">
              {menusData?.data?.menus?.map((menu) => (
                <div
                  key={menu.name}
                  className={`p-2 rounded cursor-pointer hover:bg-base-300/50 flex items-center gap-2 transition-colors ${
                    selectedMenu?.name === menu.name ? "bg-primary/10" : ""
                  }`}
                  onClick={() => handleMenuSelect(menu)}
                >
                  <BsFileEarmarkText className="text-base-content/70" />
                  <span className="font-medium text-sm truncate">
                    {menu.name}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Editor */}
          <div className="flex-1 flex flex-col min-w-0 h-full bg-base-100/50">
            {/* Editor toolbar */}
            <div className="px-4 py-2 border-b border-base-300 flex items-center justify-between shrink-0 bg-base-200/90">
              <div className="flex items-center gap-2">
                {selectedMenu && (
                  <>
                    <span className="font-medium text-sm">
                      {selectedMenu.name}
                    </span>
                    <div className="badge badge-sm badge-ghost">json</div>
                  </>
                )}
              </div>
              <div className="flex items-center gap-2">
                {selectedMenu && (
                  <>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => setShowExecuteModal(true)}
                    >
                      <BsPlay className="text-lg" />
                      <span>Execute</span>
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => {
                        const menuData = {
                          ...selectedMenu,
                          task_details: selectedMenu.task_details || {},
                        };
                        const blob = new Blob(
                          [JSON.stringify(menuData, null, 2)],
                          {
                            type: "application/json",
                          }
                        );
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement("a");
                        a.href = url;
                        a.download = `${selectedMenu.name}.json`;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        URL.revokeObjectURL(url);
                      }}
                    >
                      <BsDownload className="text-lg" />
                      <span>Download</span>
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => setShowDeleteModal(true)}
                    >
                      <BsTrash className="text-lg" />
                      <span>Delete</span>
                    </button>
                  </>
                )}
                <button
                  className="btn btn-primary btn-sm"
                  onClick={handleSave}
                  disabled={!selectedMenu}
                >
                  Save
                </button>
              </div>
            </div>

            {/* Editor content */}
            <div className="flex-1 overflow-auto p-3">
              <div className="h-full rounded-lg overflow-hidden bg-base-300/30 shadow-inner">
                <Editor
                  defaultLanguage="json"
                  value={menuContent}
                  onChange={(value: string | undefined) =>
                    setMenuContent(value || "")
                  }
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
                  }}
                  className="h-full"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Task Detail Editor */}
        <div className="flex-1 md:w-[55%] flex flex-col md:flex-row h-full border-t md:border-t-0 md:border-l border-base-300 min-w-0">
          {/* File explorer */}
          <div className="w-full md:w-[25%] h-48 md:h-full bg-base-200/80 border-r border-base-300 flex flex-col shrink-0">
            <div className="px-4 py-3 border-b border-base-300 flex justify-between items-center shrink-0 bg-base-200/90">
              <h2 className="font-bold text-sm uppercase tracking-wide">
                Task Details
              </h2>
              {selectedMenu && (
                <button
                  className="btn btn-ghost btn-sm btn-square"
                  onClick={() => setIsTaskSelectOpen(true)}
                >
                  <BsPlus className="text-lg" />
                </button>
              )}
            </div>
            {selectedMenu?.task_details && (
              <div className="flex-1 overflow-hidden">
                <TaskDetailList
                  tasks={selectedMenu.task_details}
                  selectedTask={selectedTaskDetail}
                  onTaskSelect={handleTaskDetailSelect}
                  onDragEnd={handleDragEnd}
                />
              </div>
            )}
          </div>

          {/* Editor */}
          <div className="flex-1 flex flex-col min-w-0 h-full bg-base-100/50">
            {/* Editor toolbar */}
            <div className="px-4 py-2 border-b border-base-300 flex items-center justify-between shrink-0 bg-base-200/90">
              <div className="flex items-center gap-2">
                {selectedMenu && selectedTaskDetail && (
                  <>
                    <span className="font-medium text-sm">
                      {selectedMenu.name}
                    </span>
                    <span className="text-base-content/70">/</span>
                    <span className="font-medium text-sm">
                      {selectedTaskDetail}
                    </span>
                    <div className="badge badge-sm badge-ghost">json</div>
                  </>
                )}
              </div>
            </div>

            {/* Editor content */}
            <div className="flex-1 overflow-auto p-3">
              <div className="h-full rounded-lg overflow-hidden bg-base-300/30 shadow-inner">
                <Editor
                  defaultLanguage="json"
                  value={taskDetailContent}
                  onChange={(value: string | undefined) =>
                    setTaskDetailContent(value || "")
                  }
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
                  }}
                  className="h-full"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Task Select Modal */}
      {isTaskSelectOpen && (
        <TaskSelectModal
          onClose={() => setIsTaskSelectOpen(false)}
          onSelect={handleAddTaskDetail}
        />
      )}
      {/* Execute Confirm Modal */}
      {showExecuteModal && selectedMenu && (
        <ExecuteConfirmModal
          selectedMenu={selectedMenu}
          onClose={() => setShowExecuteModal(false)}
        />
      )}

      {/* Delete Confirm Modal */}
      {showDeleteModal && selectedMenu && (
        <DeleteConfirmModal
          selectedMenu={selectedMenu}
          onConfirm={() => {
            deleteMutation.mutate(
              { name: selectedMenu.name },
              {
                onSuccess: () => {
                  setShowDeleteModal(false);
                  setSelectedMenu(null);
                  setSelectedTaskDetail(null);
                  setMenuContent("");
                  setTaskDetailContent("");
                  refetchMenus(); // 一覧を更新
                },
              }
            );
          }}
          onClose={() => setShowDeleteModal(false)}
        />
      )}

      {/* Create from Template Modal */}
      {showCreateFromTemplate && (
        <CreateFromTemplateModal
          onClose={() => setShowCreateFromTemplate(false)}
          onSuccess={() => {
            refetchMenus();
          }}
        />
      )}
    </div>
  );
}
