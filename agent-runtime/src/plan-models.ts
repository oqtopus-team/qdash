import { createModels, type Api, type Model, type Models } from "@earendil-works/pi-ai";
import { openaiProvider } from "@earendil-works/pi-ai/providers/openai";

/**
 * A QDash user's own ChatGPT plan as a chat model provider.
 *
 * QDash's API looks up the signed-in user's Sign in with ChatGPT access token
 * and sends it with that user's chat turn only (`x-qdash-chatgpt-token`). The
 * token lives in the closure of one turn's `Models`; it is never written to
 * the durable store, a credential file, the process environment or the model
 * context.
 *
 * Conversations name the provider `chatgpt`, which the shared model runtime
 * does not know. So a model reference without the turn's token, a tool that
 * reuses the conversation's model through the shared runtime, or an
 * evaluation fails instead of quietly spending an operator `OPENAI_API_KEY`.
 * Requests are sent through pi's own `openai` provider, which recognises a
 * non-`sk-` bearer to api.openai.com as Sign in with ChatGPT and applies the
 * plan route's rules: `store: false`, `stream: true`, the full context in
 * `input`, no `max_output_tokens`/`temperature`/`prompt_cache_retention`, and
 * no `previous_response_id`.
 */
export const CHATGPT_PROVIDER = "chatgpt";

const OPENAI_PROVIDER = "openai";
const OPENAI_BASE_URL = "https://api.openai.com/v1";

/**
 * A provider catalog that can never resolve an ambient credential: no env,
 * no files, an empty credential store. Every request must carry its apiKey.
 */
export function createPlanCatalog(): Models {
  const catalog = createModels({
    authContext: {
      env: async () => undefined,
      fileExists: async () => false,
    },
  });
  catalog.setProvider(openaiProvider());
  return catalog;
}

/**
 * Whether pi sends this model's tools the way the plan route accepts them:
 * in `additional_tools` input items rather than top-level function tools
 * (OpenAI preview limitations, "Supported tools").
 */
function plansToolsAsAdditionalTools(model: Model<Api>): boolean {
  const compat = model.compat as Record<string, unknown> | undefined;
  return compat?.supportsAdditionalTools === true && compat?.supportsMidConvoSystemMessages === true;
}

/** The plan model for `id` as conversations see it, or undefined when QDash cannot run it. */
export function planModel(catalog: Models, id: string): Model<Api> | undefined {
  const model = catalog.getModel(OPENAI_PROVIDER, id);
  if (!model || model.api !== "openai-responses" || model.baseUrl !== OPENAI_BASE_URL) return undefined;
  if (!plansToolsAsAdditionalTools(model)) return undefined;
  // Sampling parameters are unsupported request fields on the plan route.
  const { samplingParams: _sampling, samplingParamsByThinkingLevel: _byLevel, ...rest } =
    model as Model<Api> & { samplingParams?: unknown; samplingParamsByThinkingLevel?: unknown };
  return { ...rest, provider: CHATGPT_PROVIDER } as Model<Api>;
}

/** Model IDs QDash can run on the plan route, for QDash's API to intersect with the account's list. */
export function planModelIds(catalog: Models): string[] {
  return catalog
    .getModels(OPENAI_PROVIDER)
    .filter((model) => planModel(catalog, model.id) !== undefined)
    .map((model) => model.id)
    .sort();
}

/** The user's plan token sent with this turn, if any. */
export function requestChatGPTToken(
  headers: Record<string, string | string[] | undefined>,
): string | undefined {
  const value = headers["x-qdash-chatgpt-token"];
  if (value === undefined) return undefined;
  if (typeof value !== "string" || !value.trim() || value.startsWith("sk-")) {
    // An OpenAI API key is not a ChatGPT plan token; refuse rather than bill it.
    throw new Error("Invalid ChatGPT plan token");
  }
  return value.trim();
}

/** Route one plan model to pi's openai provider with this turn's token as the only credential. */
function toOpenAI<T extends Model<Api>>(model: T): T {
  return { ...model, provider: OPENAI_PROVIDER, baseUrl: OPENAI_BASE_URL };
}

/**
 * The `Models` one chat turn runs on: everything from the shared runtime,
 * plus `chatgpt/<id>` served with `token`.
 */
export function withPlanToken(shared: Models, catalog: Models, token: string): Models {
  if (!token || token.startsWith("sk-")) throw new Error("A ChatGPT plan token is required");
  const isPlan = (model: { provider: string }) => model.provider === CHATGPT_PROVIDER;
  // Explicit apiKey wins over any stored or ambient credential in pi's auth resolution.
  const withToken = <O>(options: O): O => ({ ...(options ?? {}), apiKey: token }) as O;
  const overrides: Partial<Models> = {
    getModel(provider, id) {
      return provider === CHATGPT_PROVIDER ? planModel(catalog, id) : shared.getModel(provider, id);
    },
    getModels(provider) {
      if (provider === CHATGPT_PROVIDER) return [];
      return shared.getModels(provider);
    },
    stream(model, context, options) {
      return isPlan(model)
        ? catalog.stream(toOpenAI(model), context, withToken(options))
        : shared.stream(model, context, options);
    },
    complete(model, context, options) {
      return isPlan(model)
        ? catalog.complete(toOpenAI(model), context, withToken(options))
        : shared.complete(model, context, options);
    },
    streamSimple(model, context, options) {
      return isPlan(model)
        ? catalog.streamSimple(toOpenAI(model), context, withToken(options))
        : shared.streamSimple(model, context, options);
    },
    completeSimple(model, context, options) {
      return isPlan(model)
        ? catalog.completeSimple(toOpenAI(model), context, withToken(options))
        : shared.completeSimple(model, context, options);
    },
    streamDeferred(model, handle, options) {
      return isPlan(model)
        ? catalog.streamDeferred(toOpenAI(model), handle, withToken(options))
        : shared.streamDeferred(model, handle, options);
    },
    fetchDeferred(model, handle, options) {
      return isPlan(model)
        ? catalog.fetchDeferred(toOpenAI(model), handle, withToken(options))
        : shared.fetchDeferred(model, handle, options);
    },
    cancelDeferred(model, handle, options) {
      return isPlan(model)
        ? catalog.cancelDeferred(toOpenAI(model), handle, withToken(options))
        : shared.cancelDeferred(model, handle, options);
    },
    async getAuth(target: string | Parameters<Models["getAuth"]>[0], overrides?: Parameters<Models["getAuth"]>[1]) {
      const provider = typeof target === "string" ? target : target.provider;
      if (provider === CHATGPT_PROVIDER) {
        return { auth: { apiKey: token }, source: "QDash ChatGPT connection" };
      }
      return shared.getAuth(target as never, overrides);
    },
  };
  return new Proxy(shared, {
    get(target, property, receiver) {
      if (Object.prototype.hasOwnProperty.call(overrides, property)) {
        return overrides[property as keyof Models];
      }
      const value = Reflect.get(target, property, receiver);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
}
