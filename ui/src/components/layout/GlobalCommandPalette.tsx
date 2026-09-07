"use client";

import { Braces, Check, FolderKanban, Gauge, Link, Palette, Search } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useGetTaskFileSettings, useListTaskInfo } from "@/client/task-file/task-file";
import { getNavigationSections } from "@/components/layout/navigation";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/Command";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { useTheme } from "@/contexts/ThemeContext";
import { AVAILABLE_THEMES } from "@/constants/themes";
import { useToast } from "@/components/ui/Toast";

export function GlobalCommandPalette() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const { canEdit, projects, projectId, switchProject } = useProject();
  const { theme, setTheme } = useTheme();
  const toast = useToast();
  const [shortcut, setShortcut] = useState("Ctrl K");
  const [open, setOpen] = useState(false);
  const isDashboard = pathname === "/dashboard";
  const isMetrics = pathname === "/metrics";
  const isTasks = pathname === "/tasks";
  const hasMetricCommands = isDashboard || isMetrics;
  const { qubitMetrics, couplingMetrics } = useMetricsConfig(hasMetricCommands);
  const { data: taskFileSettings } = useGetTaskFileSettings({
    query: { enabled: isTasks, staleTime: 60_000 },
  });
  const defaultTaskBackend = taskFileSettings?.data?.default_backend ?? "";
  const taskBackend = searchParams.get("backend") || defaultTaskBackend;
  const { data: taskInfoData } = useListTaskInfo(
    { backend: taskBackend || "__none__" },
    { query: { enabled: isTasks && !!taskBackend, staleTime: 60_000 } },
  );
  const taskCommands = taskInfoData?.data?.tasks ?? [];
  const sections = getNavigationSections({
    canEdit,
    isAdmin: user?.system_role === "admin",
  });

  useEffect(() => {
    setShortcut(/Mac|iPhone|iPad/.test(navigator.platform) ? "⌘K" : "Ctrl K");
    const handleKeyDown = (event: KeyboardEvent) => {
      if (
        (event.metaKey || event.ctrlKey) &&
        event.key.toLowerCase() === "k" &&
        !event.isComposing &&
        !event.repeat &&
        !event.altKey &&
        !event.defaultPrevented
      ) {
        event.preventDefault();
        setOpen((current) => !current);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const navigate = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  const copyPageLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setOpen(false);
      toast.success("Page link copied");
    } catch {
      toast.error("Could not copy the link. Please copy it from the address bar.");
    }
  };

  const jumpToMetric = (metricId: string) => {
    setOpen(false);
    window.setTimeout(() => {
      document.getElementById(metricId)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 0);
  };

  const selectMetricsPageMetric = (metricType: "qubit" | "coupling", metricKey: string) => {
    const params = new URLSearchParams(window.location.search);
    if (metricType === "qubit") params.delete("type");
    else params.set("type", "coupling");
    if (metricKey === "t1") params.delete("metric");
    else params.set("metric", metricKey);
    const query = params.toString();
    navigate(query ? `/metrics?${query}` : "/metrics");
  };

  const selectMetric = (metricType: "qubit" | "coupling", metricKey: string) => {
    if (isMetrics) {
      selectMetricsPageMetric(metricType, metricKey);
      return;
    }
    jumpToMetric(`dashboard-${metricType}-metric-${metricKey}`);
  };

  const selectTask = (taskName: string) => {
    const params = new URLSearchParams(window.location.search);
    params.set("backend", taskBackend);
    params.set("task", taskName);
    params.delete("execution");
    params.delete("executionChip");
    params.delete("executionTarget");
    navigate(`/tasks?${params.toString()}`);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="btn btn-ghost btn-sm gap-2 text-base-content/60"
        aria-label="Open navigation search"
      >
        <Search size={15} aria-hidden="true" />
        <span className="hidden sm:inline">Commands</span>
        <kbd className="hidden rounded border border-base-300 bg-base-200 px-1.5 py-0.5 text-xs font-normal md:inline">
          {shortcut}
        </kbd>
      </button>

      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Commands"
        description="Search pages, actions, projects, and themes. Use arrow keys to choose and Enter to run."
      >
        <Command loop label="QDash navigation">
          <CommandInput
            placeholder={
              hasMetricCommands
                ? "Search pages, metrics, and actions..."
                : isTasks
                  ? "Search pages, tasks, and actions..."
                  : "Search pages and actions..."
            }
          />
          <CommandList>
            <CommandEmpty>No matching results</CommandEmpty>
            {isTasks && taskCommands.length > 0 && (
              <CommandGroup heading="Open task">
                {taskCommands.map((task) => (
                  <CommandItem
                    key={`${task.file_path}-${task.name}`}
                    value={`${task.name} task`}
                    keywords={[task.task_type ?? "", task.file_path, taskBackend]}
                    onSelect={() => selectTask(task.name)}
                  >
                    <Braces size={15} className="shrink-0 opacity-60" aria-hidden="true" />
                    <span>{task.name}</span>
                    <span className="ml-auto text-xs text-base-content/40">
                      {task.task_type || "Other"}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {hasMetricCommands && (qubitMetrics.length > 0 || couplingMetrics.length > 0) && (
              <CommandGroup heading={isMetrics ? "Switch metric" : "Dashboard metrics"}>
                {qubitMetrics.map((metric) => (
                  <CommandItem
                    key={`qubit-${metric.key}`}
                    value={`${metric.title} qubit metric`}
                    keywords={[metric.key, "dashboard", "qubit"]}
                    onSelect={() => selectMetric("qubit", metric.key)}
                  >
                    <Gauge size={15} className="shrink-0 opacity-60" aria-hidden="true" />
                    <span>{metric.title}</span>
                    <span className="ml-auto text-xs text-base-content/40">Qubit</span>
                  </CommandItem>
                ))}
                {couplingMetrics.map((metric) => (
                  <CommandItem
                    key={`coupling-${metric.key}`}
                    value={`${metric.title} coupling metric`}
                    keywords={[metric.key, "dashboard", "coupling"]}
                    onSelect={() => selectMetric("coupling", metric.key)}
                  >
                    <Gauge size={15} className="shrink-0 opacity-60" aria-hidden="true" />
                    <span>{metric.title}</span>
                    <span className="ml-auto text-xs text-base-content/40">Coupling</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {sections.map((section) => {
              const items = section.items.filter((item) => item.visible !== false);
              if (items.length === 0) return null;

              return (
                <CommandGroup key={section.label} heading={section.label}>
                  {items.map((item) => (
                    <CommandItem
                      key={item.href}
                      value={item.label}
                      keywords={[item.href, section.label]}
                      onSelect={() => navigate(item.href)}
                    >
                      <item.icon size={15} className="shrink-0 opacity-60" aria-hidden="true" />
                      <span>{item.label}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              );
            })}
            <CommandGroup heading="Actions">
              <CommandItem
                value="Copy current page link"
                keywords={["url", "share", "clipboard", "リンク", "コピー", "共有"]}
                onSelect={() => {
                  void copyPageLink();
                }}
              >
                <Link size={15} className="shrink-0 opacity-60" aria-hidden="true" />
                <span>Copy current page link</span>
              </CommandItem>
            </CommandGroup>
            {projects.length > 1 && (
              <CommandGroup heading="Switch project">
                {projects.map((project) => (
                  <CommandItem
                    key={project.project_id}
                    value={`project ${project.project_id}`}
                    keywords={[project.name, "switch", "プロジェクト", "切り替え"]}
                    disabled={project.project_id === projectId}
                    onSelect={() => {
                      switchProject(project.project_id);
                      setOpen(false);
                    }}
                  >
                    <FolderKanban size={15} className="shrink-0 opacity-60" aria-hidden="true" />
                    <span>{project.name}</span>
                    {project.project_id === projectId && (
                      <span className="ml-auto text-xs">Current</span>
                    )}
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            <CommandGroup heading="Change theme">
              {AVAILABLE_THEMES.map((name) => (
                <CommandItem
                  key={name}
                  value={`Use ${name} theme`}
                  keywords={["appearance", "color", "テーマ", "外観"]}
                  onSelect={() => {
                    setTheme(name);
                    setOpen(false);
                  }}
                >
                  <Palette size={15} className="shrink-0 opacity-60" aria-hidden="true" />
                  <span>Use {name} theme</span>
                  {theme === name && (
                    <Check size={15} className="ml-auto" aria-label="Current theme" />
                  )}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
          <div className="flex gap-4 border-t border-base-300 px-3 py-2 text-xs text-base-content/60">
            <span>
              <kbd>↑ ↓</kbd> Navigate
            </span>
            <span>
              <kbd>Enter</kbd> Run
            </span>
            <span>
              <kbd>Esc</kbd> Close
            </span>
          </div>
        </Command>
      </CommandDialog>
    </>
  );
}
