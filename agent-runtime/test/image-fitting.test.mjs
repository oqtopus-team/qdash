import assert from "node:assert/strict";
import { test } from "node:test";
import { deflateSync } from "node:zlib";

import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai";
import { createModels } from "@earendil-works/pi-ai/models";
import { Harness, MemoryStorage, ToolResultEntry } from "@earendil-works/pi-durable";
import { createNodePhotonImages } from "@earendil-works/pi-durable/images/node";
import { DEFAULT_IMAGE_LIMITS } from "@earendil-works/pi-durable/tools";
import { Type } from "typebox";

import { buildAgentExtension, buildChatRegistry } from "../src/chat-registry.ts";
import { PRESENTATION_INTERNAL_CALLS } from "../src/presentation-tool.ts";
import { latestFigures } from "../src/figure-context.ts";
import { fitInputContent } from "../src/runtime.ts";

const context = BACKGROUND_CONTEXT;
const connection = { toolArgs: { profile: "runtime", configPath: "/private/config.ini", useEnv: false } };
const modelRuntime = { getModel: () => undefined };
const LOCAL = "/app/packages/local";

function crc32(buf) {
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i += 1) {
    crc ^= buf[i];
    for (let bit = 0; bit < 8; bit += 1) {
      crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const typeBytes = Buffer.from(type, "ascii");
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBytes, data])), 0);
  return Buffer.concat([len, typeBytes, data, crc]);
}

