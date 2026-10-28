import test from "node:test";
import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { installPluginFiles, recoverPluginUpdate } from "../src/installation";
import { hash } from "../src/core";
const names = ["main.js", "styles.css", "manifest.json"];
const files = Object.fromEntries(names.map(name => [name, new TextEncoder().encode("new:" + name).buffer]));
async function fixture(action: (directory: string) => Promise<void>) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "prelo-update-test-"));
  try {
    for (const name of names) await fs.writeFile(path.join(directory, name), "old:" + name);
    await fs.writeFile(path.join(directory, "data.json"), '{"composer":"keep"}');
    await action(directory);
    assert.equal(await fs.readFile(path.join(directory, "data.json"), "utf8"), '{"composer":"keep"}');
  } finally { await fs.rm(directory, { recursive: true, force: true }); }
}
for (const failure of [1, 2, 3]) test(`write failure ${failure} restores every plugin file`, async () => fixture(async directory => {
  let writes = 0;
  await assert.rejects(installPluginFiles(directory, files, async (filename, data) => {
    if (++writes === failure) throw new Error("Synthetic write failure");
    await fs.writeFile(filename, data);
  }));
  for (const name of names) assert.equal(await fs.readFile(path.join(directory, name), "utf8"), "old:" + name);
}));
test("a failed activation can roll back a complete replacement", async () => fixture(async directory => {
  const tx = await installPluginFiles(directory, files);
  assert.equal(await fs.readFile(path.join(directory, "main.js"), "utf8"), "new:main.js");
  await tx.rollback();
  for (const name of names) assert.equal(await fs.readFile(path.join(directory, name), "utf8"), "old:" + name);
}));
test("startup restores a replacement interrupted between files", async () => fixture(async directory => {
  const backup = path.join(directory, ".prelo-update"); await fs.mkdir(backup);
  for (const name of names) await fs.copyFile(path.join(directory, name), path.join(backup, name));
  await fs.writeFile(path.join(backup, "pending.json"), JSON.stringify(Object.fromEntries(names.map(name => [name, hash(new Uint8Array(files[name]))]))));
  await fs.writeFile(path.join(directory, "main.js"), new Uint8Array(files["main.js"]));
  assert.equal(await recoverPluginUpdate(directory), true);
  for (const name of names) assert.equal(await fs.readFile(path.join(directory, name), "utf8"), "old:" + name);
  assert.equal(await recoverPluginUpdate(directory), false);
}));
test("a complete installation survives startup and can be committed", async () => fixture(async directory => {
  const tx = await installPluginFiles(directory, files);
  assert.equal(await recoverPluginUpdate(directory), false);
  await tx.commit();
  for (const name of names) assert.equal(await fs.readFile(path.join(directory, name), "utf8"), "new:" + name);
}));

test("failed activation keeps its journal when rollback is interrupted, including the entry file", async () => fixture(async directory => {
  const tx = await installPluginFiles(directory, files);
  assert.equal(await recoverPluginUpdate(directory), false);
  const rename = fs.rename;
  fs.rename = async (source, target) => {
    if (target === path.join(directory, "styles.css")) throw new Error("Synthetic rollback interruption");
    return rename(source, target);
  };
  try { await assert.rejects(tx.rollback(), /rollback interruption/); }
  finally { fs.rename = rename; }
  assert.equal(await fs.readFile(path.join(directory, "main.js"), "utf8"), "new:main.js",
    "Keep the recovery-capable entry until the other files are restored");
  assert.equal(await recoverPluginUpdate(directory), true);
  for (const name of names) assert.equal(await fs.readFile(path.join(directory, name), "utf8"), "old:" + name);
}));
