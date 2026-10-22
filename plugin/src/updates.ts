export const RELEASES_URL = "https://github.com/samuhlo/prelo-ob/releases";
export const RELEASES_API = "https://api.github.com/repos/samuhlo/prelo-ob/releases?per_page=100";
export const UPDATE_INTERVAL = 6 * 60 * 60 * 1000;
export type ReleaseUpdate = { version: string; url: string; beta: boolean };

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
    const assets = new Set(release.assets.filter((a: { state?: string }) => a?.state === "uploaded").map((a: { name: string }) => a.name));
    if (!["main.js", "manifest.json", "styles.css"].every(name => assets.has(name))) continue;
    if (compareVersions(version, installed) !== 1 || newest && compareVersions(version, newest.version) !== 1) continue;
    newest = { version, beta: release.prerelease === true, url: `${RELEASES_URL}/tag/${encodeURIComponent(release.tag_name)}` };
  }
  return newest;
}
