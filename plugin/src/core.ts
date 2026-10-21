import { createHash } from "node:crypto";
import type { Database } from "sql.js";

export type Highlight = {
  id: string; volume_id: string; content_id: string; start_path: string;
  text: string; annotation: string; title: string; author: string; created_at: string; color: string;
};
export type ResolvedHighlight = Highlight & {
  key: string; match: string; publication_id: string | null; publication_title: string;
  source: { id: string; path: string; title: string; sha256: string } | null;
};
export const hash = (value: string | Uint8Array) => createHash("sha256").update(value).digest("hex");
export const safeName = (name: string) =>
  name.replace(/[<>:"/\\|?*\x00-\x1f#\[\]]/g, " ").replace(/\s+/g, " ").trim().slice(0, 90) || "Lectura";

export function highlightFilename(title: string) {
  const slug = title.normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
    .slice(0, 140).replace(/-$/, "");
  return `subrayados-${slug || "lectura"}.md`;
}

export function readerDate(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:T| |$)/.exec(value.trim());
  if (!match) return value;
  const [, year, month, day] = match;
  const date = new Date(`${year}-${month}-${day}T12:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== `${year}-${month}-${day}`)
    return value;
  // Keep the calendar day recorded by the reader; do not shift it to the Mac timezone.
  return `${day}/${month}/${year}`;
}

export function modernizeHighlightDates(content: string) {
  return content.replace(/<!-- margen:[^>]+ -->[\s\S]*?(?=\n---(?:\r?\n|$))/g,
    block => block.replace(/^Fecha en el lector: (.+)$/gm, (_, value: string) => `Fecha : ${readerDate(value)}`));
}

export function safeRelative(path: string) {
  const pieces = path.replace(/\\/g, "/").split("/");
  if (path.startsWith("/") || pieces.some(p => !p || p === "." || p === ".." || p.startsWith(".")) || /^[A-Z]:/i.test(path))
    throw new Error("Usa una carpeta relativa dentro del vault, sin «..» ni carpetas ocultas.");
  return pieces.join("/");
}

export function readHighlights(db: Database): Highlight[] {
  const query = (sql: string) => {
    const result = db.exec(sql)[0];
    return result ? result.values.map(row => Object.fromEntries(result.columns.map((c, i) => [c, row[i]]))) : [];
  };
  const columns = new Set(query("PRAGMA table_info(Bookmark)").map(c => c.name));
  if (!["BookmarkID", "VolumeID"].every(c => columns.has(c)))
    throw new Error("No se reconoce la tabla de subrayados de este Kobo.");
  const books = new Map<string, Record<string, unknown>>();
  const contentColumns = new Set(query("PRAGMA table_info(content)").map(c => c.name));
  if (contentColumns.has("ContentID")) {
    for (const row of query("SELECT * FROM content" + (contentColumns.has("ContentType") ? " WHERE ContentType=6" : "")))
      books.set(String(row.ContentID), row);
  }
  return query("SELECT * FROM Bookmark").filter(r =>
    !["true", "1"].includes(String(r.Hidden ?? "").toLowerCase()) && (r.Text || r.Annotation)
  ).map(r => {
    const book = books.get(String(r.VolumeID)) ?? {};
    const str = (v: unknown) => v == null ? "" : String(v);
    return {
      id: str(r.BookmarkID), volume_id: str(r.VolumeID), content_id: str(r.ContentID),
      start_path: str(r.StartContainerPath), text: str(r.Text), annotation: str(r.Annotation),
      title: str(book.Title), author: str(book.Attribution), created_at: str(r.DateCreated),
      color: str(r.Color ?? r.Colour),
    };
  });
}

export function importBlock(h: ResolvedHighlight, sourcePath: string | null) {
  const fingerprint = hash(JSON.stringify([h.text, h.annotation])).slice(0, 20);
  const marker = `<!-- margen:${h.key}:${fingerprint} -->`;
  const lines = [marker, "", ...h.text.split("\n").map(line => "> " + line), ""];
  if (h.annotation) lines.push("**Anotación en Kobo:**", "", ...h.annotation.split("\n").map(line => "> " + line), "");
  if (sourcePath) lines.push(`Origen: [[${sourcePath.replace(/\.md$/i, "")}]]`, "");
  else if (h.match === "unresolved" || h.source) lines.push("*Origen pendiente de vincular.*", "");
  if (h.publication_id) lines.push(`Edición: ${h.publication_title} · ${h.publication_id}`, "");
  if (h.created_at) lines.push(`Fecha : ${readerDate(h.created_at)}`, "");
  return { marker, text: lines.join("\n") + "\n---\n" };
}

export function appendHighlight(current: string, h: ResolvedHighlight, sourcePath: string | null) {
  const block = importBlock(h, sourcePath);
  if (current.includes(block.marker)) return current;
  const updated = current.includes(`<!-- margen:${h.key}:`);
  return current.trimEnd() + "\n\n" + (updated ? "**Actualización del subrayado**\n\n" : "") + block.text;
}
