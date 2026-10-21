import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createRequire } from 'node:module';
import { build } from 'esbuild';

test('bundled SQLite opens and reads a synthetic Kobo database without a sidecar WASM file', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'prelo-distribution-'));
  try {
    const file = join(dir, 'sqlite.cjs');
    await build({ entryPoints: ['src/sqlite.ts'], outfile: file, bundle: true, platform: 'node',
      format: 'cjs', loader: { '.wasm': 'binary' } });
    const { openKoboDatabase } = createRequire(import.meta.url)(file);
    const db = await openKoboDatabase(new Uint8Array());
    db.run('CREATE TABLE Bookmark (BookmarkID TEXT, Text TEXT)');
    db.run('INSERT INTO Bookmark VALUES (?, ?)', ['synthetic', 'Una lectura para llevar.']);
    const bytes = db.export(); db.close();
    const restored = await openKoboDatabase(bytes);
    assert.equal(restored.exec('SELECT Text FROM Bookmark')[0].values[0][0], 'Una lectura para llevar.');
    restored.close();
  } finally { await rm(dir, { recursive: true, force: true }); }
});
