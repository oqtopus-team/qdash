import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, rmSync } from "node:fs";
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
  UserEntry,
  type Conversation,
  type EntryId,
  type Harness as DurableHarness,
  type ModelRef,
} from "@earendil-works/pi-durable";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";

import { createQDashConnection, type QDashAuth, type QDashConnection } from "./auth.ts";
import {
  ALLOWED_TOOL_NAMES,
  ALLOWLISTED_PACKAGES,
  EXPERIMENTAL_WRITE_TOOL_NAMES,
  TRUSTED_EXTENSION_PACKAGES,
  isExperimentalWriteTool,
} from "./allowed-tools.ts";
import { compactionBudget } from "./budget.ts";
import { chartTool } from "./chart-tool.ts";
import { loadLanguageConfig } from "./config.ts";
import { askUserTool } from "./ask-tool.ts";
import { formatSettledDetail } from "./events.ts";
import {
  buildLocalToolGuide,
  localToolNames,
  describeExtensionError,
  discoverExtensionCheckouts,
  trustedCheckoutRoots,
} from "./local-extensions.ts";
import {
  buildQDashExtension,
  type ApprovalRequest,
  type QDashWriteTools,
} from "./durable-tools.ts";
import { PROVIDER_ALIASES, writeModelsConfig } from "./models-config.ts";
import { buildReviewSystemPrompt, buildSystemPrompt } from "./prompt.ts";
import { buildPythonTool } from "./python-tool.ts";
import { buildSkillTool, type SkillSummary } from "./skill-tool.ts";
import { submitReviewTool } from "./review-tool.ts";
import { extractToolGuide, TOOL_GUIDE_SKILL } from "./tool-guide.ts";

const AGENT_DIR = process.env.PI_CODING_AGENT_DIR ?? "/app/.pi-agent";
const WORK_DIR = process.env.AGENT_WORK_DIR ?? "/app/workspace";
const STATE_DIR = process.env.AGENT_STATE_DIR ?? "/app/state";
const COPILOT_CONFIG_PATH = process.env.COPILOT_CONFIG_PATH ?? "/app/config/copilot/config.yaml";
const CHAT_CONFIG_PATH = process.env.CHAT_CONFIG_PATH ?? "/app/config/copilot/chat.yaml";
const REVIEW_CONFIG_PATH = process.env.REVIEW_CONFIG_PATH ?? "/app/config/copilot/review.yaml";
// One model request; a whole turn is bounded by the server's own timers.
const MODEL_STREAM_TIMEOUT_MS = Number(process.env.MODEL_STREAM_TIMEOUT_MS ?? 180_000);
const EXPERIMENTAL_WRITE_TOOLS_ENABLED = ["1", "true", "yes", "on"].includes(
  (process.env.AGENT_RUNTIME_ENABLE_WRITE_TOOLS ?? "").trim().toLowerCase(),
);
// Local extension checkouts: compose mounts agent-runtime/extensions/ here. It
// is empty in production and in a clone without checkouts. Every checkout is
// loaded (replacing an installed copy of the same package); only those outside
// the allowlisted packages are trusted as a whole.
const EXTENSIONS_DIR = "/app/extensions";
const CHECKOUTS = discoverExtensionCheckouts(EXTENSIONS_DIR);
const CHECKOUT_PATHS = CHECKOUTS.map((checkout) => checkout.path);
const EXTENSION_PATHS = trustedCheckoutRoots(CHECKOUTS, ALLOWLISTED_PACKAGES);

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
  writeTools: QDashWriteTools;
  close(): Promise<void>;
}

/** Return a stable non-identifying filename for one user's QDash session. */
export function sessionStorageName(ownerId: string, sessionId: string): string {
  return `${createHash("sha256").update(ownerId).update("\0").update(sessionId).digest("hex")}.sqlite`;
}

/** Process-wide model, extension, and durable-harness configuration. */
export class SharedRuntime {
  private constructor(
    private readonly modelRuntime: ModelRuntime,
    private readonly buildChatRegistry: (connection: QDashConnection) => {
      registry: ReturnType<typeof createRegistry>;
      writeTools: QDashWriteTools;
    },
    private readonly toolNames: string[],
    private readonly reviewRegistry: ReturnType<typeof createRegistry>,
  ) {}

