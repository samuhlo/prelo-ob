import initSqlJs from "sql.js";
import wasm from "sql.js/dist/sql-wasm.wasm";

// Obsidian and BRAT install three files. Keep SQLite inside main.js so imports
// also work without a separately downloaded WASM file or a network request.
export async function openKoboDatabase(bytes: Uint8Array) {
  const SQL = await initSqlJs({ wasmBinary: new Uint8Array(wasm).buffer });
  return new SQL.Database(bytes);
}
