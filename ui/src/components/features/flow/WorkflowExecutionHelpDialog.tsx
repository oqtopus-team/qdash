"use client";

import { useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { ExternalLink, Pause, Play, X } from "lucide-react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";

const DOCS_BASE_URL = "https://oqtopus-team.github.io/qdash/";
// Generated with the docs GIFs by docs/demos/*.py; see docs/demos/README.md.
const MEDIA_BASE_PATH = "/images/execution-help/";

type HelpTopic = "one-qubit" | "two-qubit";

interface HelpMedia {
  name: string;
  width: number;
  height: number;
  alt: string;
}

interface DocsLink {
  label: string;
  path: string;
}

const TOPICS: ReadonlyArray<{ id: HelpTopic; label: string }> = [
  { id: "one-qubit", label: "1Q execution modes" },
  { id: "two-qubit", label: "2Q CR groups" },
];

const ONE_QUBIT_MEDIA: HelpMedia = {
  name: "one-qubit-execution-modes",
  width: 860,
  height: 792,
  alt:
    "Three timelines for qubits 0 and 1 on MUX 0 and qubits 8 and 9 on MUX 2, each running " +
    "CheckRabi, CreateHPIPulse, then CheckT1. In sequential, the qubits run one at a time. In " +
    "parallel_by_mux, each MUX starts its next qubit as soon as its current qubit finishes, so " +
    "qubit 1 starts while qubit 8 is still on CheckT1. In parallel_by_round, qubit 1 waits until " +
    "qubit 8 finishes its whole task list, then qubits 1 and 9 start together as round 2.",
};

const TWO_QUBIT_MEDIA: HelpMedia = {
  name: "two-qubit-cr-schedule",
  width: 860,
  height: 550,
  alt:
    "Execution timeline of four CR groups with max_parallel_ops 4 on four worker lanes. G1 runs " +
    "pairs 0 to 1, 4 to 5, 12 to 13 and 16 to 17 at once; each pair moves through " +
    "CheckCrossResonance, CreateZX90 and CheckZX90 at its own rate, and the pairs that finish " +
    "first wait for 0 to 1, the slowest pair. G2 then runs 3 to 1 and 8 to 9, G3 runs 3 to 2, " +
    "and G4 runs the inter-MUX pair 7 to 10.",
};

const ONE_QUBIT_MODES: ReadonlyArray<{ mode: string; text: string }> = [
  {
    mode: "parallel_by_mux",
    text:
      "MUXes run in parallel and the qubits of one MUX run one after another. Each MUX starts " +
      "its next qubit as soon as the current one finishes. The default in templates such as " +
      "Simple Calibration.",
  },
  {
    mode: "parallel_by_round",
    text:
      "Qubits from different MUXes run in rounds. The next round starts after every qubit of " +
      "the current round finishes its whole task list.",
  },
  { mode: "sequential", text: "One MUX and one qubit at a time." },
];

function Code({ children }: { children: ReactNode }) {
  return <code className="font-mono">{children}</code>;
}

function DocsLinks({ links }: { links: ReadonlyArray<DocsLink> }) {
  return (
    <ul className="flex flex-col gap-1">
      {links.map((link) => (
        <li key={link.path}>
          <a
            href={`${DOCS_BASE_URL}${link.path}`}
            target="_blank"
            rel="noopener noreferrer"
            className="link link-hover inline-flex items-center gap-1 text-sm"
          >
            {link.label}
            <ExternalLink size={14} aria-hidden="true" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

/**
 * Shows a still poster until the user presses Play, so the dialog never starts motion on its
 * own and the GIF is fetched only on request.
 */
function HelpAnimation({ media, caption }: { media: HelpMedia; caption: string }) {
  const [playing, setPlaying] = useState(false);
  const gif = `${MEDIA_BASE_PATH}${media.name}.gif`;
  const src = playing ? gif : `${MEDIA_BASE_PATH}${media.name}-poster.png`;

  return (
    <figure className="flex flex-col gap-2">
      <div className="overflow-hidden rounded-lg border border-base-content/10 bg-white">
        {/* eslint-disable-next-line @next/next/no-img-element -- the GIF must stay animated */}
        <img
          src={src}
          alt={media.alt}
          width={media.width}
          height={media.height}
          className="h-auto w-full"
        />
      </div>
      <figcaption className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-base-content/60">{caption}</span>
        <span className="flex items-center gap-2">
          <a
            href={gif}
            target="_blank"
            rel="noopener noreferrer"
            className="link link-hover text-xs text-base-content/60"
          >
            Open full size
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => setPlaying((value) => !value)}
          >
            {playing ? (
              <Pause size={16} aria-hidden="true" />
            ) : (
              <Play size={16} aria-hidden="true" />
            )}
            {playing ? "Pause animation" : "Play animation"}
          </button>
        </span>
      </figcaption>
    </figure>
  );
}

function OneQubitHelp() {
  return (
    <div className="flex flex-col gap-4">
      <p>
        <Code>execution_mode</Code> sets how the selected qubits wait for each other. Each qubit
        runs the step&apos;s whole task list before it counts as finished. The three modes below do
        not wait for the same task to finish across all qubits before starting the next task.
      </p>
      <dl className="flex flex-col gap-2">
        {ONE_QUBIT_MODES.map(({ mode, text }) => (
          <div key={mode}>
            <dt>
              <Code>{mode}</Code>
            </dt>
            <dd className="text-base-content/70">{text}</dd>
          </div>
        ))}
      </dl>
      <HelpAnimation
        media={ONE_QUBIT_MEDIA}
        caption="Illustrative task list and durations, not measurements"
      />
      <p className="text-base-content/70">
        A round waits for every qubit&apos;s whole task list, not for each task, and does not
        synchronize pulses. QDash chooses the actual MUX order and rounds from the chip wiring.
      </p>
      <DocsLinks
        links={[
          {
            label: "Choose an execution mode",
            path: "user-guide/creating-workflows.html#choose-an-execution-mode",
          },
        ]}
      />
    </div>
  );
}

function TwoQubitHelp() {
  return (
    <div className="flex flex-col gap-4">
      <p>
        QDash splits the coupling pairs into groups and runs the groups one after another. Pairs
        that share a qubit, use the same MUX, or use MUXes that share a readout or control module go
        to different groups. Groups of pairs inside one MUX run before pairs that span two MUXes.
      </p>
      <p>
        Inside a group, each pair runs the task list in its own worker and moves to its next task
        without waiting for the other pairs. The next group starts when every pair of the current
        group is done.
      </p>
      <HelpAnimation
        media={TWO_QUBIT_MEDIA}
        caption="Example with max_parallel_ops = 4; illustrative durations"
      />
      <p className="text-base-content/70">
        <Code>max_parallel_ops</Code> caps the pairs in one group. Raising it never puts conflicting
        pairs together, and it does not guarantee that every pair of a group runs at the same
        moment. With a cap of 2, the four pairs of G1 above would run as two groups.
      </p>
      <DocsLinks
        links={[
          {
            label: "Schedule two-qubit calibration",
            path: "user-guide/creating-workflows.html#schedule-two-qubit-calibration",
          },
          {
            label: "CR gate scheduler: conflict graph and groups",
            path: "developer-guide/architecture/cr-scheduler.html#conflict-graph-and-groups",
          },
        ]}
      />
    </div>
  );
}

interface WorkflowExecutionHelpDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Read-only reference for how a workflow runs its qubits and coupling pairs. It holds no
 * editor state, so opening it never changes, saves, or runs the flow.
 */
export function WorkflowExecutionHelpDialog({
  open,
  onOpenChange,
}: WorkflowExecutionHelpDialogProps) {
  const [topic, setTopic] = useState<HelpTopic>("one-qubit");
  const tabRefs = useRef<Partial<Record<HelpTopic, HTMLButtonElement | null>>>({});
  // The editor opens the dialog from plain buttons, not a Radix trigger, so remember the
  // control that had focus and return to it on close.
  const returnFocusRef = useRef<HTMLElement | null>(null);

  useLayoutEffect(() => {
    if (open && document.activeElement instanceof HTMLElement) {
      returnFocusRef.current = document.activeElement;
    }
  }, [open]);

  const selectTopic = (next: HelpTopic) => {
    setTopic(next);
    tabRefs.current[next]?.focus();
  };

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const index = TOPICS.findIndex((item) => item.id === topic);
    const last = TOPICS.length - 1;
    const target: Record<string, number> = {
      ArrowRight: index === last ? 0 : index + 1,
      ArrowLeft: index === 0 ? last : index - 1,
      Home: 0,
      End: last,
    };
    if (!(event.key in target)) return;
    event.preventDefault();
    selectTopic(TOPICS[target[event.key]].id);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="flex max-w-3xl flex-col gap-4 p-4 sm:p-6"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          tabRefs.current[topic]?.focus();
        }}
        onCloseAutoFocus={(event) => {
          const target = returnFocusRef.current;
          returnFocusRef.current = null;
          if (target?.isConnected) {
            event.preventDefault();
            target.focus();
          }
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <DialogTitle>Execution help</DialogTitle>
            <DialogDescription className="text-xs text-base-content/60">
              How a workflow runs its qubits and coupling pairs. Your editor changes stay as they
              are.
            </DialogDescription>
          </div>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="btn btn-ghost btn-sm btn-square"
            aria-label="Close execution help"
          >
            <X size={16} />
          </button>
        </div>

        <div role="tablist" aria-label="Help topic" className="tabs tabs-border">
          {TOPICS.map((item) => (
            <button
              key={item.id}
              ref={(element) => {
                tabRefs.current[item.id] = element;
              }}
              type="button"
              role="tab"
              id={`execution-help-tab-${item.id}`}
              aria-selected={topic === item.id}
              aria-controls={`execution-help-panel-${item.id}`}
              tabIndex={topic === item.id ? 0 : -1}
              className={`tab ${topic === item.id ? "tab-active" : ""}`}
              onClick={() => setTopic(item.id)}
              onKeyDown={handleTabKeyDown}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div
          role="tabpanel"
          id={`execution-help-panel-${topic}`}
          aria-labelledby={`execution-help-tab-${topic}`}
        >
          {topic === "one-qubit" ? <OneQubitHelp /> : <TwoQubitHelp />}
        </div>
      </DialogContent>
    </Dialog>
  );
}
