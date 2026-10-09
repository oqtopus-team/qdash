import assert from "node:assert/strict";
import { test } from "node:test";

import { Type } from "typebox";

import {
  MAX_SUPPLIED_IMAGES,
  acceptsImages,
  hasImages,
  latestImages,
  requestedImageCount,
  withImages,
} from "../src/figure-context.ts";

test("the tool's max_images decides how many newest figures are supplied", () => {
  assert.equal(requestedImageCount({ context: "x" }), 1);
  assert.equal(requestedImageCount({ max_images: 2 }), 2);
  assert.equal(requestedImageCount({ max_images: 2.7 }), 2);
  assert.equal(requestedImageCount({ max_images: 0 }), 1);
  assert.equal(requestedImageCount({ max_images: 99 }), MAX_SUPPLIED_IMAGES);
  assert.equal(requestedImageCount({ max_images: "2" }), 1);
  assert.equal(requestedImageCount(null), 1);
});

const image = (data) => ({ type: "image", data, mimeType: "image/png" });
const text = (t) => ({ type: "text", text: t });

test("only tools declaring an `images` parameter are filled", () => {
  assert.equal(acceptsImages(Type.Object({ context: Type.String() })), false);
  assert.equal(
    acceptsImages(Type.Object({ context: Type.String(), images: Type.Optional(Type.Array(Type.Any())) })),
    true,
  );
});

test("the newest figure in the transcript wins, scanning entries newest-first", () => {
  const entries = [
    // Newest entry: a plain user question without figures.
    { model: [{ role: "user", content: "Is the fit good?" }] },
    // A tool round that fetched two figures; the user message before it had another.
    {
      model: [
        { role: "user", content: [text("here"), image("older-attachment")] },
        { role: "assistant", content: [text("fetching")] },
        { role: "toolResult", content: [text("figure"), image("expected"), image("measured")] },
      ],
    },
    { model: [{ role: "user", content: [text("first"), image("oldest")] }] },
  ];
  assert.deepEqual(latestImages(entries), [image("measured")]);
  assert.deepEqual(latestImages(entries, 2), [image("expected"), image("measured")]);
  assert.deepEqual(latestImages([{ model: [{ role: "user", content: "no figures" }] }]), []);
  assert.deepEqual(latestImages([]), []);
});

test("malformed image blocks and non-array content are ignored", () => {
  const entries = [
    { model: [{ role: "toolResult", content: [{ type: "image", data: 42 }, { type: "image" }] }] },
    { model: [{ role: "user", content: [image("ok"), { type: "image", data: "x" }] }] },
  ];
  assert.deepEqual(latestImages(entries), [image("ok")]);
});

// A real PNG header in base64 is longer than any placeholder a model invents.
const REAL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";

test("images are added only when the model passed none", () => {
  const given = { context: "Rabi", images: [{ data: REAL, mimeType: "image/png" }] };
  assert.equal(hasImages(given), true);
  assert.equal(hasImages({ context: "Rabi", images: [] }), false);
  assert.equal(hasImages(null), false);

  assert.equal(withImages(given, [image("transcript")]), given);
  assert.deepEqual(withImages({ context: "Rabi" }, [image("transcript")]), {
    context: "Rabi",
    images: [{ data: "transcript", mimeType: "image/png" }],
  });
  const none = { context: "Rabi" };
  assert.equal(withImages(none, []), none);
});

test("placeholders the model invents for `images` are replaced or dropped", () => {
  for (const data of ["<image 1>", "see attached figure", "expected.png", "data:image/png;base64,"]) {
    assert.equal(hasImages({ images: [{ data, mimeType: "image/png" }] }), false, data);
  }
  // One real image next to a placeholder is still not trusted as a whole.
  assert.equal(
    hasImages({ images: [{ data: REAL, mimeType: "image/png" }, { data: "<image 2>", mimeType: "image/png" }] }),
    false,
  );
  const placeholders = { context: "Rabi", images: [{ data: "<image 1>", mimeType: "image/png" }] };
  assert.deepEqual(withImages(placeholders, [image("transcript")]), {
    context: "Rabi",
    images: [{ data: "transcript", mimeType: "image/png" }],
  });
  assert.deepEqual(withImages(placeholders, []), { context: "Rabi" });
});
