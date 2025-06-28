"use client";

import { Suspense } from "react";
import { DndContext, DragEndEvent } from "@dnd-kit/core";
import {
  useListMenu,
  useUpdateMenu,
  useDeleteMenu,
  useCreateMenu,
} from "@/client/menu/menu";
import { useFetchAllTasks } from "@/client/task/task";
import { useFetchExecutionLockStatus } from "@/client/execution/execution";
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
  BsCopy,
} from "react-icons/bs";
import TaskDetailList from "./TaskDetailList";
import { ExecuteConfirmModal } from "./ExecuteConfirmModal";
import { DeleteConfirmModal } from "./DeleteConfirmModal";
import { DeleteTaskConfirmModal } from "./DeleteTaskConfirmModal";
import { BulkDeleteTasksConfirmModal } from "./BulkDeleteTasksConfirmModal";
import { CreateFromTemplateModal } from "./CreateFromTemplateModal";
import { Toast } from "@/app/setting/components/Toast";

import AvailableTasksList from "./AvailableTasksList";
import DroppableTaskList from "./DroppableTaskList";

interface TaskSelectModalProps {
  onClose: () => void;
  onSelect: (tasks: TaskResponse[]) => void;
}

const TaskSelectModal: React.FC<TaskSelectModalProps> = ({
  onClose,
  onSelect,
}) => {
  const { data: tasksData } = useFetchAllTasks();
  const [selectedTasks, setSelectedTasks] = useState<TaskResponse[]>([]);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || !active.data.current) return;

    // If dragging from available tasks to task list
    if (over.id === "task-list" && "task_type" in active.data.current) {
      const task = active.data.current as TaskResponse;
      if (!selectedTasks.find((t) => t.name === task.name)) {
        setSelectedTasks([...selectedTasks, task]);
      }
    }
  };

  const handleTaskClick = (task: TaskResponse) => {
    if (!selectedTasks.find((t) => t.name === task.name)) {
      setSelectedTasks([...selectedTasks, task]);
    }
  };

  const handleRemoveTask = (taskName: string) => {
    setSelectedTasks(selectedTasks.filter((t) => t.name !== taskName));
  };

  return (
    <DndContext onDragEnd={handleDragEnd}>
      <div
        className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 backdrop-blur-sm p-4"
        onClick={onClose}
      >
        <div
          className="bg-base-100 rounded-xl w-full max-w-5xl max-h-[85vh] overflow-hidden flex flex-col shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="px-6 py-4 border-b border-base-300 flex items-center justify-between bg-base-100/80 backdrop-blur supports-[backdrop-filter]:bg-base-100/60">
            <h2 className="text-2xl font-bold">Select Tasks</h2>
            <div className="flex items-center gap-2">
              <button
                className="btn btn-primary btn-sm"
                onClick={() => {
                  onSelect(selectedTasks);
                  onClose();
                }}
                disabled={selectedTasks.length === 0}
              >
                Save
              </button>
              <button
                onClick={onClose}
                className="btn btn-ghost btn-sm btn-square hover:rotate-90 transition-transform"
              >
                <BsPlus className="text-xl rotate-45" />
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-hidden flex gap-4 p-4">
            {/* Left side: Available tasks */}
            <div className="w-1/2">
              {tasksData?.data?.tasks && (
                <AvailableTasksList
                  tasks={tasksData.data.tasks}
                  onTaskSelect={handleTaskClick}
                />
              )}
            </div>

            {/* Right side: Selected tasks */}
            <div className="w-1/2 flex flex-col overflow-hidden">
              <div className="flex items-center justify-between mb-4 shrink-0">
                <h3 className="text-lg font-semibold">Selected Tasks</h3>
                <span className="text-sm text-base-content/70">
                  {selectedTasks.length} tasks
                </span>
              </div>
              <DroppableTaskList
                id="task-list"
                className="flex-1 overflow-y-auto"
              >
                <div className="space-y-2">
                  {selectedTasks.map((task) => (
                    <div
                      key={task.name}
                      className="p-3 rounded-lg bg-base-100 border border-base-300 hover:border-primary group shadow-sm"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
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
                        <button
                          onClick={() => handleRemoveTask(task.name)}
                          className="btn btn-ghost btn-xs btn-square hover:text-error opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <BsTrash className="text-sm" />
                        </button>
                      </div>
                    </div>
                  ))}
                  {selectedTasks.length === 0 && (
                    <div className="text-base-content/50 text-center py-8">
                      <svg
                        className="mx-auto h-12 w-12 text-base-content/30"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        aria-hidden="true"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                        />
                      </svg>
                      <h3 className="mt-2 text-sm font-medium">
                        No tasks selected
                      </h3>
                      <p className="mt-1 text-sm text-base-content/70">
                        Drag tasks from the left or click to add them
                      </p>
                    </div>
                  )}
                </div>
              </DroppableTaskList>
            </div>
          </div>
        </div>
      </div>
    </DndContext>
  );
};

