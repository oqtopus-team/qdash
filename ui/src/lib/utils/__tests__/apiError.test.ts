import { describe, expect, it } from "vitest";

import { getApiErrorMessage } from "@/lib/utils/apiError";

const FALLBACK = "Something went wrong";

function apiError(detail: unknown, message = "Request failed with status code 400") {
  return Object.assign(new Error(message), { response: { data: { detail } } });
}

describe("getApiErrorMessage", () => {
  it("returns a string detail", () => {
    expect(getApiErrorMessage(apiError("Chip not found"), FALLBACK)).toBe("Chip not found");
  });

  it("joins the messages of a 422 validation detail array", () => {
    const detail = [
      { loc: ["body", "chip_id"], msg: "Field required", type: "missing" },
      { loc: ["body", "size"], msg: "Input should be a valid integer", type: "int_parsing" },
    ];

    expect(getApiErrorMessage(apiError(detail), FALLBACK)).toBe(
      "Field required; Input should be a valid integer",
    );
  });

  it("falls back to the error message when detail is missing or unusable", () => {
    expect(getApiErrorMessage(apiError(undefined), FALLBACK)).toBe(
      "Request failed with status code 400",
    );
    expect(getApiErrorMessage(apiError(""), FALLBACK)).toBe("Request failed with status code 400");
    expect(getApiErrorMessage(apiError([{ loc: ["body"] }]), FALLBACK)).toBe(
      "Request failed with status code 400",
    );
    expect(getApiErrorMessage(apiError({ code: 1 }), FALLBACK)).toBe(
      "Request failed with status code 400",
    );
  });

  it("returns the message of a plain Error", () => {
    expect(getApiErrorMessage(new Error("Network Error"), FALLBACK)).toBe("Network Error");
  });

  it("returns the fallback for non-Error values", () => {
    expect(getApiErrorMessage(null, FALLBACK)).toBe(FALLBACK);
    expect(getApiErrorMessage(undefined, FALLBACK)).toBe(FALLBACK);
    expect(getApiErrorMessage("oops", FALLBACK)).toBe(FALLBACK);
    expect(getApiErrorMessage({ response: { data: {} } }, FALLBACK)).toBe(FALLBACK);
    expect(getApiErrorMessage(new Error(""), FALLBACK)).toBe(FALLBACK);
  });
});