  /** Load the Pi model catalog and adapt the installed pi-qdash extension once. */
  static async create(): Promise<SharedRuntime> {
    mkdirSync(STATE_DIR, { recursive: true });
    if (EXPERIMENTAL_WRITE_TOOLS_ENABLED) {
      console.warn("[agent-runtime] experimental QDash write tools are enabled");
    }

    const { responseLanguage, thinkingLanguage } = loadLanguageConfig(COPILOT_CONFIG_PATH);
    const loader = new DefaultResourceLoader({
      cwd: WORK_DIR,
      agentDir: AGENT_DIR,
      additionalExtensionPaths: CHECKOUT_PATHS,
    });
    await loader.reload();
    for (const { path, error } of loader.getExtensions().errors) {
      const report = describeExtensionError(path, error, CHECKOUT_PATHS);
      if (report.level === "error") console.error(report.message);
      else console.log(report.message);
    }

    const modelsPath = writeModelsConfig(
      CHAT_CONFIG_PATH,
      REVIEW_CONFIG_PATH,
      join(AGENT_DIR, "models.json"),
    );
    const modelRuntime = await ModelRuntime.create({
      modelsPath,
      authPath: join(AGENT_DIR, "auth.json"),
    });

    const skills: SkillSummary[] = loader
      .getSkills()
      .skills.filter((skill) => !skill.disableModelInvocation)
      .map(({ name, description, filePath }) => ({
        name,
        description,
        filePath,
      }));
    console.log(
      `[agent-runtime] skills: ${skills.map((skill) => skill.name).join(", ") || "none"}`,
    );

    const extensions = loader.getExtensions().extensions;
    // Local checkouts and trusted installed packages are trusted as a whole
    // (see buildQDashExtension); the experimental write opt-in still applies
    // to their tool names.
    const localTools = localToolNames(extensions, EXTENSION_PATHS, TRUSTED_EXTENSION_PACKAGES).filter(
      (name) => EXPERIMENTAL_WRITE_TOOLS_ENABLED || !isExperimentalWriteTool(name),
    );
    if (CHECKOUT_PATHS.length || localTools.length) {
      console.log(
        `[agent-runtime] trusted extensions: packages=${TRUSTED_EXTENSION_PACKAGES.join(", ") || "none"}; local=${EXTENSION_PATHS.join(", ") || "none"} (tools: ${localTools.join(", ") || "none"}); allowlisted checkouts=${CHECKOUT_PATHS.filter((path) => !EXTENSION_PATHS.includes(path)).join(", ") || "none"}`,
      );
    }
    const allowed = new Set<string>([
      ...ALLOWED_TOOL_NAMES,
      ...(EXPERIMENTAL_WRITE_TOOLS_ENABLED ? EXPERIMENTAL_WRITE_TOOL_NAMES : []),
      ...localTools,
    ]);
    const qdashToolNames = [
      ...new Set(
        extensions.flatMap((extension) =>
          [...extension.tools.keys()].filter((name) => allowed.has(name)),
        ),
      ),
    ];
    const guideSkill = skills.find((skill) => skill.name === TOOL_GUIDE_SKILL);
    const toolGuide = guideSkill
      ? extractToolGuide(readFileSync(guideSkill.filePath, "utf8"), qdashToolNames)
      : null;
    if (!toolGuide) console.warn("[agent-runtime] no tool guide: qdash skill not found");
    const localToolGuide = buildLocalToolGuide(
      extensions,
      EXTENSION_PATHS,
      new Set(localTools),
      TRUSTED_EXTENSION_PACKAGES,
    );

    const copilotExtension = defineExtension({
      name: "qdash-copilot",
      sections: [
        section(
          "qdash-copilot",
          () =>
            buildSystemPrompt(
              responseLanguage,
              thinkingLanguage,
              EXPERIMENTAL_WRITE_TOOLS_ENABLED,
              skills,
              toolGuide,
              localToolGuide,
            ),
          { tag: false },
        ),
      ],
      tools: [chartTool, askUserTool, ...(skills.length ? [buildSkillTool(skills)] : [])],
    });
    const buildChatRegistry = (connection: QDashConnection) => {
      const registry = createRegistry();
      const qdash = buildQDashExtension(
        extensions,
        modelRuntime,
        WORK_DIR,
        connection,
        EXPERIMENTAL_WRITE_TOOLS_ENABLED,
        EXTENSION_PATHS,
        TRUSTED_EXTENSION_PACKAGES,
      );
      registry.install(qdash.extension);
      registry.install(copilotExtension);
      registry.install(
        defineExtension({
          name: "qdash-python",
          tools: [buildPythonTool(connection)],
        }),
      );
      return { registry, writeTools: qdash.writeTools };
    };
    const toolNames = [
      ...qdashToolNames,
      "render_chart",
      "run_python",
      "ask_user",
      ...(skills.length ? ["read_skill"] : []),
    ];

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
    return new SharedRuntime(modelRuntime, buildChatRegistry, toolNames, reviewRegistry);
  }

