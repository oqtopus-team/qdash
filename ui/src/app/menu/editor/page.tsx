"use client";

import { useListMenu, useCreateMenu, useUpdateMenu } from "@/client/menu/menu";
import { useFetchAllTasks } from "@/client/task/task";
import { CreateMenuRequest, GetMenuResponse, TaskResponse } from "@/schemas";
import { useState, useRef, useEffect } from "react";
import Editor from "@monaco-editor/react";
import { BsPlus, BsFolder, BsFileEarmarkText } from "react-icons/bs";
import { DropResult } from "react-beautiful-dnd";
import TaskDetailList from "./TaskDetailList";

interface TaskSelectModalProps {
  onClose: () => void;
  onSelect: (task: TaskResponse) => void;
}

const TaskSelectModal = ({ onClose, onSelect }: TaskSelectModalProps) => {
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

export default function MenuEditorPage() {
  const { data: menusData } = useListMenu();
  const createMenu = useCreateMenu();
  const updateMenu = useUpdateMenu();
  const [selectedMenu, setSelectedMenu] = useState<GetMenuResponse | null>(
    null
  );
  const [selectedTaskDetail, setSelectedTaskDetail] = useState<string | null>(
    null
  );
  const [menuContent, setMenuContent] = useState<string>("");
  const [taskDetailContent, setTaskDetailContent] = useState<string>("");
  const [isTaskSelectOpen, setIsTaskSelectOpen] = useState(false);

  // メニューが選択された時の処理
  const handleMenuSelect = (menu: GetMenuResponse) => {
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
  };

  // task_detailが選択された時の処理
  const handleTaskDetailSelect = (taskName: string, content: any) => {
    setSelectedTaskDetail(taskName);
    setTaskDetailContent(JSON.stringify(content, null, 2));
  };

  // メニューの保存（メニュー全体とtask_detailsを同時に保存）
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
  const handleDragEnd = (result: DropResult) => {
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

  // menuContentの変更を監視してtask_detailsを更新
  useEffect(() => {
    if (!selectedMenu) return;

    try {
      const menuData = JSON.parse(menuContent);
      const tasks = menuData.tasks || [];
      const currentTaskDetails = selectedMenu.task_details || {};

      // tasksに存在しないtask_detailsを削除
      const updatedTaskDetails = Object.entries(currentTaskDetails).reduce(
        (acc, [key, value]) => {
          if (tasks.includes(key)) {
            acc[key] = value;
          }
          return acc;
        },
        {} as Record<string, any>
      );

      // task_detailsが変更された場合のみ更新
      if (
        JSON.stringify(updatedTaskDetails) !==
        JSON.stringify(selectedMenu.task_details)
      ) {
        setSelectedMenu({
          ...selectedMenu,
          task_details: updatedTaskDetails,
        });

        // 現在選択中のtask_detailが削除された場合、選択を解除
        if (
          selectedTaskDetail &&
          !Object.keys(updatedTaskDetails).includes(selectedTaskDetail)
        ) {
          setSelectedTaskDetail(null);
          setTaskDetailContent("");
        }
      }
    } catch (e) {
      // Invalid JSON, ignore
    }
  }, [menuContent, selectedMenu]);

  return (
    <div className="h-screen w-full">
      <div className="flex flex-col md:flex-row h-full">
        {/* Menu Editor */}
        <div className="flex-1 md:w-[35%] flex flex-col md:flex-row h-1/2 md:h-full min-w-0">
          {/* File explorer */}
          <div className="w-full md:w-48 h-48 md:h-full bg-base-200 border-r border-base-300 flex flex-col shrink-0 overflow-hidden">
            <div className="p-4 border-b border-base-300 flex justify-between items-center">
              <h2 className="font-bold">MENUS</h2>
              <button
                className="btn btn-ghost btn-sm btn-square"
                onClick={() => {
                  setSelectedMenu(null);
                  setSelectedTaskDetail(null);
                  setMenuContent("");
                  setTaskDetailContent("");
                }}
              >
                <BsPlus className="text-xl" />
              </button>
            </div>
            <div className="overflow-y-auto flex-1 p-2">
              {menusData?.data?.menus?.map((menu) => (
                <div
                  key={menu.name}
                  className={`p-2 rounded cursor-pointer hover:bg-base-300 flex items-center gap-2 ${
                    selectedMenu?.name === menu.name ? "bg-base-300" : ""
                  }`}
                  onClick={() => handleMenuSelect(menu)}
                >
                  <BsFileEarmarkText className="text-base-content/70" />
                  <span className="font-medium">{menu.name}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Editor */}
          <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
            {/* Editor toolbar */}
            <div className="bg-base-200 border-b border-base-300 p-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                {selectedMenu && (
                  <>
                    <span className="font-medium">{selectedMenu.name}</span>
                    <div className="badge badge-sm">json</div>
                  </>
                )}
              </div>
              <button
                className="btn btn-primary btn-sm"
                onClick={handleSave}
                disabled={!selectedMenu}
              >
                Save
              </button>
            </div>

            {/* Editor content */}
            <div className="flex-1 overflow-hidden">
              <Editor
                defaultLanguage="json"
                value={menuContent}
                onChange={(value) => setMenuContent(value || "")}
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
              />
            </div>
          </div>
        </div>

        {/* Task Detail Editor */}
        <div className="flex-1 md:w-[65%] flex flex-col md:flex-row h-1/2 md:h-full border-t md:border-t-0 md:border-l border-base-300 min-w-0">
          {/* File explorer */}
          <div className="w-full md:w-48 h-48 md:h-full bg-base-200 border-r border-base-300 flex flex-col shrink-0 overflow-hidden">
            <div className="p-4 border-b border-base-300 flex justify-between items-center">
              <h2 className="font-bold">TASK DETAILS</h2>
              {selectedMenu && (
                <button
                  className="btn btn-ghost btn-sm btn-square"
                  onClick={() => setIsTaskSelectOpen(true)}
                >
                  <BsPlus className="text-xl" />
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
          <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
            {/* Editor toolbar */}
            <div className="bg-base-200 border-b border-base-300 p-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                {selectedMenu && selectedTaskDetail && (
                  <>
                    <span className="font-medium">{selectedMenu.name}</span>
                    <span className="text-base-content/70">/</span>
                    <span className="font-medium">{selectedTaskDetail}</span>
                    <div className="badge badge-sm">json</div>
                  </>
                )}
              </div>
            </div>

            {/* Editor content */}
            <div className="flex-1 overflow-hidden">
              <Editor
                defaultLanguage="json"
                value={taskDetailContent}
                onChange={(value) => setTaskDetailContent(value || "")}
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
              />
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
      </div>
    </div>
  );
}
