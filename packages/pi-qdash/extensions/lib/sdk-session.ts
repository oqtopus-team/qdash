import type { QDashConfig as ClientConfig } from "@oqtopus-team/qdash-client";
import { QDash } from "@oqtopus-team/qdash-sdk";

/**
 * The SDK session a tool runs on, for the client the tool already resolved from its profile or
 * the environment. The SDK is self-contained, so it gets the client's connection settings
 * rather than the client itself.
 */
export type SdkSessionFactory = (client: { config: ClientConfig }) => QDash;

/**
 * An SDK session with the client's base URL, credentials, project, Cloudflare Access headers,
 * timeout, user agent and read attempts. A username/password sign-in happens once per session;
 * proxy and TLS overrides need a custom fetch, as they do in the client.
 */
export const sdkSession: SdkSessionFactory = ({ config }) =>
  new QDash({
    baseUrl: config.baseUrl,
    ...(config.apiToken ? { apiToken: config.apiToken } : {}),
    ...(config.username ? { username: config.username } : {}),
    ...(config.passwordEnv ? { passwordEnv: config.passwordEnv } : {}),
    ...(config.projectId ? { projectId: config.projectId } : {}),
    ...(config.cfAccessClientId ? { cfAccessClientId: config.cfAccessClientId } : {}),
    ...(config.cfAccessClientSecret ? { cfAccessClientSecret: config.cfAccessClientSecret } : {}),
    ...(config.proxy ? { proxy: config.proxy } : {}),
    timeoutSec: config.timeoutSeconds,
    verifyTls: config.verifyTls,
    userAgent: config.userAgent,
    readAttempts: config.retry.maxAttempts,
  });
