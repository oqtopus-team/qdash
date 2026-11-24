import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// Run against an npm install of the SDK tarball alone, outside the monorepo. This catches
// missing published files, a dependency that only resolves inside the workspace, any
// dependency on the client, and declarations that do not resolve. Run with Node, and with
// Bun and --runtime-only to load and use the installed package on Bun as well.
const [consumer, mode] = process.argv.slice(2);
assert.ok(consumer, "Usage: sdk-package-smoke.mjs <consumer directory> [--runtime-only]");
const modules = join(consumer, "node_modules/@oqtopus-team");
const read = (path) => JSON.parse(readFileSync(path, "utf8"));
const sdkRoot = join(modules, "qdash-sdk");
const sdk = read(join(sdkRoot, "package.json"));

assert.equal(sdk.name, "@oqtopus-team/qdash-sdk");
assert.notEqual(sdk.version, "0.0.0");
assert.equal(sdk.dependencies?.["@oqtopus-team/qdash-client"], undefined, "The SDK must not depend on the client");
assert.deepEqual(Object.keys(sdk.dependencies ?? {}).sort(), ["ini", "smol-toml"], "The SDK depends on its own runtime libraries only");
for (const range of Object.values(sdk.dependencies)) {
  assert.ok(!/^(workspace:|file:|link:)/.test(range), "Published dependencies must resolve outside the workspace");
}
assert.ok(!existsSync(join(modules, "qdash-client")), "Installing the SDK must not install the client");
for (const file of ["dist/index.js", "dist/index.d.ts", "README.md", "LICENSE"]) {
  assert.ok(existsSync(join(sdkRoot, file)), `${file} must be published`);
}
assert.ok(!existsSync(join(sdkRoot, "src")), "Sources are not published");
assert.ok(!existsSync(join(sdkRoot, "fern")), "The generator configuration is not published");
const bundle = readFileSync(join(sdkRoot, "dist/index.js"), "utf8");
assert.doesNotMatch(bundle, /from "@oqtopus-team\/qdash-client"|class QDashClient\b|axios/, "The SDK must not use the client");

// Import as the consumer would: resolution starts from a file in the consumer.
const probe = join(consumer, "sdk-probe.mjs");
writeFileSync(probe, 'export * as sdk from "@oqtopus-team/qdash-sdk";\n');
const { sdk: sdkModule } = await import(pathToFileURL(probe).href);
for (const name of ["QDash", "QDashConfig", "QDashApiClient", "QDashApi", "Chip", "Workflows", "sweep", "qubitTargets", "customOneQubit", "ApiError"]) {
  assert.ok(name in sdkModule, `${name} must be exported`);
}
assert.ok(new sdkModule.QDashNotFoundError("x") instanceof sdkModule.ApiError);
const seen = [];
const qdash = new sdkModule.QDash(
  { baseUrl: "https://qdash.example/api", apiToken: "t", projectId: "p" },
  {
    fetch: async (input, init) => {
      const request = new Request(input, init);
      seen.push([request.method, new URL(request.url).pathname, request.headers.get("X-Project-Id"), request.headers.get("Authorization")]);
      return new Response(JSON.stringify({ flows: [] }), { headers: { "Content-Type": "application/json" } });
    },
  },
);
assert.deepEqual(await qdash.workflows.list(), []);
assert.deepEqual(seen, [["GET", "/api/flows", "p", "Bearer t"]]);

// Declarations resolve with Node's own module resolution when TypeScript is installed.
const tsc = join(consumer, "node_modules/typescript/bin/tsc");
if (mode !== "--runtime-only" && existsSync(tsc)) {
  writeFileSync(join(consumer, "sdk-probe.mts"), [
    'import { QDash, QDashApi, QDashConfig, QDashNotFoundError, qubitTargets, type RunResult } from "@oqtopus-team/qdash-sdk";',
    'const qdash: QDash = new QDash(new QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "t" }));',
    'const targets = qubitTargets(["0"]);',
    "const check = (result: RunResult): string => result.status;",
    "const detail = (value: QDashApi.ExecutionResponseDetail): string => value.status;",
    'const read = () => qdash.api.execution.getExecution({ execution_id: "e" });',
    "export { qdash, targets, check, detail, read, QDashNotFoundError };",
    "",
  ].join("\n"));
  execFileSync(process.execPath, [tsc, "--noEmit", "--strict", "--module", "nodenext", "--moduleResolution", "nodenext", "--target", "es2022", "--types", "node", "--skipLibCheck", "false", "sdk-probe.mts"], { cwd: consumer, stdio: "inherit" });
}
console.log(`${sdk.name}@${sdk.version}: standalone artifact verified${mode === "--runtime-only" ? " (runtime)" : ""}`);
