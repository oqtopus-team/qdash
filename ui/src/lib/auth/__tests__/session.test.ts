import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { buildAuthHeaders, getAccessToken, getProjectId } from "../session";

describe("session helpers", () => {
  beforeEach(() => {
    document.cookie = "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    localStorage.clear();
  });

  afterEach(() => {
    document.cookie = "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    localStorage.clear();
  });

  it("does not expose the access token to client code", () => {
    document.cookie = "access_token=token-value; path=/";

    expect(getAccessToken()).toBeNull();
  });

  it("returns null when the access token cookie is missing", () => {
    expect(getAccessToken()).toBeNull();
  });

  it("reads the current project id from localStorage", () => {
    localStorage.setItem("qdash_current_project_id", "project-1");

    expect(getProjectId()).toBe("project-1");
  });

  it("builds project context headers without bearer tokens", () => {
    document.cookie = "access_token=encoded%20token; path=/";
    localStorage.setItem("qdash_current_project_id", "project-1");

    expect(buildAuthHeaders()).toEqual({
      "Content-Type": "application/json",
      "X-Project-Id": "project-1",
    });
  });
});
