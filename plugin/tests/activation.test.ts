import test from 'node:test';
import assert from 'node:assert/strict';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(new URL('../package.json', import.meta.url));
const { buildSync } = require('esbuild');
const root = fileURLToPath(new URL('../..', import.meta.url));
const compile = (entry: string) => buildSync({ absWorkingDir: path.join(root, 'plugin'), entryPoints: [entry],
  bundle: true, write: false, platform: 'node', format: 'cjs', external: ['obsidian', 'electron'],
  loader: { '.svg': 'text', '.wasm': 'binary' } }).outputFiles[0].text;
const installation = { exports: {} as any };
vm.runInNewContext(compile('src/installation.ts'), { module: installation, require, Buffer });
const { installPluginFiles, recoverPluginUpdate } = installation.exports;
const names = ['main.js', 'styles.css', 'manifest.json'];
const bytes = (text: string) => new TextEncoder().encode(text).buffer;
const incoming = Object.fromEntries(names.map(name => [name, bytes('new:' + name)]));
async function fixture(action: (directory: string) => Promise<void>) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'prelo-review-'));
  try {
    for (const name of names) await fs.writeFile(path.join(directory, name), 'old:' + name);
    await action(directory);
  } finally { await fs.rm(directory, { recursive: true, force: true }); }
}

test('failed activation followed by a failed rollback still recovers at startup', async () => fixture(async directory => {
  class FileSystemAdapter { getBasePath() { return directory; } }
  const obsidian = { Plugin: class {}, PluginSettingTab: class {}, ItemView: class {}, Modal: class {}, Notice: class {}, FileSystemAdapter };
  const bundled = { exports: {} as any };
  vm.runInNewContext(compile('src/main.ts'), { module: bundled, Buffer, structuredClone,
    require: (name: string) => name === 'obsidian' ? obsidian : require(name) });
  const Prelo = bundled.exports.default;
  const tx = await installPluginFiles(directory, incoming);
  const app = { vault: { adapter: new FileSystemAdapter(), configDir: '.obsidian' }, workspace: { layoutReady: true }, plugins: {
    disablePlugin: async () => {}, loadManifests: async () => {},
    enablePlugin: async () => {
      const next = new Prelo();
      next.app = app;
      next.manifest = { id: 'margen', dir: '.' };
      next.loadData = async () => { throw new Error('Synthetic activation failure'); };
      await next.onload();
      return true;
    },
  } };
  const current = new Prelo();
  current.app = app;
  current.manifest = { id: 'margen', dir: '.' };
  const rename = fs.rename;
  fs.rename = async (from, to) => {
    if (to === path.join(directory, 'styles.css') && await fs.readFile(from, 'utf8') === 'old:styles.css')
      throw Object.assign(new Error('Synthetic rollback write failure'), { code: 'EIO' });
    return rename(from, to);
  };
  try { await assert.rejects(current.reloadAfterUpdate('2.0.0', tx), /Synthetic rollback write failure/); }
  finally { fs.rename = rename; }
  await recoverPluginUpdate(directory);
  for (const name of names)
    assert.equal(await fs.readFile(path.join(directory, name), 'utf8'), 'old:' + name, 'startup must finish the interrupted rollback');
}));
