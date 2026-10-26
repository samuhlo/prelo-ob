export type KoboPlace = "imported" | "copied" | "not_imported" | "missing";
type Delivered = { available?: boolean; delivery?: string; on_kobo?: KoboPlace | null; percent_read?: number | null };
export type DeliveryState = { text: string; tone: "" | "is-queued" | "is-warning"; resend: boolean };

// "sent" only means the file was copied; the reader's own database says whether it imported it.
export function deliveryState(p: Delivered): DeliveryState {
  if (p.available === false) return { text: "Archivo retirado · subrayados conservados", tone: "", resend: false };
  if (p.delivery === "transferring") return { text: "Copiando al Kobo", tone: "is-queued", resend: false };
  if (p.delivery === "queued") return { text: "En cola para el Kobo", tone: "is-queued", resend: false };
  if (p.delivery !== "sent") return { text: "Lista para leer", tone: "", resend: false };
  if (p.on_kobo === "imported") return { text: p.percent_read ? `En tu Kobo · ${p.percent_read} % leído` : "En tu Kobo", tone: "", resend: false };
  if (p.on_kobo === "not_imported") return { text: "Copiada, pero el Kobo no la importó", tone: "is-warning", resend: false };
  if (p.on_kobo === "missing") return { text: "Ya no está en el Kobo", tone: "is-warning", resend: true };
  return { text: "Copiada · aparecerá al desconectar el Kobo", tone: "is-queued", resend: false };
}
