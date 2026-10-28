import { safeRelative } from "./core";
export type Connection = { serverUrl: string; token: string; outputFolder?: string; highlightsFolder?: string };
export function validateConnection(value: unknown): Connection {
  if (typeof value !== "object" || value === null) throw new Error("Archivo de conexión no válido.");
  const v = value as Record<string, unknown>;
  if (typeof v.serverUrl !== "string" || typeof v.token !== "string" || v.token.length < 24 || /[\r\n]/.test(v.token))
    throw new Error("La conexión necesita una dirección y una credencial válida.");
  const url = new URL(v.serverUrl);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash)
    throw new Error("Dirección no válida.");
  if (url.protocol === "http:" && !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname))
    throw new Error("La conexión a otro equipo necesita HTTPS.");
  const result: Connection = { serverUrl: url.toString().replace(/\/$/, ""), token: v.token };
  for (const key of ["outputFolder", "highlightsFolder"] as const)
    if (key in v) {
      if (typeof v[key] !== "string") throw new Error("Carpeta de conexión no válida.");
      result[key] = safeRelative(v[key]);
    }
  return result;
}
