import test from "node:test";
import assert from "node:assert/strict";
import { needsEditorialAI, writingModes, studyAids, WritingMode, StudyAids } from "../src/editorial";

test("rewriting and study aids require AI for either magazine style, even with organization disabled", () => {
  for (const style of ["study", "retro90"]) {
    for (const writingMode of Object.keys(writingModes) as WritingMode[]) {
      for (const aids of Object.keys(studyAids) as StudyAids[]) {
        assert.equal(needsEditorialAI({ style, writingMode, studyAids: aids, useAI: false }),
          style === "retro90" || writingMode !== "original" || aids !== "none");
      }
    }
  }
  assert.equal(needsEditorialAI({ style: "study", writingMode: "original", studyAids: "none", useAI: true }), true);
});


test("extra instructions enable AI even for unchanged notes; blank instructions do not", () => {
  const original = { style: "study", useAI: false, writingMode: "original" as const, studyAids: "none" as const };
  assert.equal(needsEditorialAI({ ...original, intent: "Después de cada tema, su examen." }), true);
  assert.equal(needsEditorialAI({ ...original, intent: "   " }), false);
});
