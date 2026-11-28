import { createHash, randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import type { Api, ImageContent, Model, TextContent } from "@earendil-works/pi-ai";
import { ModelRuntime, type ToolDefinition as CodingAgentTool } from "@earendil-works/pi-coding-agent";
import {
  AssistantEntry,
  createRegistry,
  Harness,
  ROOT_CONVERSATION_ID,
  ToolResultEntry,
  type Conversation,
  type ConversationId,
  type EntryId,
  type Harness as DurableHarness,
  type HarnessSettings,
  type ModelRef,
} from "@earendil-works/pi-durable";
import { fitImages } from "@earendil-works/pi-durable/images/fit";
import { createNodePhotonImages } from "@earendil-works/pi-durable/images/node";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { imageLimits, type ImageLimits, type ImageProcessor } from "@earendil-works/pi-durable/tools";

import { createQDashConnection, type QDashAuth, type QDashConnection } from "./auth.ts";
import {
  ALLOWED_TOOL_NAMES,
  ALLOWLISTED_PACKAGES,
  isDeferredTool,
  REVIEWED_WRITE_TOOL_NAMES,
  SESSION_GRANTED_WRITE_TOOL_NAMES,
} from "./allowed-tools.ts";
import { compactionBudget, type CompactionBudget } from "./budget.ts";
import { chartTool } from "./chart-tool.ts";
import { buildCompactionExtension } from "./compaction.ts";
import {
  buildChatRegistry as buildChatRegistryFor,
  buildAgentExtension,
  USER_PREFERENCES_SECTION,
  type ChatRegistry,
  type ChatRegistryParts,
} from "./chat-registry.ts";
import { BranchError, branchFrom, openBranch } from "./branch.ts";
import { CHAT_QUEUE_SETTINGS, isUserMessage, readSteerReceipt, type SteerOutcome } from "./chat-control.ts";
import { removeStore, workspaceMarker } from "./store-identity.ts";
import {
  CODEMODE_GUIDELINE,
  CODEMODE_TOOL_NAME,
  deferredToolsGuideline,
  TOOL_SEARCH_TOOL_NAME,
} from "./codemode.ts";
import { uiTool } from "./ui-tool.ts";
import {
  buildPresentationTools,
  PRESENTATION_GUIDELINE,
  PRESENTATION_INTERNAL_CALLS,
  PRESENT_TOOL,
  configurePresentation,
} from "./presentation-tool.ts";
import { configureClassifierModels, readClassifierConfig } from "./classifier-models.ts";
import { buildClassifyChatTool, CLASSIFY_CHAT_TOOL, CLASSIFY_GUIDELINE, configureClassify } from "./classify-tool.ts";
import { loadLanguageConfig } from "./config.ts";
import { ExecWorkspace, execConfigFromEnv, removeWorkspace, WORKSPACE_TOOL_NAMES } from "./exec-env.ts";
import { askUserTool } from "./ask-tool.ts";
import {
  buildLocalToolGuide,
  bundledExtensions,
  createBundledResourceLoader,
  describeBundledExtensions,
  extensionPackage,
  isTrustedExtension,
  localToolNames,
  trustedBundleRoots,
} from "./bundled-extensions.ts";
import {
  runCodingAgentTool,
  type ApprovalRequest,
  type QDashWriteTools,
} from "./durable-tools.ts";
import {
  EVALUATION_TOOL,
  EVIDENCE_TOOL,
  EvaluationError,
  draftKnowledge,
  evaluateTask,
  plannerInstruction,
  previewEvaluationPrompts,
  plannerOutcome,
  recordFromDetails,
  type EvaluateRequest,
  type EvaluateResult,
  type PromptPreview,
  type PromptPreviewRequest,
  type ToolRun,
} from "./evaluate.ts";
import { formatSettledDetail } from "./events.ts";
import { logDurableReport } from "./durable-report.ts";
import { examplesOf, fetchKnowledgeDraft, fetchTaskKnowledgeResponse, renderReference } from "./knowledge-context.ts";
import type { TaskKnowledgeLike } from "./knowledge-context.ts";
import { resolveAgentConfigPaths, resolveAgentModelFiles } from "./agent-profile.ts";
import { chatCompactionOverrides, chatModelAvailability, missingCredentialMessage, NATIVE_API_KEY_ENV, PROVIDER_ALIASES, supportedThinkingLevel, writeModelsConfig, type ChatModelAvailability } from "./models-config.ts";
import type { PageContext } from "./page-context.ts";
import { buildSystemPrompt, buildUserInstructionsSection } from "./prompt.ts";
import {
  buildSkillTool,
  expandSkillCommand,
  skillCommands,
  type SkillCommand,
  type SkillSummary,
} from "./skill-tool.ts";
import { buildIntentGuide, extractToolGuide, TOOL_GUIDE_SKILL, toolGuideNames } from "./tool-guide.ts";

const AGENT_DIR = process.env.PI_CODING_AGENT_DIR ?? "/app/.pi-agent";
const WORK_DIR = process.env.AGENT_WORK_DIR ?? "/app/workspace";
const STATE_DIR = process.env.AGENT_STATE_DIR ?? "/app/state";
// config.yaml (AGENT_CONFIG_PATH) and the optional classifier.yaml
// (CLASSIFIER_CONFIG_PATH) default to /app/config/agent; chat.yaml and
// evaluation.yaml, or those of QDASH_AGENT_PROFILE, sit next to config.yaml.
// All are resolved once per process in SharedRuntime.create (see
// agent-profile.ts). The classifier models back present_results and classify
// when one of them is usable.
const CONFIG_ROOT = "/app/config";
// One model request; a whole turn is bounded by the server's own timers.
const MODEL_STREAM_TIMEOUT_MS = Number(process.env.MODEL_STREAM_TIMEOUT_MS ?? 180_000);
// The Agent workspace (agent-exec container); without it the chat has no
// shell or files, only QDash tools.
const EXEC_CONFIG = execConfigFromEnv();
// The pi packages built into this image are the only extensions and skills
// loaded (see bundled-extensions.ts). Those outside the allowlisted packages
// are trusted as a whole.
const BUNDLED = bundledExtensions(fileURLToPath(new URL("../../packages/", import.meta.url)));
const BUNDLED_PATHS = BUNDLED.map(({ path }) => path);
const EXTENSION_PATHS = trustedBundleRoots(BUNDLED, ALLOWLISTED_PACKAGES);

export type ThinkingLevel = "off" | "minimal" | "low" | "medium" | "high";

/**
 * Where a chat's durable state lives: the store (one SQLite file and one
 * workspace per owner and store session) and the conversation in it. A chat
 * that was never branched uses its own session ID as the store and the root
 * conversation; a branch uses the store of the chat it was branched from and
 * its own conversation. QDash's API resolves both from the chat session it
 * stored, never from what a browser sends.
 */
export interface StoreTarget {
  /** The store's session ID; unset, the chat's own `sessionId`. */
  storeSessionId?: string;
  /** The branch conversation in the store; unset, the root conversation. */
  conversationId?: ConversationId;
}

export interface SessionRequest extends StoreTarget {
  ownerId: string;
  sessionId: string;
  requestId?: string;
  message: string;
  provider?: string;
  modelName?: string;
  thinkingLevel?: ThinkingLevel;
  images?: Array<{ type: "image"; data: string; mimeType: string }>;
  /** The user's own chat instructions from QDash; a chat only, never an evaluation. */
  userInstructions?: string;
  /** What the user has open in QDash while chatting from the sidebar; rebuilt every turn. */
  pageContext?: PageContext;
}

/** What `chatSystemPrompt` returns. */
export interface ChatSystemPrompt {
  system_prompt: string;
  /** The user's preferences section, or null when they set none. */
  user_preferences: string | null;
  /** Tools offered to the chat; their descriptions travel with the request, not in this text. */
  tools: string[];
}

/** The system prompt a chat receives, with the user's preferences as the harness tags them. */
export function chatSystemPromptOf(
  systemPrompt: string,
  toolNames: readonly string[],
  userInstructions?: string,
): ChatSystemPrompt {
  const preferences = buildUserInstructionsSection(userInstructions);
  return {
    system_prompt: systemPrompt,
    user_preferences: preferences
      ? `<${USER_PREFERENCES_SECTION}>\n${preferences}\n</${USER_PREFERENCES_SECTION}>`
      : null,
    tools: [...toolNames].sort(),
  };
}

export interface OpenDurableSession {
  harness: DurableHarness;
  conversation: Conversation;
  writeTools: QDashWriteTools;
  /** Fit user-attached images to the session model's limits before committing them. */
  fitInputContent?(content: readonly (TextContent | ImageContent)[]): Promise<(TextContent | ImageContent)[]>;
  close(): Promise<void>;
}

/**
 * Fit user-attached images to the active model's limits before committing them
 * to the durable transcript. Notes (resize, format conversion, or omission of
 * an unreadable image) are appended as text so the model knows what changed.
 */
export async function fitInputContent(
  content: readonly (TextContent | ImageContent)[],
  limits: ImageLimits,
  processor: ImageProcessor,
): Promise<(TextContent | ImageContent)[]> {
  const fitted = await fitImages(content, limits, processor);
  if (fitted.kind === "unchanged") return [...content];
  return fitted.notes.length > 0
    ? [...fitted.content, { type: "text", text: fitted.notes.join("\n") }]
    : fitted.content;
}

/** Report a `models.json` load or validation error on `modelRuntime`, matching Pi's startup warning. */
export function warnModelsJsonError(
  modelRuntime: Pick<ModelRuntime, "getError">,
  warn: (message: string) => void = console.warn,
): string | undefined {
  const error = modelRuntime.getError();
  if (error) warn(`[agent-runtime] models.json error: ${error}`);
  return error;
}

/** A branch to fork: the source conversation of a store, the answer, and the QDash session it is for. */
export interface BranchRequest {
  ownerId: string;
  storeSessionId: string;
  /** The conversation the user branches from; unset, the root. */
  sourceConversationId?: ConversationId;
  at: EntryId;
  /** The QDash session the branch belongs to; the same one again returns the same branch. */
  targetSessionId: string;
}

/** Return a stable non-identifying filename for one user's QDash session. */
export function sessionStorageName(ownerId: string, sessionId: string): string {
  return `${createHash("sha256").update(ownerId).update("\0").update(sessionId).digest("hex")}.sqlite`;
}

/** Where an evaluation reads its knowledge: an uploaded draft when named, else the task's shared knowledge. */
function knowledgeSource(connection: QDashConnection, draftId: string | undefined, signal?: AbortSignal) {
  if (draftId) return draftKnowledge(() => fetchKnowledgeDraft(connection, draftId, signal));
  // One knowledge request per task serves both the reference and the examples.
  const responses = new Map<string, Promise<TaskKnowledgeLike | undefined>>();
  const load = (taskName: string) => {
    let pending = responses.get(taskName);
    if (!pending) {
      pending = fetchTaskKnowledgeResponse(connection, taskName, signal);
      responses.set(taskName, pending);
    }
    return pending;
  };
  return {
    fetchKnowledge: async (taskName: string) => {
      const knowledge = await load(taskName);
      return knowledge ? renderReference(knowledge) : undefined;
    },
    fetchExamples: async (taskName: string) => {
      const knowledge = await load(taskName);
      return knowledge ? examplesOf(knowledge) : [];
    },
  };
}

/** An enabled extension tool and the file that defines it. */
interface EnabledTool {
  definition: CodingAgentTool;
  path?: string;
}

/** Process-wide model, extension, and durable-harness configuration. */
export class SharedRuntime {
  private constructor(
    private readonly modelRuntime: ModelRuntime,
    private readonly buildChatRegistry: (
      connection: QDashConnection,
      userInstructions?: string,
      pageContext?: PageContext,
    ) => ChatRegistry,
    private readonly toolNames: string[],
    /** The same tools the chat registry adapts, for running outside a conversation. */
    private readonly enabledTools: ReadonlyMap<string, EnabledTool>,
    /** QDash's system prompt for chats, as built at startup. */
    private readonly systemPrompt: string,
    private readonly modelCompactionOverrides: Readonly<Record<string, CompactionBudget>> = {},
    /** The skills `read_skill` offers, which the user may also invoke as `/skill:name`. */
    private readonly skills: readonly SkillSummary[] = [],
    /** The chat.yaml the models were built from, for the chat model menus. */
    private readonly chatYaml: string = "",
    /** Shared Photon image processor for tool outputs and user-attached images. */
    private readonly imageProcessor?: ImageProcessor,
  ) {}

  /** chat.yaml's chat models in order, each marked by whether its credential is set. */
  async chatModels(): Promise<ChatModelAvailability[]> {
    const available = await this.modelRuntime.getAvailable();
    return chatModelAvailability(
      this.chatYaml,
      new Set(available.map((model) => `${model.provider}/${model.id}`)),
    );
  }

  /** The skills the chat composer offers after `/`, with their descriptions. */
  chatSkills(): SkillCommand[] {
    return skillCommands(this.skills);
  }

  /** The user's message with a leading `/skill:name` expanded to that skill. */
  expandSkillCommand(message: string): string {
    return expandSkillCommand(message, this.skills);
  }

  /**
   * The system prompt a chat of this user gets, as the model receives it:
   * QDash's own section, then the user's preferences wrapped the way the
   * harness wraps a tagged section. Read-only, for Settings.
   */
  chatSystemPrompt(userInstructions?: string): ChatSystemPrompt {
    return chatSystemPromptOf(this.systemPrompt, this.toolNames, userInstructions);
  }

  /** Load the Pi model catalog and adapt the bundled pi extensions once. */
  static async create(): Promise<SharedRuntime> {
    mkdirSync(STATE_DIR, { recursive: true });
    if (EXEC_CONFIG) {
      console.log(`[agent-runtime] workspace tools: agent-exec at ${EXEC_CONFIG.socketPath}`);
    } else {
      console.warn("[agent-runtime] workspace tools disabled: AGENT_EXEC_SOCKET is not set");
    }

    const configPaths = resolveAgentConfigPaths(process.env, CONFIG_ROOT, (message) =>
      console.warn(`[agent-runtime] ${message}`),
    );
    const { responseLanguage, thinkingLanguage } = loadLanguageConfig(configPaths.configPath);
    const loader = createBundledResourceLoader({ cwd: WORK_DIR, agentDir: AGENT_DIR, bundled: BUNDLED });
    await loader.reload();
    for (const { path, error } of loader.getExtensions().errors) {
      console.error(`[agent-runtime] extension ${path}: ${error}`);
    }

    const modelFiles = resolveAgentModelFiles(process.env, configPaths.configPath);
    console.log(
      `[agent-runtime] agent models: ${modelFiles.profile === undefined ? "default" : `profile ${modelFiles.profile}`} (${modelFiles.chatPath}, ${modelFiles.evaluationPath})`,
    );
    const { path: modelsPath, yaml: modelYaml } = writeModelsConfig(
      modelFiles,
      join(AGENT_DIR, "models.json"),
    );
    const modelRuntime = await ModelRuntime.create({
      modelsPath,
      authPath: join(AGENT_DIR, "auth.json"),
    });
    warnModelsJsonError(modelRuntime);

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
    for (const line of describeBundledExtensions(BUNDLED, EXTENSION_PATHS, extensions, loader.getSkills().skills)) {
      console.log(line);
    }
    // Trusted bundled roots offer every tool they define (see
    // buildQDashExtension); reviewed write names still require approval.
    const localTools = localToolNames(extensions, EXTENSION_PATHS);
    const allowed = new Set<string>([
      ...ALLOWED_TOOL_NAMES,
      ...REVIEWED_WRITE_TOOL_NAMES,
      ...SESSION_GRANTED_WRITE_TOOL_NAMES,
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
    // Listed in the prompt or marked in the guide, so the model loads them before calling.
    const deferredToolNames = qdashToolNames.filter(isDeferredTool);
    const toolGuide = guideSkill
      ? extractToolGuide(readFileSync(guideSkill.filePath, "utf8"), qdashToolNames, deferredToolNames)
      : null;
    if (!toolGuide) console.warn("[agent-runtime] no tool guide: qdash skill not found");
    const intentGuide = buildIntentGuide(qdashToolNames, deferredToolNames);
    const localToolGuide = buildLocalToolGuide(extensions, EXTENSION_PATHS, new Set(localTools));

    const classifiers = configureClassifierModels(
      readClassifierConfig(configPaths.classifierPath),
      modelRuntime,
      process.env,
      console,
    );
    const presentation = configurePresentation(classifiers, console);
    const presentationTools = presentation ? buildPresentationTools(presentation) : [];
    // On-demand classification the model asks for; separate from present_results' layouts.
    const classify = configureClassify(classifiers, console);

    // Built once: the same text every chat gets and Settings shows read-only.
    const systemPrompt = buildSystemPrompt(
      responseLanguage,
      thinkingLanguage,
      skills,
      toolGuide,
      localToolGuide,
      EXEC_CONFIG !== undefined,
      presentation ? PRESENTATION_GUIDELINE : null,
      classify ? CLASSIFY_GUIDELINE : null,
      {
        codemode: CODEMODE_GUIDELINE,
        deferredTools: deferredToolsGuideline(
          deferredToolNames,
          new Set([...toolGuideNames(toolGuide), ...toolGuideNames(intentGuide)]),
        ),
        intentGuide,
      },
    );
    const agentExtension = buildAgentExtension(systemPrompt, [
      chartTool,
      uiTool,
      ...presentationTools,
      ...(classify ? [buildClassifyChatTool(classify)] : []),
      askUserTool,
      ...(skills.length ? [buildSkillTool(skills)] : []),
    ]);
    const imageProcessor = await createNodePhotonImages();
    const chatParts: ChatRegistryParts = {
      extensions,
      modelRuntime,
      workDir: WORK_DIR,
      extensionPaths: EXTENSION_PATHS,
      agent: agentExtension,
      internalCalls: presentation ? PRESENTATION_INTERNAL_CALLS : {},
      codingTools: EXEC_CONFIG !== undefined,
      compaction: buildCompactionExtension({ timeoutMs: MODEL_STREAM_TIMEOUT_MS }),
      imageProcessor,
    };
    const buildChatRegistry = (
      connection: QDashConnection,
      userInstructions?: string,
      pageContext?: PageContext,
    ) => buildChatRegistryFor(chatParts, connection, userInstructions, pageContext);
    const toolNames = [
      ...qdashToolNames,
      "render_chart",
      "render_ui",
      ...(presentation ? [PRESENT_TOOL] : []),
      ...(classify ? [CLASSIFY_CHAT_TOOL] : []),
      "ask_user",
      ...(EXEC_CONFIG ? WORKSPACE_TOOL_NAMES : []),
      ...(skills.length ? ["read_skill"] : []),
      CODEMODE_TOOL_NAME,
      TOOL_SEARCH_TOOL_NAME,
    ];
    // Pinned definitions first so a trusted one replaces, as in buildQDashExtension.
    const enabledTools = new Map<string, EnabledTool>();
    const trusted = (extension: { path: string }) => isTrustedExtension(extension.path, EXTENSION_PATHS);
    for (const extension of [...extensions].sort((a, b) => Number(trusted(a)) - Number(trusted(b)))) {
      for (const [name, registered] of extension.tools) {
        if (allowed.has(name)) enabledTools.set(name, { definition: registered.definition, path: extension.path });
      }
    }

    const modelCompactionOverrides = chatCompactionOverrides(
      modelYaml.chatYaml,
      (provider, modelId) => modelRuntime.getModel(provider, modelId),
    );
    return new SharedRuntime(
      modelRuntime,
      buildChatRegistry,
      toolNames,
      enabledTools,
      systemPrompt,
      modelCompactionOverrides,
      skills,
      modelYaml.chatYaml,
      imageProcessor,
    );
  }

  /** A configured model named by the request, or none when the request names none. */
  private resolveModel(provider: string | undefined, modelName: string | undefined): Model<Api> | undefined {
    if (!provider && !modelName) return undefined;
    if (!provider || !modelName) {
      throw new EvaluationError("request", "model needs both provider and name", 400);
    }
    const providerId = PROVIDER_ALIASES[provider] ?? provider;
    const model = this.modelRuntime.getModel(providerId, modelName);
    if (!model) {
      throw new EvaluationError(
        "request",
        `unknown model ${providerId}/${modelName}: not declared in chat.yaml or evaluation.yaml`,
        400,
      );
    }
    return model;
  }

  /** Resolve an optional request pair into qcal_evaluate's `provider/modelId` form. */
  private resolveModelSpec(provider: string | undefined, modelName: string | undefined): string | undefined {
    const model = this.resolveModel(provider, modelName);
    return model ? `${model.provider}/${model.id}` : undefined;
  }

  /**
   * Evaluate one task result's figure without a conversation: evidence from
   * pi-qdash, judgement from pi-qcaleval, QDash's reference in between. The
   * optional model only serves pi-qcaleval's fallback when no calibration VLM
   * is configured.
   */
  async evaluateTask(
    request: EvaluateRequest & {
      provider?: string;
      modelName?: string;
      evaluationProvider?: string;
      evaluationModelName?: string;
    },
    auth: QDashAuth,
    signal?: AbortSignal,
  ): Promise<EvaluateResult> {
    const evidence = this.enabledTools.get(EVIDENCE_TOOL);
    const evaluation = this.enabledTools.get(EVALUATION_TOOL);
    if (!evidence || !evaluation) {
      const missing = [!evidence && EVIDENCE_TOOL, !evaluation && EVALUATION_TOOL].filter(Boolean);
      throw new EvaluationError("request", `evaluation tools not loaded: ${missing.join(", ")}`, 503);
    }
    const model = this.resolveModel(request.provider, request.modelName);
    const evaluationModel = this.resolveModelSpec(
      request.evaluationProvider,
      request.evaluationModelName,
    );
    const connection = await createQDashConnection(auth);
    try {
      return await evaluateTask({ ...request, evaluationModel }, {
        runTool: async (name, args) => {
          const tool = this.enabledTools.get(name);
          if (!tool) throw new EvaluationError("request", `tool ${name} is not enabled`, 503);
          return (await runCodingAgentTool(
            tool.definition,
            `evaluate:${randomUUID()}`,
            args,
            signal,
            this.modelRuntime,
            WORK_DIR,
            connection,
            model,
          )) as ToolRun;
        },
        ...knowledgeSource(connection, request.knowledgeDraftId, signal),
        evaluator: evaluation.path ? extensionPackage(evaluation.path, BUNDLED_PATHS) : undefined,
      });
    } finally {
      await connection.close();
    }
  }

  /**
   * The prompts an evaluation of a task would send, built the way a direct
   * evaluation builds them (QDash's reference and examples, the evaluator's
   * templates) but without a figure or a model call.
   */
  async previewEvaluationPrompts(
    request: PromptPreviewRequest,
    auth: QDashAuth,
    signal?: AbortSignal,
  ): Promise<PromptPreview> {
    const evaluation = this.enabledTools.get(EVALUATION_TOOL);
    if (!evaluation) {
      throw new EvaluationError("request", `evaluation tools not loaded: ${EVALUATION_TOOL}`, 503);
    }
    const connection = await createQDashConnection(auth);
    try {
      return await previewEvaluationPrompts(request, {
        runTool: async (name, args) => {
          const tool = this.enabledTools.get(name);
          if (!tool) throw new EvaluationError("request", `tool ${name} is not enabled`, 503);
          return (await runCodingAgentTool(
            tool.definition,
            `preview:${randomUUID()}`,
            args,
            signal,
            this.modelRuntime,
            WORK_DIR,
            connection,
            undefined,
          )) as ToolRun;
        },
        ...knowledgeSource(connection, request.knowledgeDraftId, signal),
      });
    } finally {
      await connection.close();
    }
  }

  /**
   * Evaluate one task result the way the chat does: a planner turn in a
   * throwaway conversation, told to summarise the result and judge its figure.
   * The record comes from the `qcal_evaluate` result the durable wrapper
   * stamped (see evaluate.ts), so it has the same shape as a direct
   * evaluation, plus what the planner did and answered. The conversation's
   * state is removed afterwards.
   */
  async evaluateWithPlanner(
    request: EvaluateRequest & {
      provider?: string;
      modelName?: string;
      evaluationProvider?: string;
      evaluationModelName?: string;
      thinkingLevel?: ThinkingLevel;
    },
    auth: QDashAuth,
    signal?: AbortSignal,
  ): Promise<EvaluateResult> {
    if (!request.provider || !request.modelName) {
      throw new EvaluationError("request", "planner mode needs a model provider and name", 400);
    }
    if (request.knowledgeDraftId) {
      // The planner's qcal_evaluate call is filled with the shared knowledge.
      throw new EvaluationError("request", "a knowledge draft can only be evaluated in direct mode", 400);
    }
    this.resolveModel(request.provider, request.modelName);
    const evaluationModel = this.resolveModelSpec(
      request.evaluationProvider,
      request.evaluationModelName,
    );
    const evaluation = this.enabledTools.get(EVALUATION_TOOL);
    if (!evaluation) {
      throw new EvaluationError("request", `evaluation tools not loaded: ${EVALUATION_TOOL}`, 503);
    }
    const ownerId = "evaluation";
    const sessionId = `planner-${randomUUID()}`;
    const started = Date.now();
    const opened = await this.openSession(
      {
        ownerId,
        sessionId,
        message: "",
        provider: request.provider,
        modelName: request.modelName,
        thinkingLevel: request.thinkingLevel,
      },
      auth,
    );
    try {
      const { conversation } = opened;
      const onAbort = () => void conversation.abort(BACKGROUND_CONTEXT);
      signal?.addEventListener("abort", onAbort, { once: true });
      let settled;
      try {
        const submission = await conversation.submit(
          {
            type: "input",
            content: plannerInstruction(
              request.taskId,
              request.question,
              request.withExamples,
              evaluationModel,
            ),
          },
          BACKGROUND_CONTEXT,
        );
        settled = await submission.wait(BACKGROUND_CONTEXT);
      } finally {
        signal?.removeEventListener("abort", onAbort);
      }
      const view = await conversation.context(BACKGROUND_CONTEXT);
      const outcome = plannerOutcome(view.entries);
      const answer =
        settled.status === "done" && settled.type === "input"
          ? await answerText(conversation, settled.answer)
          : "";
      if (outcome.error) throw new EvaluationError("evaluation", outcome.error);
      if (!outcome.details) {
        const why =
          settled.status === "done"
            ? `the planner did not call ${EVALUATION_TOOL}${answer ? `: ${answer.slice(0, 300)}` : ""}`
            : `planner turn ${settled.reason}${formatSettledDetail(settled.detail)}`;
        throw new EvaluationError("evaluation", why);
      }
      const usedModel = (outcome.details as Record<string, unknown>).model as
        | { provider?: unknown; modelId?: unknown }
        | undefined;
      const usedModelSpec =
        typeof usedModel?.provider === "string" && typeof usedModel.modelId === "string"
          ? `${usedModel.provider}/${usedModel.modelId}`
          : undefined;
      if (evaluationModel && usedModelSpec !== evaluationModel) {
        throw new EvaluationError(
          "evaluation",
          `${EVALUATION_TOOL} used ${usedModelSpec ?? "no model"}; requested ${evaluationModel}`,
        );
      }
      const providerId = PROVIDER_ALIASES[request.provider] ?? request.provider;
      return recordFromDetails(request.taskId, outcome.details, {
        mode: "planner",
        usage: outcome.usage,
        evaluator: evaluation.path ? extensionPackage(evaluation.path, BUNDLED_PATHS) : undefined,
        planner: {
          model: `${providerId}/${request.modelName}`,
          answer,
          tool_calls: outcome.toolCalls,
          duration_ms: Date.now() - started,
        },
      });
    } finally {
      try {
        await opened.close();
      } finally {
        await this.deleteSessionState(ownerId, sessionId);
      }
    }
  }

  /** Resolve a configured QDash model without allowing an invisible fallback. */
  private resolveModelWithLimits(
    provider: string | undefined,
    modelName: string | undefined,
  ): { ref: ModelRef; contextWindow: number; maxTokens: number } {
    if (!provider || !modelName) throw new Error("provider and model name are required");
    const providerId = PROVIDER_ALIASES[provider] ?? provider;
    const model = this.modelRuntime.getModel(providerId, modelName);
    if (!model) {
      throw new Error(
        `unknown model ${providerId}/${modelName}: not declared in chat.yaml or evaluation.yaml`,
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

  /**
   * Where one steer stands, read from the session's store without opening a
   * harness: no recovery, task, or admission. SQLite may still take the store's
   * lock briefly (see `readSteerReceipt`).
   */
  async steerReceipt(
    ownerId: string,
    sessionId: string,
    projectId: string | undefined,
    requestId: string,
    target: StoreTarget = {},
  ): Promise<SteerOutcome | "wrong_project"> {
    const path = join(STATE_DIR, sessionStorageName(ownerId, target.storeSessionId ?? sessionId));
    return readSteerReceipt(
      path,
      projectId,
      requestId,
      BACKGROUND_CONTEXT,
      target.conversationId ?? ROOT_CONVERSATION_ID,
    );
  }

  /** Where the SQLite store of one owner and store session lives. */
  storePath(ownerId: string, storeSessionId: string): string {
    return join(STATE_DIR, sessionStorageName(ownerId, storeSessionId));
  }

  /**
   * Delete a closed durable store and its workspace, if the store is
   * `generation` (see store-identity.ts). A store holds a chat and every branch
   * of it, so QDash deletes it only with the last chat session that uses it; Pi
   * has no way to delete one conversation of a store. The caller holds the store.
   */
  async deleteSessionState(
    ownerId: string,
    sessionId: string,
    generation?: string,
  ): Promise<"removed" | "absent" | "stale"> {
    // Only a session that used its workspace has a directory to remove; for the
    // others (most evaluations, chats that never ran code) no daemon is started.
    const { outcome, hadWorkspace } = removeStore(this.storePath(ownerId, sessionId), generation);
    if (outcome === "stale" || !EXEC_CONFIG || !hadWorkspace) return outcome;
    try {
      await removeWorkspace(EXEC_CONFIG, ownerId, sessionId);
    } catch (error) {
      // The store is gone either way; a workspace left behind is only disk.
      console.warn(`[agent-runtime] could not remove the workspace of ${sessionId}:`, error);
    }
    return outcome;
  }

  /**
   * Open a store only to cancel work in it (see `stopStoredConversation`):
   * no extension, so no tool, hook, or extension task of the chat is
   * registered, no workspace, and no QDash connection. Scheduling starts
   * paused. The caller holds the store and has checked that it exists.
   */
  async openStoreForCleanup(ownerId: string, storeSessionId: string): Promise<{ harness: DurableHarness; close(): Promise<void> }> {
    const storageName = sessionStorageName(ownerId, storeSessionId);
    const harness = await Harness.open(
      await openNodeSqliteStorage(join(STATE_DIR, storageName)),
      {
        // Only for a deferred response a stopped run still polls: its abort cancels it.
        models: this.modelRuntime,
        registry: createRegistry(),
        onReport: (report) => logDurableReport(storageName, report),
        settings: { ...CHAT_QUEUE_SETTINGS },
      },
      BACKGROUND_CONTEXT,
    );
    return { harness, close: () => harness.close(BACKGROUND_CONTEXT) };
  }

  /**
   * Open a chat's store with its tools, as `openSession` and `forkSession` do.
   * Scheduling starts paused. The workspace and its marker belong to the store,
   * so every conversation of it shares the same directory.
   */
  private async openStore(
    ownerId: string,
    storeSessionId: string,
    auth: QDashAuth,
    options: {
      userInstructions?: string;
      pageContext?: PageContext;
      settings?: Pick<HarnessSettings, "compaction">;
    } = {},
  ): Promise<{
    harness: DurableHarness;
    writeTools: QDashWriteTools;
    workspace: ExecWorkspace | undefined;
    close(): Promise<void>;
  }> {
    const storageName = sessionStorageName(ownerId, storeSessionId);
    const path = join(STATE_DIR, storageName);
    const connection = await createQDashConnection(auth);
    const workspace = EXEC_CONFIG ? new ExecWorkspace(EXEC_CONFIG, ownerId, storeSessionId) : undefined;
    // Remembered next to the store once the directory exists, so deleting the
    // session later knows whether there is a workspace to remove.
    const marker = workspaceMarker(path);
    let marked = existsSync(marker);
    const workspaceEnv = async (target: { cwd?: string }) => {
      const env = await workspace!.env(target.cwd);
      if (!marked) {
        writeFileSync(marker, "");
        marked = true;
      }
      return env;
    };
    let harness: DurableHarness | undefined;
    let closeTools: (() => Promise<void>) | undefined;
    const close = async () => {
      try {
        await harness?.close(BACKGROUND_CONTEXT);
      } finally {
        // After the harness: no script starts once its sandbox is closed, and
        // a script still running resumes with the session's next sandbox.
        try {
          await closeTools?.();
        } finally {
          workspace?.close();
          await connection.close();
        }
      }
    };
    try {
      const { registry, writeTools, close: closeRegistry } = this.buildChatRegistry(
        connection,
        options.userInstructions,
        options.pageContext,
      );
      closeTools = closeRegistry;
      harness = await Harness.open(
        await openNodeSqliteStorage(path),
        {
          models: this.modelRuntime,
          registry,
          ...(workspace ? { env: workspaceEnv } : {}),
          onReport: (report) => logDurableReport(storageName, report),
          settings: {
            stream: { timeoutMs: MODEL_STREAM_TIMEOUT_MS },
            ...CHAT_QUEUE_SETTINGS,
            ...options.settings,
          },
        },
        BACKGROUND_CONTEXT,
      );
      return { harness, writeTools, workspace, close };
    } catch (error) {
      await close();
      throw error;
    }
  }

  /**
   * Open or recover the SQLite-backed conversation of one user/session: the
   * root of its own store, or the branch `request.conversationId` of the store
   * `request.storeSessionId`. Task scheduling starts paused;
   * `harness.resume()` or a submit starts it.
   */
  async openSession(request: SessionRequest, auth: QDashAuth): Promise<OpenDurableSession> {
    const {
      ref: model,
      contextWindow,
      maxTokens,
    } = this.resolveModelWithLimits(request.provider, request.modelName);
    // A native catalog model without its key is refused here, named, never swapped for another.
    const missing =
      model.provider in NATIVE_API_KEY_ENV
        ? missingCredentialMessage(
            model.provider,
            model.modelId,
            (await this.modelRuntime.checkAuth(model.provider)) !== undefined,
          )
        : undefined;
    if (missing) throw new Error(missing);
    const selectedBudget = compactionBudget(contextWindow, maxTokens);
    const opened = await this.openStore(request.ownerId, request.storeSessionId ?? request.sessionId, auth, {
      userInstructions: request.userInstructions,
      pageContext: request.pageContext,
      settings: {
        compaction: {
          enabled: true,
          ...selectedBudget,
          modelOverrides: {
            ...this.modelCompactionOverrides,
            [`${model.provider}/${model.modelId}`]: selectedBudget,
          },
        },
      },
    });
    const { harness, writeTools, workspace, close } = opened;
    try {
      // A level the model cannot run (Off on a model whose thinking is always on) runs at the
      // nearest one it can, not at pi's fallback effort (see supportedThinkingLevel).
      const catalogModel = this.modelRuntime.getModel(model.provider, model.modelId);
      const thinkingLevel = supportedThinkingLevel(catalogModel, request.thinkingLevel);
      const limits = imageLimits(catalogModel);
      const agent = {
        model,
        ...(thinkingLevel ? { thinkingLevel } : {}),
        // Where the harness builds the workspace environment: a directory of
        // the agent-exec container, not of this one.
        cwd: workspace?.cwd ?? WORK_DIR,
      };
      // A branch keeps the agent it was forked with; this turn's model and
      // thinking level apply from here, as for the root.
      const conversation =
        request.conversationId === undefined
          ? await harness.root(BACKGROUND_CONTEXT, { agent })
          : await openBranch(harness, request.conversationId, BACKGROUND_CONTEXT);
      await conversation.configure(agent, BACKGROUND_CONTEXT);
      // Scheduling is not resumed here: the first call that asks for progress
      // (a submit) resumes it, or the caller does once it watches the
      // conversation, so a run recovered from a crash is seen from its start.
      const processor = this.imageProcessor;
      return {
        harness,
        conversation,
        writeTools,
        ...(processor
          ? { fitInputContent: (content) => fitInputContent(content, limits, processor) }
          : {}),
        close,
      };
    } catch (error) {
      await close();
      throw error;
    }
  }

  /**
   * Fork a branch of a chat at one of its answers, in the chat's store (see
   * branch.ts). Opens the store with the caller's credentials and never resumes
   * scheduling, so nothing runs while it checks and forks; the caller holds
   * the store exclusively. Writes nothing to the source conversation.
   */
  async forkSession(
    request: BranchRequest,
    auth: QDashAuth,
  ): Promise<{ conversationId: ConversationId; created: boolean }> {
    const path = join(STATE_DIR, sessionStorageName(request.ownerId, request.storeSessionId));
    // Opening a missing store would create an empty one.
    if (!existsSync(path)) throw new BranchError("store_not_found", "the chat's store was not found");
    const { harness, close } = await this.openStore(request.ownerId, request.storeSessionId, auth);
    try {
      const source =
        request.sourceConversationId === undefined
          ? await harness.conversation(ROOT_CONVERSATION_ID, BACKGROUND_CONTEXT)
          : await openBranch(harness, request.sourceConversationId, BACKGROUND_CONTEXT);
      if (!source) throw new BranchError("conversation_not_found", "the chat's conversation was not found");
      return await branchFrom(harness, source, request.at, request.targetSessionId, BACKGROUND_CONTEXT);
    } finally {
      await close();
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
    if (isUserMessage(entry)) return undefined;
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
