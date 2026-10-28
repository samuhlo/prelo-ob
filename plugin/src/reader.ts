// What the Kobo holds, as last reported by the Mac, and the changes waiting for the next connection.
export type KoboBook = {
  id: string; path: string; edition: string; title: string; author: string;
  percent: number; last_read: string; status: string; present: boolean | null; highlights: number;
};
export type KoboCommand = {
  device?: string | null; id: string; kind: "remove" | "upload"; path: string; title: string;
  state: "pending" | "executing" | "cancelled" | "done" | "failed"; message?: string | null; created_at: string; done_at?: string | null;
};
export type KoboOverview = { device?: string; at: string | null; books: KoboBook[]; commands: KoboCommand[] };
export type BookFilter = "all" | "prelo" | "other";

export function bookStatus(book: KoboBook, overview: KoboOverview): { text: string; removable: boolean } {
  const commands = overview.commands.filter(c => !!overview.device && c.device === overview.device && c.kind === "remove" && c.path === book.path && book.path);
  if (commands.some(c => ["pending", "executing"].includes(c.state))) return { text: "Se quitará en la próxima conexión", removable: false };
  if (commands.some(c => c.state === "done" && overview.at && (c.done_at ?? "") > overview.at))
    return { text: "Quitado · desaparecerá al desconectar el Kobo", removable: false };
  if (book.path && book.present === false) return { text: "El archivo ya no está en el Kobo", removable: false };
  const reading = book.percent ? `${book.percent} % leído` : book.last_read ? "Empezado" : "Sin abrir";
  return { text: reading, removable: !!book.path };
}

export function visibleBooks(books: KoboBook[], query: string, filter: BookFilter): KoboBook[] {
  const words = query.toLocaleLowerCase("es").split(/\s+/).filter(Boolean);
  return books
    .filter(b => filter === "all" || (filter === "prelo") === !!b.edition)
    .filter(b => words.every(w => `${b.title} ${b.author}`.toLocaleLowerCase("es").includes(w)))
    // Recently read first, then the rest by title.
    .sort((a, b) => (b.last_read || "").localeCompare(a.last_read || "") || a.title.localeCompare(b.title, "es"));
}

export const commandLabel = (c: KoboCommand): string =>
  `${c.kind === "remove" ? "Quitar" : "Enviar"} «${c.title}»${c.state === "failed" ? ` · no se pudo: ${c.message || "error"}` : ""}`;
