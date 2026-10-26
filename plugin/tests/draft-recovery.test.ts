import test from "node:test";
import assert from "node:assert/strict";
import { buildSync } from "esbuild";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { composerFromDraft, draftFromComposer, emptyComposer, resumable } from "../src/session";
import type { Composer } from "../src/studio";
import type { Draft } from "../src/main";

// Exercise the real plugin's persistence and asynchronous methods with a synthetic vault.
const code = buildSync({
  absWorkingDir: fileURLToPath(new URL("..", import.meta.url)),
  entryPoints: ["src/main.ts"], bundle: true, write: false, platform: "node", format: "cjs",
  external: ["obsidian", "electron"], loader: { ".svg": "text", ".wasm": "binary" },
}).outputFiles[0].text;
const require = createRequire(import.meta.url);
type Saved = { composer: Composer; parked?: Composer; parkedDrafts?: Composer[] };
type Subject = {
  state: Saved; app: unknown;
  saveData: (value: Saved) => Promise<void>;
  api: (route: string, body?: Draft) => Promise<unknown>;
  parkComposer: (announce?: boolean) => Promise<void>;
  shareParked: () => Promise<void>;
  resumeComposer: (composer: Composer) => void;
  removeParkedDraft: (id: string) => void;
  save: () => Promise<void>;
};
function subject(saved: Saved = { composer: emptyComposer() }) {
  const stub = { Plugin: class {}, PluginSettingTab: class {}, ItemView: class {}, Modal: class {}, Notice: class {} };
  const context = { module: { exports: {} as { default: new () => Subject } }, Buffer, structuredClone,
    require: (name: string) => name === "obsidian" ? stub : require(name) };
  vm.runInNewContext(code, context);
  const plugin = new context.module.exports.default();
  plugin.state = structuredClone(saved);
  plugin.app = { workspace: { getLeavesOfType: () => [] } };
  let persisted = structuredClone(saved);
  plugin.saveData = async value => { persisted = structuredClone(value); };
  plugin.api = async () => { throw new Error("Synthetic offline server"); };
  return { plugin, saved: () => persisted };
}
const selection = (title: string, draftId?: string): Composer => ({
  ...emptyComposer(), active: true, title, paths: [`${title}.md`], draftId,
});
const localDrafts = (plugin: Subject) => resumable([], plugin.state.parked, plugin.state.parkedDrafts);

test("several offline selections survive a reload with their identities and settings", { timeout: 2000 }, async () => {
  const first = subject();
  first.plugin.state.composer = { ...selection("A"), language: "gl", writingMode: "narrative", preserveOrder: true };
  await first.plugin.parkComposer(false);
  const a = localDrafts(first.plugin)[0].draft;
  first.plugin.state.composer = selection("B");
  await first.plugin.parkComposer(false);
  const restored = subject(first.saved());
  restored.plugin.state.composer = selection("C");
  await restored.plugin.parkComposer(false);
  const drafts = localDrafts(restored.plugin).map(r => r.draft);
  assert.deepEqual(drafts.map(d => d.title), ["C", "B", "A"]);
  assert.deepEqual(drafts.find(d => d.id === a.id), a);
});

test("an existing single parked draft remains recoverable when another is parked", { timeout: 2000 }, async () => {
  const { plugin } = subject({ composer: selection("New"), parked: selection("Legacy", "legacy-id") });
  await plugin.parkComposer(false);
  assert.deepEqual(localDrafts(plugin).map(r => r.draft.title), ["New", "Legacy"]);
  plugin.resumeComposer(composerFromDraft(localDrafts(plugin)[1].draft));
  assert.equal(plugin.state.composer.draftId, "legacy-id");
  assert.deepEqual(localDrafts(plugin).map(r => r.draft.title), ["New"]);
});

test("discarding a local draft leaves the other selections recoverable after reload", { timeout: 2000 }, async () => {
  const { plugin, saved } = subject();
  for (const name of ["A", "B", "C"]) {
    plugin.state.composer = selection(name);
    await plugin.parkComposer(false);
  }
  const b = localDrafts(plugin).find(r => r.draft.title === "B")!;
  plugin.removeParkedDraft(b.draft.id);
  await plugin.save();
  assert.deepEqual(localDrafts(subject(saved()).plugin).map(r => r.draft.title), ["C", "A"]);
});

test("partial sharing only removes drafts acknowledged by the server", { timeout: 2000 }, async () => {
  const { plugin, saved } = subject();
  for (const name of ["A", "B", "C"]) {
    plugin.state.composer = selection(name);
    await plugin.parkComposer(false);
  }
  const received: string[] = [];
  plugin.api = async (_route, body) => {
    if (received.length) throw new Error("Connection lost");
    received.push(body!.title);
  };
  await assert.rejects(plugin.shareParked());
  assert.deepEqual(received, ["C"]);
  assert.deepEqual(localDrafts(subject(saved()).plugin).map(r => r.draft.title), ["B", "A"]);
  plugin.api = async (_route, body) => { received.push(body!.title); };
  await plugin.shareParked();
  assert.deepEqual(received, ["C", "B", "A"]);
  assert.equal(localDrafts(plugin).length, 0);
});

test("a late acknowledgement cannot erase a newer revision of the same draft", { timeout: 2000 }, async () => {
  const { plugin } = subject({ composer: selection("Old", "same-id") });
  await plugin.parkComposer(false);
  let acknowledge!: () => void;
  let submitted!: () => void;
  const started = new Promise<void>(resolve => { submitted = resolve; });
  plugin.api = async () => { submitted(); await new Promise<void>(resolve => { acknowledge = resolve; }); };
  const sharing = plugin.shareParked();
  await started;
  plugin.resumeComposer(composerFromDraft(localDrafts(plugin)[0].draft));
  plugin.state.composer = { ...plugin.state.composer, title: "Revised" };
  const parking = plugin.parkComposer(false);
  // parkComposer persists the new revision before waiting on the in-flight share.
  assert.equal(localDrafts(plugin)[0].draft.title, "Revised");
  acknowledge();
  await Promise.all([sharing, parking]);
  assert.equal(localDrafts(plugin)[0].draft.title, "Revised");
  const remoteOld = draftFromComposer(selection("Old"), "same-id");
  assert.equal(resumable([remoteOld], plugin.state.parked, plugin.state.parkedDrafts)[0].draft.title, "Revised");
});

test("simultaneous refreshes share a pending draft once", { timeout: 2000 }, async () => {
  const { plugin } = subject({ composer: selection("A") });
  await plugin.parkComposer(false);
  let calls = 0;
  let acknowledge!: () => void;
  plugin.api = async () => { calls++; await new Promise<void>(resolve => { acknowledge = resolve; }); };
  const first = plugin.shareParked();
  const second = plugin.shareParked();
  acknowledge();
  await Promise.all([first, second]);
  assert.equal(calls, 1);
  assert.equal(localDrafts(plugin).length, 0);
});
