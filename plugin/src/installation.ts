import { promises as fs } from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { hash } from "./core";

const FILES = ["main.js", "styles.css", "manifest.json"];
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
  if (!complete) {
    // Read every backup before changing anything, so a missing backup cannot cause partial recovery.
    const previous = await Promise.all(FILES.map(name => fs.readFile(path.join(folder(directory), name))));
    for (let i = 0; i < FILES.length; i++) await atomicWrite(path.join(directory, FILES[i]), previous[i]);
  }
  await fs.rm(journal(directory), { force: true });
  return !complete;
}

export async function installPluginFiles(directory: string, files: Record<string, ArrayBuffer>,
  replace: (filename: string, data: Uint8Array) => Promise<void> = atomicWrite): Promise<UpdateTransaction> {
  await recoverPluginUpdate(directory);
  const previous = await Promise.all(FILES.map(name => fs.readFile(path.join(directory, name))));
  const incoming = FILES.map(name => {
    if (!files[name]) throw new Error("Falta un archivo de la actualización.");
    return new Uint8Array(files[name]);
  });
  await fs.mkdir(folder(directory), { recursive: true, mode: 0o700 });
  for (let i = 0; i < FILES.length; i++) await atomicWrite(path.join(folder(directory), FILES[i]), previous[i]);
  await atomicWrite(journal(directory), Buffer.from(JSON.stringify(Object.fromEntries(FILES.map((n, i) => [n, hash(incoming[i])])))));
  const transaction = {
    async rollback() {
      for (let i = 0; i < FILES.length; i++) await atomicWrite(path.join(directory, FILES[i]), previous[i]);
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
