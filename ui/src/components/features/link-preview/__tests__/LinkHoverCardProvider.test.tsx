/* eslint-disable @next/next/no-html-link-for-pages -- the cards must cover plain anchors as well as Next.js links. */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Providers from "@/app/providers";
import { ChatLinkPreviewProvider } from "@/components/features/chat/ChatLinkPreview";
import { ChatMarkdown } from "@/components/features/chat/ChatMarkdown";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/Dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import {
  CARD_CLOSE_DELAY_MS,
  CARD_OPEN_DELAY_MS,
  LinkHoverCardProvider,
} from "../LinkHoverCardProvider";

const useGetTaskResult = vi.fn();
const useGetExecution = vi.fn();
const useGetForumPost = vi.fn();
vi.mock("@/client/task/task", () => ({
  useGetTaskResult: (...args: unknown[]) => useGetTaskResult(...args),
}));
vi.mock("@/client/execution/execution", () => ({
  useGetExecution: (...args: unknown[]) => useGetExecution(...args),
}));
vi.mock("@/client/forum/forum", () => ({
  useGetForumPost: (...args: unknown[]) => useGetForumPost(...args),
}));

// The root providers that need a session, a router or a project are passed through, so the
// test renders the real provider tree around the link hover cards.
const { passThrough } = vi.hoisted(() => ({
  passThrough: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("@/contexts/AuthContext", () => ({ AuthProvider: passThrough }));
vi.mock("@/contexts/AxiosContext", () => ({ AxiosProvider: passThrough }));
vi.mock("@/contexts/ProjectContext", () => ({ ProjectProvider: passThrough }));
vi.mock("nuqs/adapters/next/app", () => ({ NuqsAdapter: passThrough }));

const TASK_RESULT = {
  task_id: "t1",
  task_name: "CheckRabi",
  qid: "0",
  chip_id: "64Qv3",
  status: "completed",
  execution_id: "20261006-012",
  figure_path: [],
  json_figure_path: [],
  raw_data_path: [],
  input_parameters: {},
  output_parameters: { rabi_frequency: { value: 12.6649, unit: "MHz" } },
};

let fetchSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.useFakeTimers();
  fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in tests"));
  useGetTaskResult.mockReturnValue({ data: { data: TASK_RESULT } });
  useGetExecution.mockReturnValue({
    data: { data: { name: "pipeline-x", status: "running", chip_id: "64Qv3", task: [] } },
  });
  useGetForumPost.mockReturnValue({ data: undefined, isError: false });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  fetchSpy.mockRestore();
  useGetTaskResult.mockReset();
  useGetExecution.mockReset();
  useGetForumPost.mockReset();
});

const link = (name: string) => screen.getByRole("link", { name });
const card = () => screen.queryByRole("tooltip");
const cards = () => screen.queryAllByRole("tooltip");

function hover(element: Element) {
  fireEvent.pointerOver(element, { pointerType: "mouse" });
}

function unhover(element: Element, to: Element = document.body) {
  fireEvent.pointerOut(element, { pointerType: "mouse", relatedTarget: to });
}

function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

function hoverOpen(element: Element) {
  hover(element);
  advance(CARD_OPEN_DELAY_MS);
}

describe("link hover cards", () => {
  it("are kept off page navigation links by the root providers", () => {
    render(
      <Providers>
        <nav aria-label="Primary navigation">
          <Link href="/">Home</Link>
        </nav>
        <Link href="/chip/64Qv3?tab=qubits">Chip 64Qv3</Link>
        <Link href="/workflow/my-flow">my-flow</Link>
        <Link href="/task-results/t1">Latest Rabi</Link>
      </Providers>,
    );

    for (const name of ["Home", "Chip 64Qv3", "my-flow", "Latest Rabi"]) {
      act(() => link(name).focus());
      hoverOpen(link(name));
      expect(card()).toBeNull();
      expect(link(name)).not.toHaveAttribute("aria-describedby");
      unhover(link(name));
    }
    expect(useGetTaskResult).not.toHaveBeenCalled();
  });

  it("describe a page link and load its record when every link is in scope", () => {
    render(
      <LinkHoverCardProvider>
        <nav>
          <Link href="/chip/64Qv3?tab=qubits">Chip 64Qv3</Link>
        </nav>
        <Link href="/task-results/t1">Latest Rabi</Link>
      </LinkHoverCardProvider>,
    );
    expect(useGetTaskResult).not.toHaveBeenCalled();

    hover(link("Chip 64Qv3"));
    advance(CARD_OPEN_DELAY_MS - 1);
    expect(card()).toBeNull();
    advance(1);
    expect(card()).toHaveTextContent("QDash page");
    expect(card()).toHaveTextContent("Chip");
    expect(card()).toHaveTextContent("/chip/64Qv3?tab=qubits");
    // A same-tab app link does not claim to open a new tab.
    expect(card()).not.toHaveTextContent("new tab");
    expect(link("Chip 64Qv3")).toHaveAttribute("aria-describedby", card()!.id);

    unhover(link("Chip 64Qv3"), link("Latest Rabi"));
    hover(link("Latest Rabi"));
    expect(card()).toHaveTextContent("Task result");
    expect(card()).toHaveTextContent("CheckRabi");
    expect(card()).toHaveTextContent("12.665 MHz");
    expect(useGetTaskResult).toHaveBeenCalledWith("t1", expect.anything());
    expect(cards()).toHaveLength(1);
  });

  it("leaves link clicks to the browser and closes the card", () => {
    const onClick = vi.fn((event: React.MouseEvent) => event.defaultPrevented);
    render(
      <LinkHoverCardProvider>
        <a href="/dashboard" onClick={onClick}>
          Overview
        </a>
      </LinkHoverCardProvider>,
    );
    hoverOpen(link("Overview"));
    expect(card()).toHaveTextContent("Overview");
    expect(fireEvent.click(link("Overview"))).toBe(true);
    expect(onClick).toHaveReturnedWith(false);
    expect(card()).toBeNull();
  });

  it("does not load a record for a record-shaped path on another host", () => {
    render(
      <LinkHoverCardProvider>
        <a href="https://elsewhere.example/task-results/t1">Elsewhere</a>
        <a href="//elsewhere.example/forum/p1">Protocol-relative</a>
      </LinkHoverCardProvider>,
    );
    hoverOpen(link("Elsewhere"));
    expect(card()).toHaveTextContent("External link");
    expect(card()).toHaveTextContent("elsewhere.example");
    expect(card()).toHaveTextContent("https://elsewhere.example/task-results/t1");

    unhover(link("Elsewhere"), link("Protocol-relative"));
    hover(link("Protocol-relative"));
    expect(card()).toHaveTextContent("External link");

    expect(useGetTaskResult).not.toHaveBeenCalled();
    expect(useGetForumPost).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("labels fragments, downloads, email and phone links without fetching or navigating", () => {
    render(
      <LinkHoverCardProvider>
        <h2 id="calibration-notes">Calibration notes</h2>
        <a href="#calibration-notes">Jump to notes</a>
        <a href="#missing">Missing section</a>
        <a href="/api/executions/figure?path=exec%2F1%2Fa.png" download="rabi.png">
          Save figure
        </a>
        <a href="mailto:ops@example.com">Email ops</a>
        <a href="tel:+81-3-0000-0000">Call ops</a>
        <a href="/api/flows/export">Export flows</a>
      </LinkHoverCardProvider>,
    );
    hoverOpen(link("Jump to notes"));
    expect(card()).toHaveTextContent("Section on this page");
    expect(card()).toHaveTextContent("Calibration notes");
    expect(card()).toHaveTextContent("#calibration-notes");

    const sequence: Array<[string, string[]]> = [
      ["Missing section", ["Section on this page", "#missing"]],
      ["Save figure", ["Download", "rabi.png", "Saves a file"]],
      ["Email ops", ["Email", "ops@example.com"]],
      ["Call ops", ["Phone", "+81-3-0000-0000"]],
      ["Export flows", ["QDash API", "/api/flows/export"]],
    ];
    let previous = link("Jump to notes");
    for (const [name, texts] of sequence) {
      unhover(previous, link(name));
      hover(link(name));
      for (const text of texts) expect(card()).toHaveTextContent(text);
      previous = link(name);
    }
    // The download names the file instead of loading the figure.
    expect(screen.queryByRole("img")).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("does not invent cards for placeholders, script links or button-only navigation", () => {
    render(
      <LinkHoverCardProvider>
        <a href="#">Placeholder</a>
        <a href="javascript:void(0)">Script</a>
        <a>No destination</a>
        <button type="button">Go to dashboard</button>
        <a href="/dashboard" aria-disabled="true">
          Disabled
        </a>
        <div data-link-preview="off">
          <a href="/dashboard">Opted out</a>
        </div>
      </LinkHoverCardProvider>,
    );
    for (const name of ["Placeholder", "Script", "Disabled", "Opted out"]) {
      hoverOpen(link(name));
      expect(card()).toBeNull();
    }
    hoverOpen(screen.getByText("No destination"));
    hoverOpen(screen.getByRole("button", { name: "Go to dashboard" }));
    act(() => screen.getByRole("button", { name: "Go to dashboard" }).focus());
    expect(card()).toBeNull();
  });

  it("reaches links in a dialog portal and closes only the card on Escape or a press in it", () => {
    function DialogWithLink() {
      const [open, setOpen] = useState(true);
      return (
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogContent aria-describedby={undefined}>
            <DialogTitle>Run details</DialogTitle>
            <a href="/execution/64Qv3/20261006-012">Open run</a>
          </DialogContent>
        </Dialog>
      );
    }
    render(
      <LinkHoverCardProvider>
        <DialogWithLink />
      </LinkHoverCardProvider>,
    );
    const dialog = screen.getByRole("dialog");
    // Radix registers its outside-press listeners on the next tick.
    advance(0);
    hoverOpen(link("Open run"));
    const shown = screen.getByRole("tooltip");
    expect(shown).toHaveTextContent("Execution");
    expect(shown).toHaveTextContent("pipeline-x");
    expect(useGetExecution).toHaveBeenCalledWith("20261006-012", expect.anything());

    // A press inside the card is not a press outside the dialog.
    fireEvent.pointerDown(shown, { pointerType: "mouse" });
    fireEvent.click(shown);
    advance(0);
    expect(screen.getByRole("dialog")).toBe(dialog);

    fireEvent.keyDown(link("Open run"), { key: "Escape" });
    expect(card()).toBeNull();
    expect(screen.getByRole("dialog")).toBe(dialog);
  });

  it("reaches links in a dropdown menu by keyboard and by pointer", () => {
    render(
      <LinkHoverCardProvider>
        <DropdownMenu defaultOpen>
          <DropdownMenuTrigger>Shortcuts</DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem asChild>
              <a href="/settings">Settings</a>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/forum">Forum</Link>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </LinkHoverCardProvider>,
    );
    const settings = screen.getByRole("menuitem", { name: "Settings" });
    const forum = screen.getByRole("menuitem", { name: "Forum" });

    // Keyboard focus opens the card at once.
    fireEvent.keyDown(settings, { key: "ArrowDown" });
    act(() => settings.focus());
    expect(card()).toHaveTextContent("Settings");

    act(() => forum.focus());
    expect(card()).toHaveTextContent("Forum");
    expect(cards()).toHaveLength(1);

    fireEvent.keyDown(forum, { key: "Escape" });
    expect(card()).toBeNull();
  });

  it("does not open on focus that a pointer press or hover caused", () => {
    render(
      <LinkHoverCardProvider>
        <a href="/dashboard">Overview</a>
        <a href="/metrics">Metrics</a>
      </LinkHoverCardProvider>,
    );
    fireEvent.pointerDown(link("Overview"), { pointerType: "mouse" });
    act(() => link("Overview").focus());
    expect(card()).toBeNull();

    // Back on the keyboard, focus opens at once again.
    fireEvent.keyDown(link("Overview"), { key: "Tab" });
    act(() => link("Metrics").focus());
    expect(card()).toHaveTextContent("Metrics");
    act(() => link("Metrics").blur());
    advance(CARD_CLOSE_DELAY_MS);
    expect(card()).toBeNull();

    // A menu-style hover that moves focus waits for the hover delay.
    hover(link("Overview"));
    act(() => link("Overview").focus());
    expect(card()).toBeNull();
    advance(CARD_OPEN_DELAY_MS);
    expect(card()).toHaveTextContent("Overview");
    unhover(link("Overview"));
    advance(CARD_CLOSE_DELAY_MS);
    expect(card()).toBeNull();
  });

  it("ignores touch, and closes for a link that leaves the page", async () => {
    function Removable() {
      const [shown, setShown] = useState(true);
      return (
        <>
          {shown && <a href="/metrics">Metrics</a>}
          <button type="button" onClick={() => setShown(false)}>
            Remove
          </button>
        </>
      );
    }
    render(
      <LinkHoverCardProvider>
        <Removable />
      </LinkHoverCardProvider>,
    );
    fireEvent.pointerOver(link("Metrics"), { pointerType: "touch" });
    advance(CARD_OPEN_DELAY_MS * 2);
    expect(card()).toBeNull();

    hoverOpen(link("Metrics"));
    expect(card()).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    await act(async () => {});
    expect(card()).toBeNull();
  });

  it("drops a pending open when the link is detached or the provider unmounts", () => {
    const { unmount } = render(<LinkHoverCardProvider>{null}</LinkHoverCardProvider>);
    // A link rendered outside React, as Markdown renderers and diagrams do.
    const anchor = document.createElement("a");
    anchor.href = "/metrics";
    anchor.textContent = "Metrics";
    document.body.append(anchor);
    hover(anchor);
    anchor.remove();
    advance(CARD_OPEN_DELAY_MS);
    expect(card()).toBeNull();

    document.body.append(anchor);
    hover(anchor);
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
    anchor.remove();
  });

  it("shows one card for chat links under the root provider, with the chat's click preview", () => {
    render(
      <Providers>
        <ChatLinkPreviewProvider>
          <ChatMarkdown>
            {"See [the Rabi result](http://localhost:28005/task-results/t1) and [docs](/chip)."}
          </ChatMarkdown>
        </ChatLinkPreviewProvider>
      </Providers>,
    );
    // Chat answers keep their record leniency for a misconfigured host.
    hoverOpen(link("the Rabi result"));
    expect(cards()).toHaveLength(1);
    expect(card()).toHaveTextContent("CheckRabi");

    unhover(link("the Rabi result"), link("docs"));
    hover(link("docs"));
    expect(cards()).toHaveLength(1);
    expect(card()).toHaveTextContent("Opens in a new tab");

    expect(fireEvent.click(link("the Rabi result"))).toBe(false);
    expect(screen.getByTestId("chat-link-preview")).toHaveTextContent("CheckRabi");
    expect(card()).toBeNull();
  });
});
