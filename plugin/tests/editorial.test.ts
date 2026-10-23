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

test("detects Galician prose and leaves Spanish or code-only notes alone", async () => {
  const { looksGalician } = await import("../src/editorial");
  const galician = "Aínda que as clases de redes permiten dispoñer de redes de tamaños diferentes, esta clasificación non permite establecer o número de equipos. Se a rede medra e precisamos máis direccións, é posible que teñamos que cambiar todas as direccións dunha vez. Tamén hai que pensar nos encamiñadores e nunha xerarquía de tres niveis.";
  const spanish = "Aunque las clases de redes permiten disponer de redes de tamaños diferentes, esta clasificación no permite establecer el número de equipos. Si la red crece y necesitamos más direcciones, es posible que tengamos que cambiar todas las direcciones de una vez. También hay que pensar en los encaminadores y en una jerarquía de tres niveles.";
  assert.equal(looksGalician([galician]), true);
  assert.equal(looksGalician([spanish]), false);
  assert.equal(looksGalician([spanish, galician.slice(0, 80)]), false);
  assert.equal(looksGalician(["---\ntags: []\n---\n```sh\nip a\n```"]), false);
});
