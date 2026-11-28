import { describe, expect, it } from "vitest";

import {
  BUG_REPORT_URL,
  buildChatErrorReport,
  classifyChatError,
  reportPageCategory,
} from "@/lib/chatErrorReport";

describe("classifyChatError", () => {
  it("offers a report only for faults, never for a refused or correctable request", () => {
    expect(classifyChatError("HTTP 500: Internal Server Error")).toEqual({
      kind: "server_error",
      status: 500,
      reportable: true,
    });
    expect(classifyChatError("The connection closed before the answer was complete").kind).toBe(
      "interrupted",
    );
    for (const message of [
      "HTTP 422: policy.task_quality_gates: CheckT1 must be in allowed_tasks",
      "HTTP 401: Not authenticated",
      "HTTP 403: Forbidden",
      "HTTP 409: Agent session is not active: cancelled",
      "HTTP 429: Too many requests",
    ]) {
      expect(classifyChatError(message).reportable, message).toBe(false);
    }
  });
});

describe("buildChatErrorReport", () => {
  const secret =
    "HTTP 502: upstream http://10.0.0.5:8000/v1 rejected Bearer xoxb-123 for prompt 'calibrate Q6' QDASH_API_TOKEN=abc";

  it("keeps only allowlisted facts, never the error text, the query, or credentials", () => {
    const draft = buildChatErrorReport({
      message: secret,
      path: "/chat/abc?token=qdash-secret#frag",
      chatId: "chat-42",
      at: new Date("2026-11-22T00:00:00Z"),
    });
    expect(draft).toContain("HTTP status: 502");
    expect(draft).toContain("Failure kind: server_error");
    expect(draft).toContain("Page: /chat/[redacted]");
    expect(draft).toContain("Draft generated at (UTC): 2026-11-22T00:00:00.000Z");
    expect(draft).toContain("Chat id (delete this line if you prefer): chat-42");
    for (const leaked of [
      "10.0.0.5",
      "xoxb",
      "Bearer",
      "calibrate Q6",
      "QDASH_API_TOKEN",
      "token=",
      "frag",
    ]) {
      expect(draft).not.toContain(leaked);
    }
    // Facts and the user's own hypotheses stay apart; QDash claims no diagnosis.
    expect(draft).toMatch(/### Confirmed facts \(recorded by QDash\)[\s\S]*### Hypotheses/);
    expect(draft).toContain("QDash does not diagnose the cause");
  });

  it("links the repository bug form without putting any text in the URL", () => {
    expect(BUG_REPORT_URL).toBe(
      "https://github.com/oqtopus-team/qdash/issues/new?template=BUG_REPORT.yaml",
    );
    expect(reportPageCategory("/a?b=c")).toBe("[not included]");
    expect(reportPageCategory("")).toBe("[not included]");
  });
});

it("does not copy private or encoded path segments into a report", () => {
  for (const path of [
    "/workflow/private-token?x=y",
    "/chat/%73ecret",
    "/private-token",
    "https://private-token/chat",
  ]) {
    const draft = buildChatErrorReport({ message: "unknown", path });
    expect(draft).not.toContain("private-token");
    expect(draft).not.toContain("%73ecret");
    expect(draft).toContain("Failure kind: unclassified_error");
    expect(draft).toContain("its source is not established");
  }
});
