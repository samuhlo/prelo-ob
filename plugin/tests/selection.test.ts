import assert from "node:assert/strict";
import { test } from "node:test";
import { addPaths, matchesSearch, movePath, noteTitle, renamePaths } from "../src/selection";

test("adding from several entry points preserves order and avoids duplicate notes", () => {
  assert.deepEqual(addPaths(["a.md", "b.md"], ["b.md", "c.md", "a.md"]), ["a.md", "b.md", "c.md"]);
  const current = Array.from({ length: 99 }, (_, i) => `${i}.md`);
  assert.throws(() => addPaths(current, ["new.md", "extra.md"]), /hasta 100/);
  assert.equal(current.length, 99); // Reject the whole operation without losing the existing basket.
});

test("reordering and folder renames preserve every chosen note", () => {
  const original = ["clases/a.md", "clases/b.md", "ideas/c.md"];
  assert.deepEqual(movePath(original, "ideas/c.md", "clases/a.md"), ["ideas/c.md", "clases/a.md", "clases/b.md"]);
  assert.deepEqual(movePath(original, "missing.md", "clases/a.md"), original);
  assert.deepEqual(renamePaths(original, "clases", "estudio"), ["estudio/a.md", "estudio/b.md", "ideas/c.md"]);
  assert.deepEqual(original, ["clases/a.md", "clases/b.md", "ideas/c.md"]);
});

test("search finds the visible title and path without requiring accents", () => {
  assert.equal(matchesSearch("Qué empaqueta Docker", "07_Clases/tema_05.md", "que docker"), true);
  assert.equal(matchesSearch("Imágenes", "07_Clases/tema_05.md", "imagenes clases"), true);
  assert.equal(matchesSearch("Imágenes", "07_Clases/tema_05.md", "imagenes redes"), false);
});

test("a malformed first heading falls back to the file name", () => {
  assert.equal(noteTitle("1.8.3. Que é SSH", "ssh"), "1.8.3. Que é SSH");
  assert.equal(noteTitle("1.8.4. Que é o %=u2IWj6/EI/dozvKuY0BYoK2n71zVT4gxbVTT4mHbkmI51v3R5O", "1.8.4 DNS"), "1.8.4 DNS");
  assert.equal(noteTitle("x".repeat(130), "larga"), "larga");
  assert.equal(noteTitle(undefined, "nota"), "nota");
});
