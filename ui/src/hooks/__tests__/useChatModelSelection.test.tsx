import { QueryClient, QueryClientProvider, focusManager } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useChatModelSelection, useChatThinkingSelection } from "../useChatModelSelection";

const customInstance = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/custom-instance", () => ({ customInstance }));

const QWEN = { provider: "openai-compatible-chat", name: "qwen", reasoning_effort: "medium" };
const KIMI = { provider: "openai-compatible-chat", name: "kimi", reasoning_effort: "high" };

function serveModels(...chatModels: object[]) {
  customInstance.mockResolvedValue({ data: { enabled: true, chat_models: chatModels } });
}

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

/** Settings and a docked chat mounted side by side. */
function useTwoSurfaces() {
  const settings = useChatModelSelection();
  const dock = useChatModelSelection();
  return { settings, dock, thinking: useChatThinkingSelection(dock) };
}

beforeEach(() => {
  localStorage.clear();
  customInstance.mockReset();
});

afterEach(() => {
  focusManager.setFocused(undefined);
});

describe("useChatModelSelection", () => {
  it("names the model the default resolves to and keeps surfaces in sync", async () => {
    serveModels(QWEN, KIMI);
    const { result } = renderHook(useTwoSurfaces, { wrapper: wrapper() });
    expect(result.current.dock.status).toBe("loading");
    await waitFor(() => expect(result.current.dock.status).toBe("ready"));

    expect(result.current.dock.selected).toMatchObject({ label: "qwen", model: null });
    expect(result.current.thinking.modelDefault).toBe("medium");

    act(() => result.current.settings.select("model:openai-compatible-chat:kimi"));
    expect(result.current.dock.selected.model).toEqual(KIMI);
    expect(result.current.thinking.modelDefault).toBe("high");

    act(() => result.current.thinking.select("low"));
    expect(localStorage.getItem("qdash_chat_thinking")).toBe("low");
  });

  it("shares the applied selection when browser persistence fails", async () => {
    serveModels(QWEN, KIMI);
    const { result } = renderHook(useTwoSurfaces, { wrapper: wrapper() });
    await waitFor(() => expect(result.current.dock.status).toBe("ready"));
    const write = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage unavailable");
    });
    try {
      act(() => result.current.settings.select("model:openai-compatible-chat:kimi"));
      expect(write).toHaveBeenCalled();
      expect(localStorage.getItem("qdash_chat_model_key")).toBeNull();
      expect(result.current.settings.selected.model).toEqual(KIMI);
      expect(result.current.dock.selected.model).toEqual(KIMI);
      expect(result.current.thinking.modelDefault).toBe("high");
    } finally {
      write.mockRestore();
      act(() => result.current.settings.select("default"));
    }
  });

  it("picks up a choice another tab stores", async () => {
    serveModels(QWEN, KIMI);
    const { result } = renderHook(useTwoSurfaces, { wrapper: wrapper() });
    await waitFor(() => expect(result.current.dock.status).toBe("ready"));

    localStorage.setItem("qdash_chat_model_key", "model:openai-compatible-chat:kimi");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "qdash_chat_model_key" }));
    });
    expect(result.current.dock.selected.label).toBe("kimi");
  });

  it("refetches the list on focus and drops a model the new config removed", async () => {
    serveModels(QWEN, KIMI);
    localStorage.setItem("qdash_chat_model_key", "model:openai-compatible-chat:kimi");
    const { result } = renderHook(useTwoSurfaces, { wrapper: wrapper() });
    await waitFor(() => expect(result.current.dock.selected.label).toBe("kimi"));

    // A redeploy left only one chat model; the user comes back to the tab.
    serveModels(QWEN);
    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });

    await waitFor(() => expect(result.current.dock.options).toHaveLength(1));
    expect(result.current.dock.selected).toMatchObject({ label: "qwen", model: null });
    expect(result.current.settings.unavailableModel).toBe("openai-compatible-chat:kimi");
  });

  it("keeps a choice by identity when the config is reordered", async () => {
    serveModels(QWEN, KIMI);
    localStorage.setItem("qdash_chat_model_key", "model:openai-compatible-chat:qwen");
    serveModels(KIMI, QWEN);
    const { result } = renderHook(useTwoSurfaces, { wrapper: wrapper() });
    await waitFor(() => expect(result.current.dock.status).toBe("ready"));
    expect(result.current.dock.selected.model).toEqual(QWEN);
    expect(result.current.dock.unavailableModel).toBeNull();
  });

  it("ignores a key from the old positional format", async () => {
    serveModels(QWEN, KIMI);
    localStorage.setItem("qdash_chat_model_key", "chat-1");
    const { result } = renderHook(useTwoSurfaces, { wrapper: wrapper() });
    await waitFor(() => expect(result.current.dock.status).toBe("ready"));
    expect(result.current.dock.selected.isConfiguredDefault).toBe(true);
    expect(result.current.dock.unavailableModel).toBeNull();
  });

  it("keeps a remembered model that became the default without a warning", async () => {
    // The first model's key was removed, so the server now lists KIMI first.
    localStorage.setItem("qdash_chat_model_key", "model:openai-compatible-chat:kimi");
    serveModels(KIMI);
    const { result } = renderHook(useTwoSurfaces, { wrapper: wrapper() });
    await waitFor(() => expect(result.current.dock.status).toBe("ready"));
    expect(result.current.dock.selected).toMatchObject({
      label: "kimi",
      model: null,
      isConfiguredDefault: true,
    });
    expect(result.current.dock.unavailableModel).toBeNull();
  });

  it("offers no model when none has its API key set", async () => {
    localStorage.setItem("qdash_chat_model_key", "model:openai-compatible-chat:kimi");
    customInstance.mockResolvedValue({ data: { enabled: true, chat_models: [], model: null } });
    const { result } = renderHook(useTwoSurfaces, { wrapper: wrapper() });
    await waitFor(() => expect(result.current.dock.status).toBe("none"));
    expect(result.current.dock.options).toHaveLength(1);
    expect(result.current.dock.selected).toMatchObject({
      label: "No chat model available",
      model: null,
      resolvedModel: null,
    });
    expect(result.current.settings.status).toBe("none");
    expect(result.current.dock.unavailableModel).toBeNull();
    expect(result.current.thinking.modelDefault).toBeNull();
  });

  it("falls back to the configured default when the list fails to load", async () => {
    customInstance.mockRejectedValue(new Error("down"));
    const { result } = renderHook(useTwoSurfaces, { wrapper: wrapper() });
    await waitFor(() => expect(result.current.dock.status).toBe("error"));
    expect(result.current.dock.selected).toMatchObject({
      label: "Configured default",
      model: null,
    });
  });
});
