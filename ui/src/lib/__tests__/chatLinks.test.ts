import { describe, expect, it } from "vitest";

import { chatLinkPagePath, classifyChatLink } from "../chatLinks";

const ORIGIN = "https://qdash.example";

describe("classifyChatLink", () => {
  it("recognises QDash records by route, absolute or relative, current or legacy", () => {
    expect(classifyChatLink(`${ORIGIN}/task-results/abc%2F1`, ORIGIN)).toEqual({
      kind: "task-result",
      taskId: "abc/1",
      href: `${ORIGIN}/task-results/abc%2F1`,
    });
    expect(classifyChatLink("/executions/20261006-012", ORIGIN)).toMatchObject({
      kind: "execution",
      executionId: "20261006-012",
      chipId: null,
    });
    expect(classifyChatLink("/execution/64Qv3/20261006-012", ORIGIN)).toMatchObject({
      kind: "execution",
      executionId: "20261006-012",
      chipId: "64Qv3",
    });
    expect(classifyChatLink("/forum/p1", ORIGIN)).toMatchObject({
      kind: "forum-post",
      postId: "p1",
    });
    expect(classifyChatLink("/forum/posts/p1", ORIGIN)).toMatchObject({
      kind: "forum-post",
      postId: "p1",
    });
    expect(classifyChatLink("/api/executions/figure?path=exec%2F1%2Fa.png", ORIGIN)).toMatchObject({
      kind: "figure",
      path: "exec/1/a.png",
    });
  });

  it("previews QDash records even when the answer names another host", () => {
    expect(
      classifyChatLink("http://localhost:28005/execution/144Qv2/20261006-018", ORIGIN),
    ).toMatchObject({
      kind: "execution",
      chipId: "144Qv2",
      executionId: "20261006-018",
    });
    expect(classifyChatLink("http://api:5715/task-results/t1", ORIGIN).kind).toBe("task-result");
    expect(classifyChatLink("http://localhost:28005/dashboard", ORIGIN).kind).toBe("external");
  });

  it("leaves other links alone", () => {
    expect(classifyChatLink("/forum/new", ORIGIN).kind).toBe("internal");
    expect(classifyChatLink("/dashboard", ORIGIN).kind).toBe("internal");
    expect(classifyChatLink("/task-results", ORIGIN).kind).toBe("internal");
    expect(classifyChatLink("https://arxiv.org/abs/1", ORIGIN).kind).toBe("external");
    expect(classifyChatLink("not a url at all", "::bad").kind).toBe("external");
  });
});

describe("chatLinkPagePath", () => {
  it("maps records to their real pages", () => {
    expect(chatLinkPagePath(classifyChatLink("/forum/posts/p1", ORIGIN))).toBe("/forum/p1");
    expect(chatLinkPagePath(classifyChatLink("/execution/64Qv3/x", ORIGIN))).toBe(
      "/execution/64Qv3/x",
    );
    expect(chatLinkPagePath(classifyChatLink("/executions/x", ORIGIN))).toBe("/executions/x");
    expect(chatLinkPagePath(classifyChatLink("/dashboard", ORIGIN))).toBeNull();
  });
});
