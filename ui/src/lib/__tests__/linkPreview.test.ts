import { describe, expect, it } from "vitest";

import { describeLink, pageSection } from "../linkPreview";

const location = { origin: "https://qdash.example", pathname: "/chip/64Qv3", search: "?tab=t1" };

const describe_ = (href: string, extra: Partial<Parameters<typeof describeLink>[0]> = {}) =>
  describeLink({ href, location, ...extra });

describe("describeLink", () => {
  it("names QDash records on this origin only, unless the link is in a chat answer", () => {
    expect(describe_("/task-results/t1")).toMatchObject({ kind: "task-result", taskId: "t1" });
    expect(describe_("https://qdash.example/execution/64Qv3/x")).toMatchObject({
      kind: "execution",
      chipId: "64Qv3",
      executionId: "x",
    });
    expect(describe_("http://api:5715/task-results/t1")).toMatchObject({
      kind: "external",
      host: "api:5715",
    });
    expect(describe_("http://api:5715/task-results/t1", { scope: "chat" })).toMatchObject({
      kind: "task-result",
      taskId: "t1",
    });
  });

  it("names app pages by their sidebar section", () => {
    expect(describe_("/chip/64Qv3?tab=qubits")).toMatchObject({
      kind: "page",
      path: "/chip/64Qv3?tab=qubits",
      section: "Chip",
    });
    expect(describe_("/executions")).toMatchObject({ kind: "page", section: "Execution" });
    expect(describe_("/forum/new")).toMatchObject({ kind: "page", section: "Forum" });
    expect(describe_("/")).toMatchObject({ kind: "page", path: "/", section: null });
    expect(describe_("/api/flows/export")).toMatchObject({ kind: "api" });
    expect(pageSection("/task-results")).toBe("Task Results");
  });

  it("treats a hash on the current page as a fragment, and on another page as that page", () => {
    expect(describe_("#notes", { resolveFragment: () => "Notes" })).toMatchObject({
      kind: "fragment",
      id: "notes",
      label: "Notes",
    });
    expect(describe_("/chip/64Qv3?tab=t1#q0")).toMatchObject({ kind: "fragment", id: "q0" });
    expect(describe_("/metrics#q0")).toMatchObject({ kind: "page", path: "/metrics#q0" });
  });

  it("labels downloads and non-web schemes without treating them as pages", () => {
    expect(describe_("/api/executions/figure?path=a.png", { download: "" })).toMatchObject({
      kind: "download",
      filename: "figure",
    });
    expect(describe_("blob:https://qdash.example/1", { download: "run.zip" })).toMatchObject({
      kind: "download",
      filename: "run.zip",
    });
    expect(describe_("mailto:ops@example.com?subject=hi")).toMatchObject({
      kind: "email",
      address: "ops@example.com",
    });
    expect(describe_("tel:+1-555")).toMatchObject({ kind: "phone", number: "+1-555" });
    expect(describe_("vscode://file/x")).toMatchObject({ kind: "other", scheme: "vscode" });
  });

  it("reports whether the link opens a new tab", () => {
    expect(describe_("/metrics", { target: "_blank" })?.newTab).toBe(true);
    expect(describe_("/metrics", { target: "_self" })?.newTab).toBe(false);
    expect(describe_("/metrics")?.newTab).toBe(false);
  });

  it("has nothing to describe for placeholders and script links", () => {
    expect(describe_("")).toBeNull();
    expect(describe_("#")).toBeNull();
    expect(describe_(" javascript:alert(1)")).toBeNull();
    expect(describe_("http://[bad")).toBeNull();
  });
});
