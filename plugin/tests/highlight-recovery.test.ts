import test from "node:test";
import assert from "node:assert/strict";
import { buildSync } from "esbuild";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { readFileSync, promises as fs } from "node:fs";
import path from "node:path";
import os from "node:os";
import vm from "node:vm";
import initSqlJs from "sql.js";
const code = buildSync({
  absWorkingDir: fileURLToPath(new URL("..", import.meta.url)), entryPoints: ["src/main.ts"],
  bundle: true, write: false, platform: "node", format: "cjs", external: ["obsidian", "electron", "sql.js"],
  loader: { ".svg": "text", ".wasm": "binary" },
}).outputFiles[0].text;
const require = createRequire(import.meta.url);

test("manual import retains quote ownership when its publication manifest recovers", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "prelo-synthetic-reader-"));
  try {
    const SQL = await initSqlJs();
    const db = new SQL.Database();
    db.run("CREATE TABLE Bookmark (BookmarkID TEXT, VolumeID TEXT, ContentID TEXT, Text TEXT, Annotation TEXT, Hidden TEXT)");
    db.run("CREATE TABLE content (ContentID TEXT, ContentType INTEGER, Title TEXT, Attribution TEXT)");
    db.run("INSERT INTO content VALUES ('book',6,'Book','')");
    db.run("INSERT INTO Bookmark VALUES ('a','book','','Quote','',0)");
    await fs.mkdir(path.join(directory, ".kobo"));
    await fs.writeFile(path.join(directory, ".kobo/KoboReader.sqlite"), db.export());
    db.close();
    class TFile { constructor(public path: string, public content: string) {} }
    class FileSystemAdapter {}
    const stub = { TFile, FileSystemAdapter, Plugin: class {}, PluginSettingTab: class {}, ItemView: class {}, Modal: class {}, Notice: class {} };
    const context = { module: { exports: {} as any }, Buffer, structuredClone,
      require: (name: string) => name === "obsidian" ? stub : name.endsWith(".wasm") ? new Uint8Array(readFileSync(require.resolve(name))) : require(name) };
    vm.runInNewContext(code, context);
    const plugin = new context.module.exports.default();
    const notes: TFile[] = [];
    plugin.state = { settings: { koboPath: directory, highlightsFolder: "Quotes", frontmatter: "" }, sources: {}, importNotes: {} };
    plugin.app = { vault: {
      adapter: new FileSystemAdapter(), getMarkdownFiles: () => notes,
      getAbstractFileByPath: (name: string) => notes.find(n => n.path === name),
      cachedRead: async (file: TFile) => file.content,
      create: async (name: string, content: string) => { const file = new TFile(name, content); notes.push(file); return file; },
      process: async (file: TFile, update: (text: string) => string) => { file.content = update(file.content); },
    }, metadataCache: { getFileCache: (file: TFile) => ({ frontmatter: { margen_lectura: JSON.parse(/^margen_lectura: (.*)$/m.exec(file.content)![1]) } }) } };
    plugin.ensureFolder = async () => {};
    plugin.verifyKobo = async () => {};
    plugin.saveData = async () => {};
    plugin.findSource = async () => null;
    const quote = { key: "a".repeat(64), volume_id: "book", text: "Quote", annotation: "", match: "book", title: "Book", author: "", created_at: "", source: null as any };
    plugin.api = async () => ({ json: { highlights: [quote] } });
    await plugin.importUsb();
    notes[0].content += "\nPersonal comment.\n";
    quote.source = { id: "source", path: "source.md", title: "Source", sha256: "b".repeat(64) };
    quote.match = "chapter";
    await plugin.importUsb();
    assert.equal(notes.length, 1);
    assert.equal(notes[0].content.split("<!-- margen:").length - 1, 1);
    quote.annotation = "Updated annotation";
    await plugin.importUsb();
    assert.equal(notes.length, 1);
    assert.match(notes[0].content, /Personal comment/);
    assert.match(notes[0].content, /Updated annotation/);
  } finally { await fs.rm(directory, { recursive: true, force: true }); }
});
