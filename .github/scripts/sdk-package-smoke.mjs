import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// Run against an npm install of the SDK and client tarballs outside the monorepo. This
// catches missing published files, a dependency that only resolves inside the workspace,
// a second or bundled copy of the client, and declarations that do not resolve.
const [consumer] = process.argv.slice(2);
assert.ok(consumer, "Usage: sdk-package-smoke.mjs <consumer directory>");
const modules = join(consumer, "node_modules/@oqtopus-team");
const read = (path) => JSON.parse(readFileSync(path, "utf8"));
const sdkRoot = join(modules, "qdash-sdk");
const sdk = read(join(sdkRoot, "package.json"));
const client = read(join(modules, "qdash-client/package.json"));

assert.equal(sdk.name, "@oqtopus-team/qdash-sdk");
assert.notEqual(sdk.version, "0.0.0");
assert.deepEqual(Object.keys(sdk.dependencies ?? {}), ["@oqtopus-team/qdash-client"], "The SDK depends on the client only");
assert.equal(sdk.dependencies["@oqtopus-team/qdash-client"], sdk.version, "The SDK pins the client of its own release");
assert.equal(client.version, sdk.version);
assert.equal(client.dependencies?.["@oqtopus-team/qdash-sdk"], undefined, "The client must not depend on the SDK");
assert.ok(!client.exports["./sdk"], "The client has no SDK subpath");
assert.ok(!existsSync(join(sdkRoot, "node_modules/@oqtopus-team/qdash-client")), "npm must share one client copy");
for (const file of ["dist/index.js", "dist/index.d.ts", "README.md", "LICENSE"]) {
  assert.ok(existsSync(join(sdkRoot, file)), `${file} must be published`);
}
assert.ok(!existsSync(join(sdkRoot, "src")), "Sources are not published");
const bundle = readFileSync(join(sdkRoot, "dist/index.js"), "utf8");
assert.match(bundle, /from "@oqtopus-team\/qdash-client"/);
assert.doesNotMatch(bundle, /class QDashClient\b|class QDashApiError\b|axios/, "The SDK must not bundle the client");

// Import as the consumer would: resolution starts from a file in the consumer.
const probe = join(consumer, "sdk-probe.mjs");
writeFileSync(probe, 'export * as client from "@oqtopus-team/qdash-client";\nexport * as sdk from "@oqtopus-team/qdash-sdk";\n');
const { client: clientModule, sdk: sdkModule } = await import(pathToFileURL(probe).href);
for (const name of ["QDash", "Chip", "Workflows", "sweep", "qubitTargets", "customOneQubit"]) {
  assert.ok(name in sdkModule, `${name} must be exported`);
}
for (const name of ["QDashApiError", "QDashConfigError", "QDashNotFoundError", "QDashTimeoutError", "QDashValidationError"]) {
  assert.equal(sdkModule[name], clientModule[name], `${name} must be the client's class`);
}
const base = new clientModule.QDashClient(new clientModule.QDashConfig({ baseUrl: "https://qdash.example/api", apiToken: "t" }));
assert.ok(new sdkModule.QDash(base, { projectId: "p" }).client instanceof clientModule.QDashClient);

// Declarations resolve with Node's own module resolution when TypeScript is installed.
const tsc = join(consumer, "node_modules/typescript/bin/tsc");
if (existsSync(tsc)) {
  writeFileSync(join(consumer, "sdk-probe.mts"), [
    'import { QDashClient, QDashConfig, QDashNotFoundError } from "@oqtopus-team/qdash-client";',
    'import { QDash, qubitTargets, type RunResult } from "@oqtopus-team/qdash-sdk";',
    'const qdash: QDash = new QDash(new QDashClient(new QDashConfig({ baseUrl: "https://qdash.example/api" })));',
    'const targets = qubitTargets(["0"]);',
    "const check = (result: RunResult): string => result.status;",
    "export { qdash, targets, check, QDashNotFoundError };",
    "",
  ].join("\n"));
  execFileSync(process.execPath, [tsc, "--noEmit", "--strict", "--module", "nodenext", "--moduleResolution", "nodenext", "--target", "es2022", "--types", "node", "--skipLibCheck", "false", "sdk-probe.mts"], { cwd: consumer, stdio: "inherit" });
}
console.log(`${sdk.name}@${sdk.version}: standalone artifact verified with ${client.name}@${client.version}`);
