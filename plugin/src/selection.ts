export const MAX_NOTES = 100;

export function addPaths(current: string[], incoming: string[]): string[] {
  const result = [...new Set([...current, ...incoming])];
  if (result.length > MAX_NOTES)
    throw new Error(`Puedes reunir hasta ${MAX_NOTES} notas por revista. Selecciona menos notas.`);
  return result;
}

export function movePath(paths: string[], source: string, target: string): string[] {
  const result = [...paths];
  const from = result.indexOf(source), to = result.indexOf(target);
  if (from < 0 || to < 0 || from === to) return result;
  result.splice(from, 1);
  result.splice(to, 0, source);
  return result;
}

export function renamePaths(paths: string[], oldPath: string, newPath: string): string[] {
  return [...new Set(paths.map(path => path === oldPath || path.startsWith(oldPath + "/")
    ? newPath + path.slice(oldPath.length) : path))];
}

export function matchesSearch(title: string, path: string, query: string): boolean {
  const clean = (text: string) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
  const haystack = clean(`${title} ${path}`);
  return clean(query).trim().split(/\s+/).every(word => haystack.includes(word));
}