  /** Resolve a configured QDash model without allowing an invisible fallback. */
  private resolveModel(provider: string | undefined, modelName: string | undefined): ModelRef {
    return this.resolveModelWithLimits(provider, modelName).ref;
  }

  private resolveModelWithLimits(
    provider: string | undefined,
    modelName: string | undefined,
  ): { ref: ModelRef; contextWindow: number; maxTokens: number } {
    if (!provider || !modelName) throw new Error("provider and model name are required");
    const providerId = PROVIDER_ALIASES[provider] ?? provider;
    const model = this.modelRuntime.getModel(providerId, modelName);
    if (!model) {
      throw new Error(
        `unknown model ${providerId}/${modelName}: not declared in chat.yaml or review.yaml`,
      );
    }
    return {
      ref: { provider: providerId, modelId: modelName },
      contextWindow: model.contextWindow,
      maxTokens: model.maxTokens,
    };
  }

  /** Names of the tools the chat agent can actually call. */
  listToolNames(): string[] {
    return [...new Set(this.toolNames)].sort();
  }

  /** Delete the closed durable store for one deleted QDash session. */
  deleteSessionState(ownerId: string, sessionId: string): void {
    const path = join(STATE_DIR, sessionStorageName(ownerId, sessionId));
    for (const suffix of ["", "-wal", "-shm"]) rmSync(`${path}${suffix}`, { force: true });
  }

  /** Open or recover the SQLite-backed root conversation for one user/session. */
  async openSession(request: SessionRequest, auth: QDashAuth): Promise<OpenDurableSession> {
    const {
      ref: model,
      contextWindow,
      maxTokens,
    } = this.resolveModelWithLimits(request.provider, request.modelName);
    const path = join(STATE_DIR, sessionStorageName(request.ownerId, request.sessionId));
    const connection = await createQDashConnection(auth);
    let harness: DurableHarness | undefined;
    const close = async () => {
      try {
        await harness?.close(BACKGROUND_CONTEXT);
      } finally {
        await connection.close();
      }
    };
    try {
      const { registry, writeTools } = this.buildChatRegistry(connection);
      harness = await Harness.open(
        await openNodeSqliteStorage(path),
        {
          models: this.modelRuntime,
          registry,
          settings: {
            stream: { timeoutMs: MODEL_STREAM_TIMEOUT_MS },
            compaction: {
              enabled: true,
              ...compactionBudget(contextWindow, maxTokens),
            },
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
      return { harness, conversation, writeTools, close };
    } catch (error) {
      await close();
      throw error;
    }
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
      const settled = await submission
        .wait(BACKGROUND_CONTEXT)
        .finally(() => clearTimeout(timeout));
      if (settled.status !== "done" || settled.type !== "input") {
        throw new Error(
          `review was not answered: ${settled.reason}${formatSettledDetail(settled.detail)}`,
        );
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

/**
 * The write call the user is deciding on, if `id` names one still pending.
 *
 * Only an approval requested since the last user message counts: once the
 * decision has been submitted it is a user entry, so a replayed or stale
 * decision cannot run the operation a second time.
 */
export async function pendingApproval(
  conversation: Conversation,
  id: string,
): Promise<ApprovalRequest | undefined> {
  const view = await conversation.context(BACKGROUND_CONTEXT);
  for (let i = view.entries.length - 1; i >= 0; i--) {
    const entry = view.entries[i];
    if (UserEntry.is(entry)) return undefined;
    if (!ToolResultEntry.is(entry)) continue;
    const details = entry.model?.[0]?.role === "toolResult" ? entry.model[0].details : undefined;
    const approval = (details as { approval?: ApprovalRequest } | undefined)?.approval;
    if (approval?.id === id) return approval;
  }
  return undefined;
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
