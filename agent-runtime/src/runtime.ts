import { join } from "node:path";

import {
  DefaultResourceLoader,
  ModelRuntime,
  SessionManager,
  createAgentSession,
  type CreateAgentSessionResult,
} from "@earendil-works/pi-coding-agent";
import { EnvHttpProxyAgent, setGlobalDispatcher } from "undici";

import { resolveQDashApiToken } from "./auth.ts";
import { chartTool } from "./chart-tool.ts";
import { pythonTool } from "./python-tool.ts";
import { loadLanguageConfig } from "./config.ts";
import { buildEntries } from "./entries.ts";
import { EXCLUDED_TOOL_NAMES } from "./excluded-tools.ts";
import { PROVIDER_ALIASES, writeModelsConfig } from "./models-config.ts";
import { buildReviewSystemPrompt, buildSystemPrompt } from "./prompt.ts";
import { submitReviewTool } from "./review-tool.ts";

const AGENT_DIR = process.env.PI_CODING_AGENT_DIR ?? "/app/.pi-agent";
const WORK_DIR = process.env.AGENT_WORK_DIR ?? "/app/workspace";
const COPILOT_CONFIG_PATH =
  process.env.COPILOT_CONFIG_PATH ?? "/app/config/copilot/config.yaml";
const CHAT_CONFIG_PATH = process.env.CHAT_CONFIG_PATH ?? "/app/config/copilot/chat.yaml";
const REVIEW_CONFIG_PATH = process.env.REVIEW_CONFIG_PATH ?? "/app/config/copilot/review.yaml";
const HTTP_IDLE_TIMEOUT_MS = Number(process.env.HTTP_IDLE_TIMEOUT_MS ?? 300_000);

/**
 * Restore proxy support after importing pi.
 *
 * Pi replaces globalThis.fetch with npm undici's, which drops Node's built-in
 * NODE_USE_ENV_PROXY handling. Pi's CLI reinstalls a proxy-aware dispatcher at
 * startup, but the SDK does not, so behind a proxy every LLM call fails with
 * UND_ERR_CONNECT_TIMEOUT. HTTP(S)_PROXY and NO_PROXY are read from the
 * environment.
 */
function installProxyAwareDispatcher(): void {
  setGlobalDispatcher(
    new EnvHttpProxyAgent({
      allowH2: false,
      proxyTunnel: true,
      bodyTimeout: HTTP_IDLE_TIMEOUT_MS,
      headersTimeout: HTTP_IDLE_TIMEOUT_MS,
    }),
  );
}

/** Thinking level requested per model in QDash's chat config. */
export type ThinkingLevel = "off" | "minimal" | "low" | "medium" | "high";

export interface SessionRequest {
  sessionId: string;
  messages: unknown[];
  provider?: string;
  modelName?: string;
  thinkingLevel?: ThinkingLevel;
}

export interface ReviewSessionRequest {
  sessionId: string;
  provider?: string;
  modelName?: string;
}

/**
 * Process-wide resources shared by every conversation.
 *
 * Loading extensions and model catalogs is the expensive part; creating an
 * AgentSession on top of them costs a couple of milliseconds.
 */
export class SharedRuntime {
  private constructor(
    private readonly loader: DefaultResourceLoader,
    private readonly reviewLoader: DefaultResourceLoader,
    private readonly modelRuntime: ModelRuntime,
  ) {}

  static async create(): Promise<SharedRuntime> {
    installProxyAwareDispatcher();
    // Must follow the dispatcher install so the QDash origin bypasses any proxy.
    await resolveQDashApiToken();

    const { responseLanguage, thinkingLanguage } = loadLanguageConfig(COPILOT_CONFIG_PATH);

    const loader = new DefaultResourceLoader({
      cwd: WORK_DIR,
      agentDir: AGENT_DIR,
      systemPromptOverride: () => buildSystemPrompt(responseLanguage, thinkingLanguage),
    });
    await loader.reload();

    // A second loader, because the system prompt is fixed at loader construction
    // and createAgentSession has no per-session override.
    const reviewLoader = new DefaultResourceLoader({
      cwd: WORK_DIR,
      agentDir: AGENT_DIR,
      systemPromptOverride: () => buildReviewSystemPrompt(responseLanguage),
    });
    await reviewLoader.reload();

    const modelsPath = writeModelsConfig(
      CHAT_CONFIG_PATH,
      REVIEW_CONFIG_PATH,
      join(AGENT_DIR, "models.json"),
    );
    const modelRuntime = await ModelRuntime.create({
      modelsPath,
      authPath: join(AGENT_DIR, "auth.json"),
    });

    return new SharedRuntime(loader, reviewLoader, modelRuntime);
  }

  /**
   * Resolve a QDash provider/model pair against pi's catalog.
   *
   * Throws rather than falling back: answering with a different model than the
   * caller asked for is invisible in the result and makes the recorded model a
   * lie. See .agents/sessions/2026-09-28-analyze-sidebar-pi-agent/adr/0004-*.md
   */
  private resolveModel(provider: string | undefined, modelName: string | undefined) {
    if (!provider || !modelName) return undefined;
    const providerId = PROVIDER_ALIASES[provider] ?? provider;
    const model = this.modelRuntime.getModel(providerId, modelName);
    if (!model) {
      throw new Error(
        `unknown model ${providerId}/${modelName}: not declared in chat.yaml or review.yaml`,
      );
    }
    return model;
  }

  /** Names of the tools the agent will actually see. Logged once at startup. */
  listToolNames(): string[] {
    const names = new Set<string>([chartTool.name, pythonTool.name]);
    for (const extension of this.loader.getExtensions().extensions) {
      for (const name of extension.tools?.keys() ?? []) names.add(name);
    }
    for (const name of EXCLUDED_TOOL_NAMES) names.delete(name);
    return [...names].sort();
  }

  /**
   * Create a session for one AI review.
   *
   * No stored history, no QDash tools: the prompt carries the whole context and
   * `submit_review` is the only way out.
   * See .agents/sessions/2026-09-28-ai-review-pi-agent/adr/0001-*.md
   */
  async createReviewSession(request: ReviewSessionRequest): Promise<CreateAgentSessionResult> {
    const model = this.resolveModel(request.provider, request.modelName);

    return createAgentSession({
      cwd: WORK_DIR,
      agentDir: AGENT_DIR,
      resourceLoader: this.reviewLoader,
      modelRuntime: this.modelRuntime,
      ...(model ? { model } : {}),
      noTools: "all",
      tools: [submitReviewTool.name],
      customTools: [submitReviewTool],
      sessionManager: SessionManager.inMemory(
        WORK_DIR,
        { id: request.sessionId },
        buildEntries(WORK_DIR, request.sessionId, []) as never,
      ),
    });
  }

  /** Create a throwaway session seeded with the stored conversation. */
  async createSession(request: SessionRequest): Promise<CreateAgentSessionResult> {
    const model = this.resolveModel(request.provider, request.modelName);

    return createAgentSession({
      cwd: WORK_DIR,
      agentDir: AGENT_DIR,
      resourceLoader: this.loader,
      modelRuntime: this.modelRuntime,
      ...(model ? { model } : {}),
      ...(request.thinkingLevel ? { thinkingLevel: request.thinkingLevel } : {}),
      noTools: "builtin",
      excludeTools: EXCLUDED_TOOL_NAMES,
      customTools: [chartTool, pythonTool],
      sessionManager: SessionManager.inMemory(
        WORK_DIR,
        { id: request.sessionId },
        buildEntries(WORK_DIR, request.sessionId, request.messages) as never,
      ),
    });
  }
}
