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

// Keep the original single-draft field readable; additional selections are stored alongside it.
export function parkedComposers(parked?: Composer, others: Composer[] = []): Composer[] {
  const found = new Map<string, Composer>();
  for (const composer of [parked, ...others])
    if (composer?.draftId && composer.paths.length && !found.has(composer.draftId))
      found.set(composer.draftId, composer);
  return [...found.values()];
}

// Unsynced local revisions take precedence over older shared copies of the same draft.
export function resumable(drafts: Draft[], parked?: Composer, others: Composer[] = []): Resumable[] {
  const pending = parkedComposers(parked, others);
  const ids = new Set(pending.map(c => c.draftId));
  return [
    ...pending.map(c => ({ draft: draftFromComposer(c, c.draftId!), local: true })),
    ...drafts.filter(d => !ids.has(d.id)).map(draft => ({ draft, local: false })),
  ];
}
