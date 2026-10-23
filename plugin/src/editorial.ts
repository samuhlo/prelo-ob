export const writingModes = {
  original: { label: "Notas originales", description: "Conserva el texto de tus notas tal como está." },
  narrative: { label: "Revista narrativa", description: "Conecta los artículos con introducciones, transiciones y un hilo de lectura." },
  simple: { label: "Explícamelo fácil", description: "Explica desde cero, con frases sencillas y ejemplos cotidianos." },
  step_by_step: { label: "Paso a paso", description: "Avanza de lo básico a lo complejo con pasos y ejemplos explicados." },
  review: { label: "Repaso rápido", description: "Condensa las notas en lo esencial; omite detalles para repasar." },
} as const;
export const studyAids = {
  none: { label: "Sin extras", description: "Solo el texto de la lectura." },
  visual: { label: "Esquemas y comparaciones", description: "Añade esquemas, secuencias y tablas legibles en el Kobo." },
  practice: { label: "Preguntas para practicar", description: "Añade preguntas de autoevaluación y respuestas explicadas." },
  complete: { label: "Kit de estudio completo", description: "Combina esquemas, comparaciones, preguntas y respuestas." },
} as const;
export type WritingMode = keyof typeof writingModes;
export type StudyAids = keyof typeof studyAids;
export function adaptsContent(c: { writingMode: WritingMode; studyAids: StudyAids }): boolean {
  return c.writingMode !== "original" || c.studyAids !== "none";
}
export function needsEditorialAI(c: { style: string; useAI: boolean; intent?: string; writingMode: WritingMode; studyAids: StudyAids }): boolean {
  return c.style === "retro90" || c.useAI || !!c.intent?.trim() || adaptsContent(c);
}
export const languages = {
  es: { label: "Castellano" },
  gl: { label: "Galego" },
} as const;
export type Language = keyof typeof languages;
// Function words that tell Galician from Spanish; shared words such as "para" are left out.
const GALICIAN = new Set(["unha", "unhas", "dun", "dunha", "dunhas", "nun", "nunha", "nunhas", "non", "tamén", "xa",
  "cando", "polo", "pola", "polos", "polas", "dende", "aínda", "isto", "iso", "moi", "ou", "coa", "coas", "cos", "ao",
  "aos", "á", "ás", "os", "e", "hai", "sen", "nin", "súa", "súas", "seu", "seus", "outro", "outra", "entón", "porén", "fai"]);
const SPANISH = new Set(["una", "unas", "del", "también", "ya", "cuando", "por", "muy", "más", "esto", "eso", "y",
  "el", "los", "las", "lo", "sin", "ni", "hay", "su", "sus", "otro", "otra", "entonces", "hace", "pero"]);
export function looksGalician(texts: string[]): boolean {
  let galician = 0, spanish = 0;
  for (const text of texts) {
    const prose = text.replace(/^---\r?\n[\s\S]*?\r?\n---/, "").replace(/```[\s\S]*?```/g, " ");
    for (const word of prose.toLowerCase().match(/\p{L}+/gu) ?? []) {
      if (GALICIAN.has(word)) galician++;
      else if (SPANISH.has(word)) spanish++;
    }
  }
  return galician >= 8 && galician > spanish * 1.5;
}
