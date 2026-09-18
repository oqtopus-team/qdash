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
import { loadLanguageConfig } from "./config.ts";
import { buildEntries } from "./entries.ts";
import { EXCLUDED_TOOL_NAMES } from "./excluded-tools.ts";
import { buildSystemPrompt } from "./prompt.ts";

const AGENT_DIR = process.env.PI_CODING_AGENT_DIR ?? "/app/.pi-agent";
const WORK_DIR = process.env.AGENT_WORK_DIR ?? "/app/workspace";
const COPILOT_CONFIG_PATH =
  process.env.COPILOT_CONFIG_PATH ?? "/app/config/copilot/config.yaml";
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

/**
 * QDash's chat config names providers the way LiteLLM does; pi uses its own ids.
 * Without this, enabling a Bedrock model in chat.yaml silently falls back to the
 * default model.
 */
const PROVIDER_ALIASES: Record<string, string> = { bedrock: "amazon-bedrock" };

/** Thinking level requested per model in QDash's chat config. */
export type ThinkingLevel = "off" | "minimal" | "low" | "medium" | "high";

export interface SessionRequest {
  sessionId: string;
  messages: unknown[];
  provider?: string;
  modelName?: string;
  thinkingLevel?: ThinkingLevel;
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

    const modelRuntime = await ModelRuntime.create({
      modelsPath: join(AGENT_DIR, "models.json"),
      authPath: join(AGENT_DIR, "auth.json"),
    });

    return new SharedRuntime(loader, modelRuntime);
  }

  /** Names of the tools the agent will actually see. Logged once at startup. */
  listToolNames(): string[] {
    const names = new Set<string>([chartTool.name]);
    for (const extension of this.loader.getExtensions().extensions) {
      for (const name of extension.tools?.keys() ?? []) names.add(name);
    }
    for (const name of EXCLUDED_TOOL_NAMES) names.delete(name);
    return [...names].sort();
  }

  /** Create a throwaway session seeded with the stored conversation. */
  async createSession(request: SessionRequest): Promise<CreateAgentSessionResult> {
    const provider = request.provider
      ? (PROVIDER_ALIASES[request.provider] ?? request.provider)
      : undefined;
    const model =
      provider && request.modelName
        ? this.modelRuntime.getModel(provider, request.modelName)
        : undefined;
    if (provider && request.modelName && !model) {
      console.warn(
        `[agent-runtime] unknown model ${provider}/${request.modelName}, falling back to default`,
      );
    }

    return createAgentSession({
      cwd: WORK_DIR,
      agentDir: AGENT_DIR,
      resourceLoader: this.loader,
      modelRuntime: this.modelRuntime,
      ...(model ? { model } : {}),
      ...(request.thinkingLevel ? { thinkingLevel: request.thinkingLevel } : {}),
      noTools: "builtin",
      excludeTools: EXCLUDED_TOOL_NAMES,
      customTools: [chartTool],
      sessionManager: SessionManager.inMemory(
        WORK_DIR,
        { id: request.sessionId },
        buildEntries(WORK_DIR, request.sessionId, request.messages) as never,
      ),
    });
  }
}
