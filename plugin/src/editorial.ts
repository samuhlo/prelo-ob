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
