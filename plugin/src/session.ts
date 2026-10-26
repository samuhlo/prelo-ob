import type { Composer } from "./studio";
import type { Draft } from "./main";

export const emptyComposer = (): Composer => ({
  paths: [], title: "", intent: "", preserveOrder: false, style: "study", writingMode: "original", studyAids: "none", language: undefined, useAI: false, sendToKobo: true, step: 1, active: false,
});

export const draftFromComposer = (c: Composer, id: string): Draft => ({
  id, title: c.title, intent: c.intent, preserve_order: c.preserveOrder, style: c.style, paths: c.paths,
  writing_mode: c.writingMode, study_aids: c.studyAids, language: c.language ?? null, use_ai: c.useAI, send_to_kobo: c.sendToKobo,
});

export const composerFromDraft = (d: Draft): Composer => ({
  ...emptyComposer(), active: true, paths: d.paths, title: d.title, intent: d.intent, preserveOrder: d.preserve_order ?? false,
  style: d.style === "retro90" ? "retro90" : "study", useAI: d.use_ai ?? d.style === "retro90", writingMode: d.writing_mode ?? "original",
  studyAids: d.study_aids ?? "none", language: d.language ?? undefined, sendToKobo: d.send_to_kobo ?? true, draftId: d.id,
});

export type Resumable = { draft: Draft; local: boolean };

// A selection parked while the Mac was unreachable stays on this computer until it can be shared.
export function resumable(drafts: Draft[], parked?: Composer): Resumable[] {
  const shared = drafts.map(draft => ({ draft, local: false }));
  if (!parked?.draftId || !parked.paths.length || drafts.some(d => d.id === parked.draftId)) return shared;
  return [{ draft: draftFromComposer(parked, parked.draftId), local: true }, ...shared];
}