function MenuEditor() {
  const searchParams = useSearchParams();
  const [showExecuteModal, setShowExecuteModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showDeleteTaskModal, setShowDeleteTaskModal] = useState(false);
  const [taskToDelete, setTaskToDelete] = useState<string | null>(null);
  const [tasksToDelete, setTasksToDelete] = useState<string[]>([]);
  const [showBulkDeleteModal, setShowBulkDeleteModal] = useState(false);
  const { data: menusData, refetch: refetchMenus } = useListMenu();
  const { data: lockStatus, isLoading: isLockStatusLoading } =
    useFetchExecutionLockStatus({
      query: {
        refetchInterval: 5000, // 5秒ごとに更新
      },
    });

  const updateMenu = useUpdateMenu();
  const deleteMutation = useDeleteMenu();
  const createMenu = useCreateMenu();
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
  const [showSaveToast, setShowSaveToast] = useState(false);

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
            setShowSaveToast(true);
          },
        }
      );
    } catch (e) {
      // メニューのJSONが不正な場合
      console.error("Invalid menu JSON:", e);
    }
  };

  // 新しいtask_detailを追加（最下部に追加）
  const handleAddTaskDetails = (tasks: TaskResponse[]) => {
    if (!selectedMenu) return;

    try {
      // 現在のmenuContentからtasksを取得
      const menuData = JSON.parse(menuContent);
      const currentTasks = menuData.tasks || [];

      // Add all tasks to the end
      const updatedTasks = [...currentTasks];
      const updatedTaskDetails = { ...selectedMenu.task_details };

      tasks.forEach((task) => {
        if (!currentTasks.includes(task.name)) {
          updatedTasks.push(task.name);
          updatedTaskDetails[task.name] = {
            input_parameters: task.input_parameters || {},
            output_parameters: task.output_parameters || {},
          };
        }
      });

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
            // Select the last added task
            const lastTask = tasks[tasks.length - 1];
            setSelectedTaskDetail(lastTask.name);
            setTaskDetailContent(
              JSON.stringify(
                {
                  input_parameters: lastTask.input_parameters || {},
                  output_parameters: lastTask.output_parameters || {},
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
          },
        }
      );
    } catch (e) {
      // JSON解析エラー
      console.error("Invalid JSON:", e);
    }
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || !active.data.current) return;

    // If dragging from available tasks to task list in the main view
    if (
      !isTaskSelectOpen &&
      over.id === "task-list" &&
      "task_type" in active.data.current
    ) {
      handleAddTaskDetails([active.data.current as TaskResponse]);
    }
    // If reordering within task list
    else if (active.id !== over.id && selectedMenu?.tasks) {
      const taskNames = selectedMenu.tasks;
      const sourceIndex = taskNames.indexOf(active.id.toString());
      const destinationIndex = taskNames.indexOf(over.id.toString());

      if (sourceIndex !== -1 && destinationIndex !== -1) {
        // Create new array with reordered tasks
        const newTasks = [...taskNames];
        const [movedTask] = newTasks.splice(sourceIndex, 1);
        newTasks.splice(destinationIndex, 0, movedTask);

        // Update menu content
        const menuData = JSON.parse(menuContent);
        menuData.tasks = newTasks;
        setMenuContent(JSON.stringify(menuData, null, 2));

        // Update menu state
        updateMenu.mutate({
          name: selectedMenu.name,
          data: {
            ...selectedMenu,
            tasks: newTasks,
          },
        });
      }
    }
  };

  return (
    <DndContext onDragEnd={handleDragEnd}>
      <div className="container mx-auto h-[calc(100vh-4rem)] max-w-[3000px] p-4">
        <div className="flex flex-col md:flex-row bg-base-200/50 backdrop-blur-sm rounded-lg shadow-xl overflow-hidden border border-base-300 h-full gap-px relative">
          {/* Menu Editor */}
          <div className="flex-1 md:w-[30%] flex flex-col md:flex-row h-full min-w-0">
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
                    className={`p-2 rounded cursor-pointer hover:bg-base-300/50 flex items-center gap-2 transition-colors group ${
                      selectedMenu?.name === menu.name ? "bg-primary/10" : ""
                    }`}
                    onClick={() => handleMenuSelect(menu)}
                  >
                    <BsFileEarmarkText className="text-base-content/70" />
                    <span className="font-medium text-sm truncate flex-1">
                      {menu.name}
                    </span>
                    <button
                      className="btn btn-ghost btn-xs btn-square opacity-50 hover:opacity-100 transition-opacity tooltip tooltip-left"
                      data-tip="Duplicate menu"
                      onClick={(e) => {
                        e.stopPropagation();
                        const newName = `${menu.name}_copy`;
                        const menuData = {
                          ...menu,
                          name: newName,
                        };
                        createMenu.mutate(
                          { data: menuData },
                          {
                            onSuccess: () => {
                              refetchMenus();
                            },
                          }
                        );
                      }}
                      title="Duplicate menu"
                    >
                      <BsCopy className="text-sm" />
                    </button>
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
                        className={`btn btn-sm ${
                          lockStatus?.data.lock ? "btn-disabled" : "btn-success"
                        }`}
                        onClick={() => setShowExecuteModal(true)}
                        disabled={lockStatus?.data.lock || isLockStatusLoading}
                      >
                        <BsPlay className="text-lg" />
                        <span>
                          {lockStatus?.data.lock ? "Locked" : "Execute"}
                        </span>
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
          <div className="flex-1 md:w-[40%] flex flex-col md:flex-row h-full border-t md:border-t-0 md:border-l border-base-300 min-w-0">
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
                    title="Add task"
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
                    onDeleteTask={(taskName) => {
                      setTaskToDelete(taskName);
                      setShowDeleteTaskModal(true);
                    }}
                    onBulkDeleteTasks={(taskNames) => {
                      setTasksToDelete(taskNames);
                      setShowBulkDeleteModal(true);
                    }}
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

        {/* Save Success Toast */}
        {showSaveToast && (
          <div className="fixed bottom-4 right-4 z-50">
            <Toast
              message="変更を保存しました"
              onClose={() => setShowSaveToast(false)}
            />
          </div>
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

        {/* Bulk Delete Tasks Confirm Modal */}
        {showBulkDeleteModal && tasksToDelete.length > 0 && selectedMenu && (
          <BulkDeleteTasksConfirmModal
            taskNames={tasksToDelete}
            onConfirm={() => {
              try {
                // メニューデータを取得
                const menuData = JSON.parse(menuContent);
                const currentTasks = menuData.tasks || [];
                const currentTaskDetails = { ...selectedMenu.task_details };

                // タスクを削除
                const updatedTasks = currentTasks.filter(
                  (task: string) => !tasksToDelete.includes(task)
                );

                // task_detailsから削除
                tasksToDelete.forEach((taskName) => {
                  delete currentTaskDetails[taskName];
                });

                // メニューを更新
                updateMenu.mutate(
                  {
                    name: selectedMenu.name,
                    data: {
                      ...selectedMenu,
                      tasks: updatedTasks,
                      task_details: currentTaskDetails,
                    },
                  },
                  {
                    onSuccess: () => {
                      setShowBulkDeleteModal(false);
                      setTasksToDelete([]);
                      if (
                        selectedTaskDetail &&
                        tasksToDelete.includes(selectedTaskDetail)
                      ) {
                        setSelectedTaskDetail(null);
                        setTaskDetailContent("");
                      }
                      setSelectedMenu({
                        ...selectedMenu,
                        tasks: updatedTasks,
                        task_details: currentTaskDetails,
                      });
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
                    },
                  }
                );
              } catch (e) {
                console.error("Invalid JSON:", e);
              }
            }}
            onClose={() => {
              setShowBulkDeleteModal(false);
              setTasksToDelete([]);
            }}
          />
        )}

        {/* Delete Task Confirm Modal */}
        {showDeleteTaskModal && taskToDelete && selectedMenu && (
          <DeleteTaskConfirmModal
            taskName={taskToDelete}
            onConfirm={() => {
              try {
                // メニューデータを取得
                const menuData = JSON.parse(menuContent);
                const currentTasks = menuData.tasks || [];
                const currentTaskDetails = { ...selectedMenu.task_details };

                // タスクを削除
                const taskIndex = currentTasks.indexOf(taskToDelete);
                if (taskIndex > -1) {
                  currentTasks.splice(taskIndex, 1);
                }
                delete currentTaskDetails[taskToDelete];

                // メニューを更新
                updateMenu.mutate(
                  {
                    name: selectedMenu.name,
                    data: {
                      ...selectedMenu,
                      tasks: currentTasks,
                      task_details: currentTaskDetails,
                    },
                  },
                  {
                    onSuccess: () => {
                      setShowDeleteTaskModal(false);
                      setTaskToDelete(null);
                      if (selectedTaskDetail === taskToDelete) {
                        setSelectedTaskDetail(null);
                        setTaskDetailContent("");
                      }
                      setSelectedMenu({
                        ...selectedMenu,
                        tasks: currentTasks,
                        task_details: currentTaskDetails,
                      });
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
                    },
                  }
                );
              } catch (e) {
                console.error("Invalid JSON:", e);
              }
            }}
            onClose={() => {
              setShowDeleteTaskModal(false);
              setTaskToDelete(null);
            }}
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

        {/* Task Select Modal */}
        {isTaskSelectOpen && (
          <TaskSelectModal
            onClose={() => setIsTaskSelectOpen(false)}
            onSelect={(tasks) => {
              handleAddTaskDetails(tasks);
              setIsTaskSelectOpen(false);
            }}
          />
        )}
      </div>
    </DndContext>
  );
}

export default function MenuEditorPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-[calc(100vh-4rem)]">
          <div className="loading loading-spinner loading-lg text-primary"></div>
        </div>
      }
    >
      <MenuEditor />
    </Suspense>
  );
}
