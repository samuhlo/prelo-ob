import test from "node:test";
import assert from "node:assert/strict";
import { composerFromDraft, draftFromComposer, emptyComposer, resumable } from "../src/session";

test("a parked selection survives the round trip through a shared draft", () => {
  const composer = { ...emptyComposer(), active: true, paths: ["a.md", "b.md"], title: "Redes", style: "retro90" as const, writingMode: "narrative" as const, language: "gl" as const, step: 2 as const };
  const restored = composerFromDraft(draftFromComposer(composer, "d1"));
  assert.deepEqual(restored, { ...composer, step: 1, draftId: "d1" });
  assert.equal(emptyComposer().active, false);
});

test("resume list shows a local parked selection once, before shared drafts", () => {
  const shared = draftFromComposer({ ...emptyComposer(), paths: ["a.md"] }, "shared");
  const parked = { ...emptyComposer(), paths: ["b.md"], draftId: "local" };
  assert.deepEqual(resumable([shared], parked).map(r => [r.draft.id, r.local]), [["local", true], ["shared", false]]);
  assert.equal(resumable([shared, { ...shared, id: "local" }], parked).length, 2);
  assert.equal(resumable([shared], { ...parked, paths: [] }).length, 1);
});
