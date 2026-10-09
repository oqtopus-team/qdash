import assert from "node:assert/strict";
import { test } from "node:test";

import { Type } from "typebox";

import { acceptsImages, hasImages, latestImages, withImages } from "../src/figure-context.ts";

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

test("images are added only when the model passed none", () => {
  const given = { context: "Rabi", images: [{ data: "mine", mimeType: "image/png" }] };
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
