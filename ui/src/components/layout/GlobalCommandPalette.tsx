"use client";

import { Gauge, Search } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

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

export function GlobalCommandPalette() {
  const router = useRouter();
  const pathname = usePathname();
  const { user } = useAuth();
  const { canEdit } = useProject();
  const [open, setOpen] = useState(false);
  const isDashboard = pathname === "/dashboard";
  const { qubitMetrics, couplingMetrics } = useMetricsConfig(isDashboard);
  const sections = getNavigationSections({
    canEdit,
    isAdmin: user?.system_role === "admin",
  });

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
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

  const jumpToMetric = (metricId: string) => {
    setOpen(false);
    window.setTimeout(() => {
      document.getElementById(metricId)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 0);
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
        <span className="hidden sm:inline">Navigate</span>
        <kbd className="hidden rounded border border-base-300 bg-base-200 px-1.5 py-0.5 text-xs font-normal md:inline">
          ⌘K
        </kbd>
      </button>

      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Navigate"
        description="Search for a page or dashboard metric to open."
      >
        <Command loop label="QDash navigation">
          <CommandInput
            placeholder={isDashboard ? "Search pages and metrics..." : "Search pages..."}
          />
          <CommandList>
            <CommandEmpty>No matching results</CommandEmpty>
            {isDashboard && (qubitMetrics.length > 0 || couplingMetrics.length > 0) && (
              <CommandGroup heading="Dashboard metrics">
                {qubitMetrics.map((metric) => (
                  <CommandItem
                    key={`qubit-${metric.key}`}
                    value={`${metric.title} qubit metric`}
                    keywords={[metric.key, "dashboard", "qubit"]}
                    onSelect={() => jumpToMetric(`dashboard-qubit-metric-${metric.key}`)}
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
                    onSelect={() => jumpToMetric(`dashboard-coupling-metric-${metric.key}`)}
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
          </CommandList>
        </Command>
      </CommandDialog>
    </>
  );
}