/** Minimal valid RGBA PNG of exact `width` x `height` pixels. */
function makePng(width, height) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // RGBA
  const stride = 1 + width * 4;
  const raw = Buffer.alloc(stride * height, 0);
  for (let y = 0; y < height; y += 1) {
    const row = y * stride;
    raw[row] = 0; // filter None
    if (width > 0) {
      raw[row + 1] = 30;
      raw[row + 2] = 120;
      raw[row + 3] = 220;
      raw[row + 4] = 255;
    }
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", deflateSync(raw)),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

function readPngDimensions(base64) {
  const buf = Buffer.from(base64, "base64");
  assert.equal(buf.subarray(0, 8).toString("hex"), "89504e470d0a1a0a");
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

function imageTool(name, respond) {
  return {
    definition: {
      name,
      label: name,
      description: `${name} (test)`,
      parameters: Type.Object({}),
      execute: async () => respond(),
    },
  };
}

async function runToolTurn(extensions, imageProcessor, { codingTools = false } = {}) {
  const faux = fauxProvider({ tokensPerSecond: 0 });
  const models = createModels();
  models.setProvider(faux.provider);
  const model = faux.getModel();
  faux.setResponses([
    fauxAssistantMessage([fauxToolCall("qdash_get_figure", {}, { id: "fig-1" })], { stopReason: "toolUse" }),
    fauxAssistantMessage([fauxText("done")]),
  ]);
  const chat = buildChatRegistry(
    {
      extensions: [{ tools: new Map(extensions.map((tool) => [tool.definition.name, tool])) }],
      modelRuntime,
      workDir: "/tmp/work",
      extensionPaths: [LOCAL],
      agent: buildAgentExtension("QDash test prompt", []),
      internalCalls: PRESENTATION_INTERNAL_CALLS,
      codingTools,
      imageProcessor,
    },
    connection,
  );
  const harness = await Harness.open(
    new MemoryStorage(),
    { models, registry: chat.registry, settings: { retry: { enabled: false } } },
    context,
  );
  const conversation = await harness.root(context, {
    agent: { model: { provider: model.provider, modelId: model.id } },
  });
  harness.resume();
  try {
    const submission = await conversation.submit({ type: "input", content: "Inspect figure" }, context);
    const settled = await submission.wait(context);
    assert.equal(settled.status, "done");
    const view = await conversation.context(context);
    const entries = view.entries.filter((entry) => ToolResultEntry.is(entry));
    return {
      chat,
      viewEntries: view.entries,
      entry: entries[0],
      message: entries[0]?.model[0],
    };
  } finally {
    await harness.close(context);
    await chat.close();
  }
}

const processorPromise = createNodePhotonImages({ idleMs: 100 });

test("small valid PNG passes through buildChatRegistry unchanged and stays intact for transcript readers", async () => {
  const processor = await processorPromise;
  const smallPng = makePng(4, 4).toString("base64");
  const tool = imageTool("qdash_get_figure", () => ({
    content: [
      { type: "text", text: "Fetched Rabi figure." },
      { type: "image", data: smallPng, mimeType: "image/png" },
    ],
  }));
  const { entry, message, viewEntries } = await runToolTurn([tool], processor);
  const images = message.content.filter((block) => block.type === "image");
  assert.deepEqual(images, [{ type: "image", data: smallPng, mimeType: "image/png" }]);
  assert.deepEqual(entry.data?.diagnostics ?? [], []);
  const latest = latestFigures([...viewEntries].reverse());
  assert.deepEqual(latest.images, [{ type: "image", data: smallPng, mimeType: "image/png" }]);
});

test("oversized PNG returned by a tool is resized within limits and attaches a diagnostic note", async () => {
  const processor = await processorPromise;
  const widePng = makePng(2100, 10).toString("base64");
  const tool = imageTool("qdash_get_figure", () => ({
    content: [
      { type: "text", text: "Wide plot." },
      { type: "image", data: widePng, mimeType: "image/png" },
    ],
  }));
  const { entry, message } = await runToolTurn([tool], processor);
  const images = message.content.filter((block) => block.type === "image");
  assert.equal(images.length, 1);
  assert.equal(images[0].mimeType, "image/png");
  const dims = readPngDimensions(images[0].data);
  assert.ok(dims.width <= DEFAULT_IMAGE_LIMITS.maxWidth);
  assert.ok(dims.height <= DEFAULT_IMAGE_LIMITS.maxHeight);
  const diagnostics = entry.data?.diagnostics ?? [];
  assert.equal(diagnostics.length, 1);
  assert.equal(diagnostics[0].code, "image");
  assert.match(diagnostics[0].message, /Resized from 2100x10 to /);
});

test("corrupt image bytes returned by a tool are omitted with an explanation instead of poisoning the transcript", async () => {
  const processor = await processorPromise;
  const corrupt = Buffer.from("not-really-a-png", "utf8").toString("base64");
  const tool = imageTool("qdash_get_figure", () => ({
    content: [
      { type: "text", text: "Broken figure." },
      { type: "image", data: corrupt, mimeType: "image/png" },
    ],
  }));
  const { entry, message } = await runToolTurn([tool], processor);
  assert.deepEqual(message.content.filter((block) => block.type === "image"), []);
  const diagnostics = entry.data?.diagnostics ?? [];
  assert.equal(diagnostics.length, 1);
  assert.equal(diagnostics[0].code, "image");
  assert.match(diagnostics[0].message, /cannot be prepared for the model and was left out/);
});

test("wrong declared image MIME type is corrected to the actual bytes MIME type", async () => {
  const processor = await processorPromise;
  const realPng = makePng(4, 4).toString("base64");
  const tool = imageTool("qdash_get_figure", () => ({
    content: [{ type: "image", data: realPng, mimeType: "image/jpeg" }],
  }));
  const { message } = await runToolTurn([tool], processor);
  assert.deepEqual(message.content.filter((block) => block.type === "image"), [
    { type: "image", data: realPng, mimeType: "image/png" },
  ]);
});

test("fitInputContent keeps valid user images unchanged, resizes oversized ones, and omits corrupt ones", async () => {
  const processor = await processorPromise;
  const smallPng = makePng(4, 4).toString("base64");
  const unchanged = await fitInputContent(
    [{ type: "text", text: "Look at this" }, { type: "image", data: smallPng, mimeType: "image/png" }],
    DEFAULT_IMAGE_LIMITS,
    processor,
  );
  assert.deepEqual(unchanged, [
    { type: "text", text: "Look at this" },
    { type: "image", data: smallPng, mimeType: "image/png" },
  ]);

  const widePng = makePng(2100, 10).toString("base64");
  const resized = await fitInputContent(
    [{ type: "text", text: "Wide user image" }, { type: "image", data: widePng, mimeType: "image/png" }],
    DEFAULT_IMAGE_LIMITS,
    processor,
  );
  const resizedImages = resized.filter((block) => block.type === "image");
  assert.equal(resizedImages.length, 1);
  assert.ok(readPngDimensions(resizedImages[0].data).width <= DEFAULT_IMAGE_LIMITS.maxWidth);
  const resizeNotes = resized.filter((block) => block.type === "text").map((block) => block.text).join("\n");
  assert.match(resizeNotes, /Resized from 2100x10 to /);

  const corrupt = Buffer.from("invalid-image-bytes", "utf8").toString("base64");
  const omitted = await fitInputContent(
    [{ type: "text", text: "Broken attachment" }, { type: "image", data: corrupt, mimeType: "image/png" }],
    DEFAULT_IMAGE_LIMITS,
    processor,
  );
  assert.deepEqual(omitted.filter((block) => block.type === "image"), []);
  const omitNotes = omitted.filter((block) => block.type === "text").map((block) => block.text).join("\n");
  assert.match(omitNotes, /cannot be prepared for the model and was left out/);
});

test("buildChatRegistry with codingTools: true registers workspace tools alongside fit-images", async () => {
  const processor = await processorPromise;
  const widePng = makePng(2100, 10).toString("base64");
  const tool = imageTool("qdash_get_figure", () => ({
    content: [{ type: "image", data: widePng, mimeType: "image/png" }],
  }));
  const { chat, entry } = await runToolTurn([tool], processor, { codingTools: true });
  const toolNames = new Set(chat.registry.snapshot().tools().map(({ tool: registered }) => registered.name));
  for (const expected of ["read", "write", "edit", "bash"]) {
    assert.ok(toolNames.has(expected), `missing ${expected}`);
  }
  assert.equal(entry.data?.diagnostics?.[0]?.code, "image");
});
