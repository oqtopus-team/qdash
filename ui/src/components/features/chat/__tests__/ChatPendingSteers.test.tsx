import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatNotice, ChatPendingSteers } from "../ChatPendingSteers";

afterEach(cleanup);

describe("ChatPendingSteers", () => {
  it("shows a queued steer without actions and an undelivered one with resend and dismiss", () => {
    const onResend = vi.fn();
    const onDismiss = vi.fn();
    const { rerender } = render(
      <ChatPendingSteers
        steers={[
          { requestId: "a", text: "Use Q5", status: "queued" },
          { requestId: "b", text: "Plot it", status: "rejected", reason: "idle" },
        ]}
        isStreaming={false}
        onResend={onResend}
        onDismiss={onDismiss}
      />,
    );
    expect(screen.getByText("Read after the current step")).toBeInTheDocument();
    expect(screen.getByText("Not sent: the answer had already finished")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Dismiss" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Send as new message" }));
    expect(onResend).toHaveBeenCalledWith("b");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalledWith("b");

    rerender(
      <ChatPendingSteers
        steers={[{ requestId: "b", text: "Plot it", status: "withdrawn", reason: "aborted" }]}
        isStreaming
        onResend={onResend}
        onDismiss={onDismiss}
      />,
    );
    expect(screen.getByRole("button", { name: "Send again" })).toBeInTheDocument();
  });

  it("offers to check an unconfirmed steer again, never to send it again", () => {
    const onResend = vi.fn();
    const onCheck = vi.fn();
    const { rerender } = render(
      <ChatPendingSteers
        steers={[{ requestId: "a", text: "Use Q5", status: "unconfirmed" }]}
        isStreaming={false}
        onResend={onResend}
        onCheck={onCheck}
        onDismiss={vi.fn()}
      />,
    );
    expect(screen.getByText("Not confirmed whether the answer read it")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send as new message" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(onCheck).toHaveBeenCalledWith("a");
    rerender(
      <ChatPendingSteers
        steers={[{ requestId: "a", text: "Use Q5", status: "unconfirmed", checking: true }]}
        isStreaming={false}
        onResend={onResend}
        onCheck={onCheck}
        onDismiss={vi.fn()}
      />,
    );
    expect(screen.getByText("Checking whether the answer read it…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check again" })).toBeNull();
  });

  it("renders nothing without steers, and a dismissable notice", () => {
    const { container } = render(
      <ChatPendingSteers steers={[]} isStreaming={false} onResend={vi.fn()} onDismiss={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
    const onDismiss = vi.fn();
    render(<ChatNotice text="Nothing to continue" onDismiss={onDismiss} />);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalled();
  });
});
