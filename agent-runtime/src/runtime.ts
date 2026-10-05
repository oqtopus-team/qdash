import { createHash } from "node:crypto";
import { mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { DefaultResourceLoader, ModelRuntime } from "@earendil-works/pi-coding-agent";
import {
  AssistantEntry,
  createRegistry,
  defineExtension,
  Harness,
  MemoryStorage,
  section,
  ToolResultEntry,
  type Conversation,
  type EntryId,
  type Harness as DurableHarness,
  type ModelRef,
} from "@earendil-works/pi-durable";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";

import { resolveQDashApiToken } from "./auth.ts";
import { chartTool } from "./chart-tool.ts";
import { loadLanguageConfig } from "./config.ts";
import { buildQDashExtension } from "./durable-tools.ts";
import { PROVIDER_ALIASES, writeModelsConfig } from "./models-config.ts";
import { buildReviewSystemPrompt, buildSystemPrompt } from "./prompt.ts";
import { pythonTool } from "./python-tool.ts";
import { submitReviewTool } from "./review-tool.ts";

const AGENT_DIR = process.env.PI_CODING_AGENT_DIR ?? "/app/.pi-agent";
const WORK_DIR = process.env.AGENT_WORK_DIR ?? "/app/workspace";
const STATE_DIR = process.env.AGENT_STATE_DIR ?? "/app/state";
const COPILOT_CONFIG_PATH =
  process.env.COPILOT_CONFIG_PATH ?? "/app/config/copilot/config.yaml";
const CHAT_CONFIG_PATH = process.env.CHAT_CONFIG_PATH ?? "/app/config/copilot/chat.yaml";
const REVIEW_CONFIG_PATH = process.env.REVIEW_CONFIG_PATH ?? "/app/config/copilot/review.yaml";
const EXPERIMENTAL_WRITE_TOOLS_ENABLED = ["1", "true", "yes", "on"].includes(
  (process.env.AGENT_RUNTIME_ENABLE_WRITE_TOOLS ?? "").trim().toLowerCase(),
);

export type ThinkingLevel = "off" | "minimal" | "low" | "medium" | "high";

export interface SessionRequest {
  ownerId: string;
  sessionId: string;
  requestId?: string;
  message: string;
  provider?: string;
  modelName?: string;
  thinkingLevel?: ThinkingLevel;
  images?: Array<{ type: "image"; data: string; mimeType: string }>;
}

export interface ReviewSessionRequest {
  prompt: string;
  provider?: string;
  modelName?: string;
  images?: Array<{ type: "image"; data: string; mimeType: string }>;
}

export interface OpenDurableSession {
  harness: DurableHarness;
  conversation: Conversation;
}

/** Return a stable non-identifying filename for one user's QDash session. */
export function sessionStorageName(ownerId: string, sessionId: string): string {
  return `${createHash("sha256").update(ownerId).update("\0").update(sessionId).digest("hex")}.sqlite`;
}

/** Process-wide model, extension, and durable-harness configuration. */
export class SharedRuntime {
  private constructor(
    private readonly modelRuntime: ModelRuntime,
    private readonly chatRegistry: ReturnType<typeof createRegistry>,
    private readonly reviewRegistry: ReturnType<typeof createRegistry>,
  ) {}

  /** Load the Pi model catalog and adapt the installed pi-qdash extension once. */
  static async create(): Promise<SharedRuntime> {
    await resolveQDashApiToken();
    mkdirSync(STATE_DIR, { recursive: true });
    if (EXPERIMENTAL_WRITE_TOOLS_ENABLED) {
      console.warn("[agent-runtime] experimental QDash write tools are enabled");
    }

    const { responseLanguage, thinkingLanguage } = loadLanguageConfig(COPILOT_CONFIG_PATH);
    const loader = new DefaultResourceLoader({ cwd: WORK_DIR, agentDir: AGENT_DIR });
    await loader.reload();

    const modelsPath = writeModelsConfig(
      CHAT_CONFIG_PATH,
      REVIEW_CONFIG_PATH,
      join(AGENT_DIR, "models.json"),
    );
    const modelRuntime = await ModelRuntime.create({
      modelsPath,
      authPath: join(AGENT_DIR, "auth.json"),
    });

    const chatRegistry = createRegistry();
    chatRegistry.install(
      buildQDashExtension(
        loader.getExtensions().extensions,
        modelRuntime,
        WORK_DIR,
        EXPERIMENTAL_WRITE_TOOLS_ENABLED,
      ),
    );
    chatRegistry.install(
      defineExtension({
        name: "qdash-copilot",
        sections: [
          section(
            "qdash-copilot",
            () =>
              buildSystemPrompt(
                responseLanguage,
                thinkingLanguage,
                EXPERIMENTAL_WRITE_TOOLS_ENABLED,
              ),
            { tag: false },
          ),
        ],
        tools: [chartTool, pythonTool],
      }),
    );

    const reviewRegistry = createRegistry();
    reviewRegistry.install(
      defineExtension({
        name: "qdash-review",
        sections: [
          section("qdash-review", () => buildReviewSystemPrompt(responseLanguage), {
            tag: false,
          }),
        ],
        tools: [submitReviewTool],
      }),
    );
    return new SharedRuntime(modelRuntime, chatRegistry, reviewRegistry);
  }

  /** Resolve a configured QDash model without allowing an invisible fallback. */
  private resolveModel(provider: string | undefined, modelName: string | undefined): ModelRef {
    if (!provider || !modelName) throw new Error("provider and model name are required");
    const providerId = PROVIDER_ALIASES[provider] ?? provider;
    if (!this.modelRuntime.getModel(providerId, modelName)) {
      throw new Error(
        `unknown model ${providerId}/${modelName}: not declared in chat.yaml or review.yaml`,
      );
    }
    return { provider: providerId, modelId: modelName };
  }

  /** Names of the tools the chat agent can actually call. */
  listToolNames(): string[] {
    return [...new Set(this.chatRegistry.snapshot().tools().map(({ tool }) => tool.name))].sort();
  }

  /** Delete the closed durable store for one deleted QDash session. */
  deleteSessionState(ownerId: string, sessionId: string): void {
    const path = join(STATE_DIR, sessionStorageName(ownerId, sessionId));
    for (const suffix of ["", "-wal", "-shm"]) rmSync(`${path}${suffix}`, { force: true });
  }

  /** Open or recover the SQLite-backed root conversation for one user/session. */
  async openSession(request: SessionRequest): Promise<OpenDurableSession> {
    const model = this.resolveModel(request.provider, request.modelName);
    const path = join(STATE_DIR, sessionStorageName(request.ownerId, request.sessionId));
    const harness = await Harness.open(
      await openNodeSqliteStorage(path),
      {
        models: this.modelRuntime,
        registry: this.chatRegistry,
        settings: {
          stream: { timeoutMs: Number(process.env.CHAT_TIMEOUT_MS ?? 180_000) },
          compaction: { enabled: true },
        },
      },
      BACKGROUND_CONTEXT,
    );
    const agent = {
      model,
      ...(request.thinkingLevel ? { thinkingLevel: request.thinkingLevel } : {}),
      cwd: WORK_DIR,
    };
    const conversation = await harness.root(BACKGROUND_CONTEXT, { agent });
    await conversation.configure(agent, BACKGROUND_CONTEXT);
    harness.resume();
    return { harness, conversation };
  }

  /** Run a stateless automatic review with durable task semantics in memory. */
  async runReview(request: ReviewSessionRequest): Promise<{ review?: unknown; text: string }> {
    const model = this.resolveModel(request.provider, request.modelName);
    const harness = await Harness.open(
      new MemoryStorage(),
      { models: this.modelRuntime, registry: this.reviewRegistry },
      BACKGROUND_CONTEXT,
    );
    try {
      const conversation = await harness.root(BACKGROUND_CONTEXT, {
        agent: { model, cwd: WORK_DIR },
      });
      const content = request.images?.length
        ? [{ type: "text" as const, text: request.prompt }, ...request.images]
        : request.prompt;
      const submission = await conversation.submit({ type: "input", content }, BACKGROUND_CONTEXT);
      const timeout = setTimeout(
        () => void conversation.abort(BACKGROUND_CONTEXT),
        Number(process.env.REVIEW_TIMEOUT_MS ?? 300_000),
      );
      const settled = await submission.wait(BACKGROUND_CONTEXT).finally(() => clearTimeout(timeout));
      if (settled.status !== "done" || settled.type !== "input") {
        throw new Error(`review was not answered: ${settled.reason}`);
      }

      const view = await conversation.context(BACKGROUND_CONTEXT);
      let review: unknown;
      for (const entry of view.entries) {
        if (!ToolResultEntry.is(entry)) continue;
        const message = entry.model?.[0];
        if (message?.role === "toolResult" && message.details) {
          review = (message.details as { review?: unknown }).review ?? review;
        }
      }
      return { review, text: await answerText(conversation, settled.answer) };
    } finally {
      await harness.close(BACKGROUND_CONTEXT);
    }
  }
}

/** Read the concatenated text blocks of a durable answer entry. */
export async function answerText(conversation: Conversation, answerId: EntryId): Promise<string> {
  const entry = await conversation.commit(
    (transaction) => transaction.entry(AssistantEntry, answerId),
    BACKGROUND_CONTEXT,
  );
  const message = entry?.model?.[0];
  if (message?.role !== "assistant") return "";
  return message.content
    .filter((block) => block.type === "text")
    .map((block) => (block.type === "text" ? block.text : ""))
    .join("");
}

export { BACKGROUND_CONTEXT };
