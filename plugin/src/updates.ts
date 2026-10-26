import { hash } from "./core";

export const RELEASES_URL = "https://github.com/samuhlo/prelo-ob/releases";
export const RELEASES_API = "https://api.github.com/repos/samuhlo/prelo-ob/releases?per_page=100";
export const UPDATE_INTERVAL = 6 * 60 * 60 * 1000;
export const PLUGIN_FILES = ["main.js", "manifest.json", "styles.css"];
const DOWNLOADS = "https://github.com/samuhlo/prelo-ob/releases/download/";
export type ReleaseUpdate = { version: string; url: string; beta: boolean; downloads: Record<string, string> };

// Published tags use numeric major.minor.patch; GitHub marks beta releases separately.
export function compareVersions(a: string, b: string): number | undefined {
  const parse = (value: string) => /^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.exec(value)?.slice(1).map(Number);
  const left = parse(a), right = parse(b);
  if (!left || !right || [...left, ...right].some(n => !Number.isSafeInteger(n))) return undefined;
  for (let i = 0; i < 3; i++) if (left[i] !== right[i]) return left[i] > right[i] ? 1 : -1;
  return 0;
}

export function findUpdate(data: unknown, installed: string): ReleaseUpdate | undefined {
  if (!Array.isArray(data)) throw new Error("Respuesta de versiones no válida.");
  let newest: ReleaseUpdate | undefined;
  for (const release of data) {
    if (!release || release.draft !== false || typeof release.tag_name !== "string" || !Array.isArray(release.assets)) continue;
    const version = release.tag_name.replace(/^v/, "");
    const downloads: Record<string, string> = {};
    for (const asset of release.assets)
      if (asset?.state === "uploaded" && typeof asset.name === "string")
        downloads[asset.name] = typeof asset.browser_download_url === "string" && asset.browser_download_url.startsWith(DOWNLOADS) ? asset.browser_download_url : "";
    if (!PLUGIN_FILES.every(name => name in downloads)) continue;
    if (compareVersions(version, installed) !== 1 || newest && compareVersions(version, newest.version) !== 1) continue;
    newest = { version, beta: release.prerelease === true, downloads, url: `${RELEASES_URL}/tag/${encodeURIComponent(release.tag_name)}` };
  }
  return newest;
}

// In-place installation requires the release checksums: a file that does not match is never written.
export const installable = (update: ReleaseUpdate): boolean =>
  [...PLUGIN_FILES, "SHA256SUMS"].every(name => !!update.downloads[name]);

export function verifyUpdate(files: Record<string, ArrayBuffer>, expected: { id: string; version: string }): { minAppVersion: string } {
  const sums = new Map<string, string>();
  for (const line of new TextDecoder().decode(files.SHA256SUMS).split(/\r?\n/)) {
    const match = /^([0-9a-f]{64})\s+\*?(\S+)$/.exec(line.trim());
    if (match) sums.set(match[2], match[1]);
  }
  for (const name of PLUGIN_FILES)
    if (!files[name] || sums.get(name) !== hash(new Uint8Array(files[name])))
      throw new Error(`La descarga de ${name} no coincide con la release. No se ha cambiado nada.`);
  let manifest: unknown;
  try { manifest = JSON.parse(new TextDecoder().decode(files["manifest.json"])); } catch { manifest = undefined; }
  if (typeof manifest !== "object" || manifest === null) throw new Error("El manifiesto de la release no es válido.");
  const minAppVersion: unknown = Reflect.get(manifest, "minAppVersion");
  if (Reflect.get(manifest, "id") !== expected.id || Reflect.get(manifest, "version") !== expected.version || typeof minAppVersion !== "string")
    throw new Error("La release no corresponde a esta versión de Prelo. No se ha cambiado nada.");
  return { minAppVersion };
}
