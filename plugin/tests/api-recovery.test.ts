import test from "node:test";
import assert from "node:assert/strict";
import { buildSync } from "esbuild";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
const code = buildSync({
  absWorkingDir: fileURLToPath(new URL("..", import.meta.url)),
  entryPoints: ["src/main.ts"], bundle: true, write: false, platform: "node", format: "cjs",
  external: ["obsidian", "electron"], loader: { ".svg": "text", ".wasm": "binary" },
}).outputFiles[0].text;
const require = createRequire(import.meta.url);
function subject(requestUrl: (request: { url: string; method: string }) => Promise<unknown>) {
  const notices: string[] = [];
  const stub = { Plugin: class {}, PluginSettingTab: class {}, ItemView: class {}, Modal: class {},
    Notice: class { constructor(message: string) { notices.push(message); } }, requestUrl };
  const context = { module: { exports: {} as any }, Buffer, structuredClone, URL, ArrayBuffer,
    require: (name: string) => name === "obsidian" ? stub : require(name) };
  vm.runInNewContext(code, context);
  const plugin = new context.module.exports.default();
  plugin.state = { activeJob: "missing", settings: { serverUrl: "http://localhost:8765", token: "x".repeat(24) }, composer: { paths: ["a.md"] } };
  plugin.app = { workspace: { getLeavesOfType: () => [] } };
  let saved: any;
  plugin.saveData = async (value: unknown) => { saved = structuredClone(value); };
  return { plugin, notices, saved: () => saved };
}
for (const action of ["recover", "cancel"]) test(`confirmed absent job is released on ${action}`, async () => {
  const { plugin, notices, saved } = subject(async ({ url, method }) => {
    if (url.includes("missing")) return { status: 404, json: { detail: "Trabajo no encontrado." } };
    if (method === "POST") return { status: 202, json: { state: "queued" } };
    if (url.includes("/v1/jobs/")) return { status: 200, json: { state: "complete", message: "Done", publication_id: "result" } };
    return { status: 200, json: { id: "result" } };
  });
  if (action === "recover") await assert.rejects(plugin.awaitPublication("missing", () => {}), /Trabajo no encontrado/);
  else await plugin.cancelJob();
  assert.equal(plugin.state.activeJob, undefined);
  assert.equal(saved().activeJob, undefined);
  assert.ok(notices.every(n => !n.startsWith("Cancelando")));
  await assert.doesNotReject(plugin.createPublication({}, () => {}));
});
for (const status of [401, 500, 503]) test(`HTTP ${status} preserves the recoverable job`, async () => {
  const { plugin } = subject(async () => ({ status, json: { detail: "Temporary error" } }));
  await assert.rejects(plugin.awaitPublication("missing", () => {}));
  await plugin.cancelJob();
  assert.equal(plugin.state.activeJob, "missing");
});
test("lost submission and lookup responses preserve the new job identifier", async () => {
  const { plugin } = subject(async () => { throw new Error("Synthetic network outage"); });
  plugin.state.activeJob = undefined;
  await assert.rejects(plugin.createPublication({}, () => {}));
  assert.ok(plugin.state.activeJob);
});
for (const folder of ["", "../outside"]) test(`library API does not require export folder ${JSON.stringify(folder)}`, async () => {
  let calls = 0;
  const { plugin } = subject(async () => { calls++; return { status: 200, json: {} }; });
  plugin.state.settings.outputFolder = folder;
  await plugin.api("/v1/library");
  assert.equal(calls, 1);
  await assert.rejects(plugin.ensureFolder(folder));
});
