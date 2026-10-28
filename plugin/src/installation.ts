import { promises as fs } from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { hash } from "./core";

const FILES = ["main.js", "styles.css", "manifest.json"];
const RESTORE = ["styles.css", "manifest.json", "main.js"];
const folder = (directory: string) => path.join(directory, ".prelo-update");
const journal = (directory: string) => path.join(folder(directory), "pending.json");

async function atomicWrite(filename: string, data: Uint8Array) {
  const temporary = filename + "." + randomUUID() + ".partial";
  try {
    const file = await fs.open(temporary, "wx", 0o600);
    try { await file.writeFile(data); await file.sync(); } finally { await file.close(); }
    await fs.rename(temporary, filename);
  } finally { await fs.rm(temporary, { force: true }); }
}

export type UpdateTransaction = { rollback(): Promise<void>; commit(): Promise<void> };

// On startup, recover a torn replacement; a complete new set may load normally.
export async function recoverPluginUpdate(directory: string): Promise<boolean> {
  let expected: Record<string, string>;
  try { expected = JSON.parse(await fs.readFile(journal(directory), "utf8")); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return false; throw error; }
  let complete = true;
  for (const name of FILES) {
    try { if (hash(await fs.readFile(path.join(directory, name))) !== expected[name]) complete = false; }
    catch { complete = false; }
  }
  if (!complete || expected._phase === "rollback") {
    // Read every backup before changing anything, so a missing backup cannot cause partial recovery.
    const previous = await Promise.all(RESTORE.map(name => expected["_absent:" + name] === "true" ? null : fs.readFile(path.join(folder(directory), name))));
    await atomicWrite(journal(directory), Buffer.from(JSON.stringify({ ...expected, _phase: "rollback" })));
    for (let i = 0; i < RESTORE.length; i++) {
      const filename = path.join(directory, RESTORE[i]);
      if (previous[i] === null) await fs.rm(filename, { force: true });
      else await atomicWrite(filename, previous[i]!);
    }
    await fs.rm(journal(directory), { force: true });
    return true;
  }
  // Files matching the download are not proof that activation succeeded.
  // Keep the recovery signal until the caller confirms activation.
  return false;
}

export async function installPluginFiles(directory: string, files: Record<string, ArrayBuffer>,
  replace: (filename: string, data: Uint8Array) => Promise<void> = atomicWrite): Promise<UpdateTransaction> {
  await recoverPluginUpdate(directory);
  // A new explicit update adopts the current complete set as its baseline.
  await fs.rm(journal(directory), { force: true });
  const previous = await Promise.all(FILES.map(name => fs.readFile(path.join(directory, name))));
  const incoming = FILES.map(name => {
    if (!files[name]) throw new Error("Falta un archivo de la actualización.");
    return new Uint8Array(files[name]);
  });
  await fs.mkdir(folder(directory), { recursive: true, mode: 0o700 });
  for (let i = 0; i < FILES.length; i++) await atomicWrite(path.join(folder(directory), FILES[i]), previous[i]);
  const expected = Object.fromEntries(FILES.map((n, i) => [n, hash(incoming[i])]));
  await atomicWrite(journal(directory), Buffer.from(JSON.stringify(expected)));
  const transaction = {
    async rollback() {
      await atomicWrite(journal(directory), Buffer.from(JSON.stringify({ ...expected, _phase: "rollback" })));
      for (const name of RESTORE) await atomicWrite(path.join(directory, name), previous[FILES.indexOf(name)]);
      await fs.rm(journal(directory), { force: true });
    },
    async commit() { await fs.rm(journal(directory), { force: true }); },
  };
  try {
    for (let i = 0; i < FILES.length; i++) await replace(path.join(directory, FILES[i]), incoming[i]);
    return transaction;
  } catch (error) {
    await transaction.rollback();
    throw error;
  }
}
