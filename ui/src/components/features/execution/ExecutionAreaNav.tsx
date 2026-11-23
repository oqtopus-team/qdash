"use client";

import Link from "next/link";

import { EXECUTION_VIEWS } from "@/components/layout/navigation";
import {
  type ExecutionCrumb,
  calibrationSessionListHref,
  executionListHref,
} from "@/lib/executionArea";

export type ExecutionView = "executions" | "sessions";

const VIEW_KEYS: Record<(typeof EXECUTION_VIEWS)[number]["href"], ExecutionView> = {
  "/execution": "executions",
  "/calibration-sessions": "sessions",
};

/**
 * Switches between the two lists of the Execution area: every execution, and the calibration
 * sessions that group runs by objective. They list different things, so each keeps its own
 * filters; the switch carries only the chip and the project.
 */
export function ExecutionViewSwitch({
  current,
  chipId,
  projectId,
  className = "",
}: {
  current: ExecutionView;
  chipId?: string | null;
  projectId?: string | null;
  className?: string;
}) {
  return (
    <nav aria-label="Execution views" className={className}>
      <div className="tabs tabs-border w-full sm:w-fit">
        {EXECUTION_VIEWS.map((view) => {
          const key = VIEW_KEYS[view.href];
          const active = key === current;
          const href =
            key === "executions"
              ? executionListHref({ chipId, projectId })
              : calibrationSessionListHref({ chip: chipId }, projectId);
          return (
            <Link
              key={view.href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`tab ${active ? "tab-active" : ""}`}
            >
              {view.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

/** Labels up to this length are never cut. */
const SHORT_CRUMB = 24;

/**
 * Where a page sits in the Execution area, from the area down to the page's parent; the page's own
 * heading names the page. A long label is cut only visually: the text stays whole for assistive
 * technology, and `title` shows it on hover.
 */
export function ExecutionBreadcrumbs({ crumbs }: { crumbs: ExecutionCrumb[] }) {
  if (crumbs.length === 0) return null;
  return (
    <nav aria-label="Breadcrumb" className="breadcrumbs max-w-full py-0 text-sm">
      <ul>
        {crumbs.map((crumb, index) => (
          // Only a long label, such as an objective, gives up width; short ones stay whole.
          <li
            key={`${index}:${crumb.href ?? crumb.label}`}
            className={crumb.label.length > SHORT_CRUMB ? "min-w-0" : "shrink-0"}
          >
            {crumb.href ? (
              <Link
                href={crumb.href}
                title={crumb.title}
                className="inline-block max-w-[16rem] truncate align-bottom sm:max-w-[24rem]"
              >
                {crumb.label}
              </Link>
            ) : (
              <span
                title={crumb.title}
                className="inline-block max-w-[16rem] truncate align-bottom text-base-content/60 sm:max-w-[24rem]"
              >
                {crumb.label}
              </span>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}
