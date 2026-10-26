import test from "node:test";
import assert from "node:assert/strict";
import { bookStatus, commandLabel, KoboBook, KoboOverview, visibleBooks } from "../src/reader";

const book = (extra: Partial<KoboBook>): KoboBook => ({ id: "file:///mnt/onboard/a.epub", path: "a.epub", edition: "", title: "A", author: "",
  percent: 0, last_read: "", status: "", present: true, highlights: 0, ...extra });
const overview = (commands: KoboOverview["commands"] = []): KoboOverview => ({ at: "2026-10-26T10:00:00", books: [], commands });

test("a book shows its reading progress until a removal is requested or carried out", () => {
  assert.deepEqual(bookStatus(book({ percent: 40 }), overview()), { text: "40 % leído", removable: true });
  assert.equal(bookStatus(book({}), overview()).text, "Sin abrir");
  const removal = { id: "1", kind: "remove" as const, path: "a.epub", title: "A", created_at: "2026-10-26T11:00:00" };
  assert.equal(bookStatus(book({}), overview([{ ...removal, state: "pending" }])).removable, false);
  assert.match(bookStatus(book({}), overview([{ ...removal, state: "done", done_at: "2026-10-26T11:05:00" }])).text, /desaparecerá/);
  // A removal older than the inventory means the book came back (sent again).
  assert.equal(bookStatus(book({}), overview([{ ...removal, state: "done", done_at: "2026-10-25T09:00:00" }])).removable, true);
  assert.equal(bookStatus(book({ path: "" }), overview()).removable, false);
});

test("books filter by origin and words, recently read first", () => {
  const books = [book({ title: "Docker", edition: "e1" }), book({ title: "Dune", author: "Frank Herbert", last_read: "2026-10-20" }), book({ title: "Ansible", last_read: "2026-10-25" })];
  assert.deepEqual(visibleBooks(books, "", "all").map(b => b.title), ["Ansible", "Dune", "Docker"]);
  assert.deepEqual(visibleBooks(books, "", "prelo").map(b => b.title), ["Docker"]);
  assert.deepEqual(visibleBooks(books, "herbert", "other").map(b => b.title), ["Dune"]);
  assert.match(commandLabel({ id: "2", kind: "upload", path: "x.epub", title: "x", state: "failed", message: "Ya existe", created_at: "" }), /no se pudo: Ya existe/);
});
