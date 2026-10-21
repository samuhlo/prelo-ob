import test from "node:test";
import assert from "node:assert/strict";
import initSqlJs from "sql.js";
import { appendHighlight, readHighlights, ResolvedHighlight, safeRelative, highlightFilename, readerDate, modernizeHighlightDates } from "../src/core";

test("Kobo database: annotations and metadata, without altering the source database", async () => {
  const SQL = await initSqlJs();
  const db = new SQL.Database();
  db.run("CREATE TABLE Bookmark (BookmarkID TEXT, VolumeID TEXT, ContentID TEXT, Text TEXT, Annotation TEXT, Hidden TEXT, Color TEXT)");
  db.run("CREATE TABLE content (ContentID TEXT, ContentType INTEGER, Title TEXT, Attribution TEXT)");
  db.run("INSERT INTO content VALUES ('book',6,'Una novela','Su autora')");
  db.run("INSERT INTO Bookmark VALUES ('a','book','chapter','Texto','Comentario',0,'yellow')");
  db.run("INSERT INTO Bookmark VALUES ('b','book','chapter','Borrado','',1,'')");
  db.run("INSERT INTO Bookmark VALUES ('c','book','chapter','','Solo anotación',0,'')");
  db.run("INSERT INTO Bookmark VALUES ('d','book','chapter','Oculto','', 'true','')");
  const before = Buffer.from(db.export());
  const rows = readHighlights(db);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].author, "Su autora");
  assert.equal(rows[0].color, "yellow");
  assert.equal(rows[1].annotation, "Solo anotación");
  assert.deepEqual(Buffer.from(db.export()), before);
  db.close();
});

const highlight: ResolvedHighlight = {
  id: "a", key: "f".repeat(64), volume_id: "book", content_id: "", start_path: "",
  text: "Una idea\ncon dos líneas.", annotation: "Estudiar esto", title: "Apuntes",
  author: "", created_at: "2026-10-20", color: "", match: "chapter",
  publication_id: "edition", publication_title: "Cuaderno",
  source: { id: "source-a", path: "Docker.md", title: "Docker", sha256: "" },
};
test("Repeated imports are idempotent; updates preserve personal comments and previous highlights", () => {
  const initial = "# Subrayados\n\nMi reflexión personal.\n";
  const first = appendHighlight(initial, highlight, "clases/Docker.md");
  assert.equal(appendHighlight(first, highlight, "clases/Docker.md"), first);
  assert.ok(first.includes("[[clases/Docker]]"));
  const revised = appendHighlight(first, { ...highlight, annotation: "Nuevo comentario" }, "clases/Docker.md");
  assert.ok(revised.includes("Mi reflexión personal."));
  assert.ok(revised.includes("Estudiar esto"));
  assert.ok(revised.includes("Nuevo comentario"));
  assert.ok(revised.includes("Actualización del subrayado"));
});
test("Import folders cannot escape the vault or write hidden configuration", () => {
  for (const path of ["../other", "/tmp", ".obsidian", "A/../../B", "C:\\Users\\X", "A//B"])
    assert.throws(() => safeRelative(path));
  assert.equal(safeRelative("02_Cerebro/Media & Consumo"), "02_Cerebro/Media & Consumo");
});

test("Reading filenames are descriptive and cannot contain paths", () => {
  assert.equal(highlightFilename("¿Está usted de broma Sr. Feynman?"), "subrayados-esta-usted-de-broma-sr-feynman.md");
  assert.equal(highlightFilename("12 reglas para vivir"), "subrayados-12-reglas-para-vivir.md");
  assert.equal(highlightFilename("../Docker / redes"), "subrayados-docker-redes.md");
});

test("Reader dates keep their original calendar day and reject invalid conversions", () => {
  assert.equal(readerDate("2026-10-20T23:59:59-05:00"), "20/10/2026");
  assert.equal(readerDate("2024-02-29"), "29/02/2024");
  assert.equal(readerDate("2025-02-29"), "2025-02-29");
  assert.equal(readerDate("20/10/2026"), "20/10/2026");
});

test("Date migration preserves quotes, personal text and duplicate markers", () => {
  const marker = `<!-- margen:${highlight.key}:123 -->`;
  const original = `# Mis notas\nFecha en el lector: no tocar\n\n${marker}\n\n> Texto\n\nFecha en el lector: 2026-10-20T09:10:00Z\n\n---\n\nMi reflexión.\n`;
  const migrated = modernizeHighlightDates(original);
  assert.ok(migrated.includes("Fecha : 20/10/2026"));
  assert.ok(migrated.includes("Fecha en el lector: no tocar"));
  assert.ok(migrated.includes(marker) && migrated.includes("> Texto") && migrated.includes("Mi reflexión."));
  assert.equal(modernizeHighlightDates(migrated), migrated);
  assert.ok(appendHighlight("# Notas", highlight, null).includes("Fecha : 20/10/2026"));
});
