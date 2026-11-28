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
import {
  MAX_DECODED_IMAGE_PIXELS,
  createBoundedImageProcessor,
  declaredImageDimensions,
} from "../src/image-fit.ts";
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

function makePngHeader(width, height) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk("IHDR", ihdr),
  ]);
}

function makeJpegHeader(width, height) {
  const buf = Buffer.alloc(22);
  buf[0] = 0xff;
  buf[1] = 0xd8;
  buf[2] = 0xff;
  buf[3] = 0xe0;
  buf.writeUInt16BE(4, 4);
  buf[8] = 0xff;
  buf[9] = 0xff;
  buf[10] = 0xc0;
  buf.writeUInt16BE(11, 11);
  buf[13] = 8;
  buf.writeUInt16BE(height, 14);
  buf.writeUInt16BE(width, 16);
  return buf;
}

function makeGifHeader(width, height) {
  const buf = Buffer.alloc(10);
  buf.write("GIF89a", 0, "ascii");
  buf.writeUInt16LE(width, 6);
  buf.writeUInt16LE(height, 8);
  return buf;
}

function makeWebpVp8Header(width, height) {
  const buf = Buffer.alloc(30);
  buf.write("RIFF", 0, "ascii");
  buf.write("WEBP", 8, "ascii");
  buf.write("VP8 ", 12, "ascii");
  buf[23] = 0x9d;
  buf[24] = 0x01;
  buf[25] = 0x2a;
  buf.writeUInt16LE(width & 0x3fff, 26);
  buf.writeUInt16LE(height & 0x3fff, 28);
  return buf;
}

function makeWebpVp8lHeader(width, height) {
  const buf = Buffer.alloc(25);
  buf.write("RIFF", 0, "ascii");
  buf.write("WEBP", 8, "ascii");
  buf.write("VP8L", 12, "ascii");
  buf[20] = 0x2f;
  const bits = ((width - 1) & 0x3fff) | (((height - 1) & 0x3fff) << 14);
  buf.writeUInt32LE(bits >>> 0, 21);
  return buf;
}

function makeWebpVp8xHeader(width, height) {
  const buf = Buffer.alloc(30);
  buf.write("RIFF", 0, "ascii");
  buf.write("WEBP", 8, "ascii");
  buf.write("VP8X", 12, "ascii");
  const w = width - 1;
  const h = height - 1;
  buf[24] = w & 0xff;
  buf[25] = (w >> 8) & 0xff;
  buf[26] = (w >> 16) & 0xff;
  buf[27] = h & 0xff;
  buf[28] = (h >> 8) & 0xff;
  buf[29] = (h >> 16) & 0xff;
  return buf;
}

function makeBmpHeader(width, heightSigned) {
  const buf = Buffer.alloc(26);
  buf.write("BM", 0, "ascii");
  buf.writeUInt32LE(40, 14);
  buf.writeInt32LE(width, 18);
  buf.writeInt32LE(heightSigned, 22);
  return buf;
}

test("declaredImageDimensions parses PNG, JPEG, GIF, WebP, and BMP headers without decoding pixels", () => {
  assert.deepEqual(declaredImageDimensions(makePngHeader(30000, 30000)), { width: 30000, height: 30000 });
  assert.deepEqual(declaredImageDimensions(makeJpegHeader(6400, 4800)), { width: 6400, height: 4800 });
  assert.deepEqual(declaredImageDimensions(makeGifHeader(800, 600)), { width: 800, height: 600 });
  assert.deepEqual(declaredImageDimensions(makeWebpVp8Header(1200, 900)), { width: 1200, height: 900 });
  assert.deepEqual(declaredImageDimensions(makeWebpVp8lHeader(1024, 768)), { width: 1024, height: 768 });
  assert.deepEqual(declaredImageDimensions(makeWebpVp8xHeader(4096, 3072)), { width: 4096, height: 3072 });
  assert.deepEqual(declaredImageDimensions(makeBmpHeader(1920, 1080)), { width: 1920, height: 1080 });
  assert.deepEqual(declaredImageDimensions(makeBmpHeader(1920, -1080)), { width: 1920, height: 1080 });
  assert.equal(declaredImageDimensions(makePngHeader(0, 100)), undefined);
  assert.equal(declaredImageDimensions(Buffer.from("II*\x00not-tiff-bomb", "latin1")), undefined);
});

test("createBoundedImageProcessor rejects decompression bombs and unknown formats before invoking Photon", async () => {
  let innerCalls = 0;
  const spyInner = {
    async prepare() {
      innerCalls += 1;
      return { data: "ok", mimeType: "image/png" };
    },
  };
  const bounded = createBoundedImageProcessor(spyInner);
  assert.equal(MAX_DECODED_IMAGE_PIXELS, 25_000_000);
  const bombs = [
    [makePngHeader(30000, 30000), "image/png"],
    [makeJpegHeader(8000, 8000), "image/jpeg"],
    [makeGifHeader(6000, 6000), "image/gif"],
    [makeWebpVp8xHeader(8000, 8000), "image/webp"],
    [makeBmpHeader(8000, 8000), "image/bmp"],
    [Buffer.from("II*\x00unknown-format", "latin1"), "image/tiff"],
  ];
  for (const [bytes, mime] of bombs) {
    assert.equal(await bounded.prepare(bytes, mime, DEFAULT_IMAGE_LIMITS), undefined, mime);
  }
  assert.equal(innerCalls, 0);

  // Within the pixel cap delegates cleanly.
  assert.deepEqual(await bounded.prepare(makePngHeader(4000, 4000), "image/png", DEFAULT_IMAGE_LIMITS), {
    data: "ok",
    mimeType: "image/png",
  });
  assert.equal(innerCalls, 1);
});

test("bounded Photon processor omits 30000x30000 PNG bombs in fitInputContent and buildChatRegistry without allocating pixels", async () => {
  const processor = createBoundedImageProcessor(await processorPromise);
  const bombBase64 = makePngHeader(30000, 30000).toString("base64");

  const fitted = await fitInputContent(
    [{ type: "text", text: "Huge image" }, { type: "image", data: bombBase64, mimeType: "image/png" }],
    DEFAULT_IMAGE_LIMITS,
    processor,
  );
  assert.deepEqual(fitted.filter((block) => block.type === "image"), []);
  const text = fitted.filter((block) => block.type === "text").map((block) => block.text).join("\n");
  assert.match(text, /cannot be prepared for the model and was left out/);

  const tool = imageTool("qdash_get_figure", () => ({
    content: [{ type: "image", data: bombBase64, mimeType: "image/png" }],
  }));
  const { entry, message } = await runToolTurn([tool], processor);
  assert.deepEqual(message.content.filter((block) => block.type === "image"), []);
  assert.equal(entry.data?.diagnostics?.[0]?.code, "image");
  assert.match(entry.data?.diagnostics?.[0]?.message ?? "", /cannot be prepared for the model and was left out/);
});
