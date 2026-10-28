import {
  App, FileSystemAdapter, Modal, Notice, Plugin, PluginSettingTab,
  requestUrl, requireApiVersion, Setting, TFile, TFolder, TAbstractFile, MarkdownView, normalizePath, addIcon, setIcon,
} from "obsidian";
import { promises as fs, constants as fsConstants } from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { openKoboDatabase } from "./sqlite";
import { apiErrorMessage, validateNoteSizes, appendHighlight, hash, readHighlights, ResolvedHighlight, highlightFilename, modernizeHighlightDates, safeRelative } from "./core";
import { writingModes, studyAids, WritingMode, StudyAids, Language } from "./editorial";
import { Composer, MARGEN_ICON, STUDIO_TYPE, StudioTab, StudioView } from "./studio";
import { draftFromComposer, emptyComposer, parkedComposers } from "./session";
import { addPaths, noteTitle, renamePaths } from "./selection";
import { installPluginFiles, recoverPluginUpdate, UpdateTransaction } from "./installation";
import { validateConnection, Connection } from "./connection";
import type { KoboPlace } from "./delivery";
import type { KoboBook } from "./reader";
import { findUpdate, installable, PLUGIN_FILES, RELEASES_API, RELEASES_URL, ReleaseUpdate, UPDATE_INTERVAL, verifyUpdate } from "./updates";

type Settings = {
  serverUrl: string; token: string; koboPath: string; outputFolder: string;
  highlightsFolder: string; frontmatter: string; checkUpdates: boolean;
};
// Obsidian's plugin registry is not part of the public API; checked before use.
type PluginRegistry = { disablePlugin(id: string): Promise<void>; enablePlugin(id: string): Promise<boolean>; loadManifests?(): Promise<void> };
const isPluginRegistry = (value: unknown): value is PluginRegistry => typeof value === "object" && value !== null
  && typeof Reflect.get(value, "disablePlugin") === "function" && typeof Reflect.get(value, "enablePlugin") === "function";
type ImportReceipt = { completedAt: string; examined: number; added: number; unresolved: number };
type State = { settings: Settings; sources: Record<string, string>; importNotes: Record<string, string>; lastImport?: ImportReceipt;
  activeJob?: string;
  composer: Composer; previousComposer?: Composer;
  // The newest local draft retains the legacy field; the rest wait alongside it.
  parked?: Composer;
  parkedDrafts?: Composer[];
  visualWelcomeSeen?: boolean;
  lastMigration?: { completedAt: string; notes: number; renamed: number; dates: number; backup: string } };
export type Publication = {
  id: string; title: string; subtitle: string; filename: string;
  created_at: string; warnings: string[]; ai_used: boolean;
  style?: string; writing_mode?: WritingMode; study_aids?: StudyAids;
  available?: boolean; pinned?: boolean; delivery?: string; bytes?: number;
  on_kobo?: KoboPlace | null; percent_read?: number | null;
};
type PublicationDetail = Publication & {
  plan: { chapters: { title: string; source_ids: string[] }[] };
  sources: { id: string; title: string; path: string }[];
  artwork?: { id: string; placement: string; concept: string; caption: string }[];
};
type Source = { id: string; path: string; title: string; markdown: string; original_sha256: string };
type Asset = { id: string; media_type: string; data: string };
export type Draft = { id: string; title: string; intent: string; preserve_order?: boolean; style: string; paths: string[]; writing_mode?: WritingMode; study_aids?: StudyAids; language?: Language | null; use_ai?: boolean; send_to_kobo?: boolean; updated_at?: string };
const DEFAULTS: Settings = {
  checkUpdates: true, serverUrl: "http://127.0.0.1:8765", token: "", koboPath: "/Volumes/KOBOeReader",
  outputFolder: "Prelo/Publicaciones", highlightsFolder: "Prelo/Subrayados",
  frontmatter: "tipo: fuente_externa\nzona: cerebro\narea: media_consumo\nformato: subrayados\ntags: []\nrelacionadas: []",
};

class ServiceError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
}

export default class Prelo extends Plugin {
  state!: State;
  busy = false;
  update?: ReleaseUpdate;
  serverVersion?: string;
  updateMessage = "Aún no se han comprobado las versiones.";
  private checkingUpdates = false;
  private lastUpdateCheck = 0;
  private notifiedVersion = "";
  private unloaded = false;
  lastNote?: TFile;
  private ribbon?: HTMLElement;
  private modals = new Set<Modal>();
  private saveQueue: Promise<void> = Promise.resolve();
  private sharingParked?: Promise<void>;
  async onload() {
    if (this.app.vault.adapter instanceof FileSystemAdapter) {
      const directory = path.join(this.app.vault.adapter.getBasePath(), this.manifest.dir ?? `${this.app.vault.configDir}/plugins/${this.manifest.id}`);
      if (await recoverPluginUpdate(directory)) {
        new Notice("Se ha recuperado la versión anterior tras una actualización interrumpida. Reinicia Obsidian.", 0);
        return;
      }
    }
    // Enabled or updated in a running workspace: its Prelo tab is restored after this load.
    const reloading = this.app.workspace.layoutReady;
    const stored = await this.loadData();
    this.state = { settings: { ...DEFAULTS, ...stored?.settings }, sources: stored?.sources ?? {},
      importNotes: stored?.importNotes ?? {}, lastImport: stored?.lastImport, lastMigration: stored?.lastMigration,
      composer: { ...emptyComposer(), ...stored?.composer }, previousComposer: stored?.previousComposer, parked: stored?.parked,
      parkedDrafts: stored?.parkedDrafts ?? [],
      visualWelcomeSeen: stored?.visualWelcomeSeen ?? false };
    this.state.composer.paths = [...new Set<string>((this.state.composer.paths || []).filter((p: unknown) => typeof p === "string"))];
    this.state.activeJob = stored?.activeJob;
    addIcon(MARGEN_ICON, '<path d="M49 23C37 15 23 15 10 18v63c14-4 26-2 39 5 13-7 26-9 41-5V18c-14-3-27-3-41 5Z" fill="none" stroke="currentColor" stroke-width="6" stroke-linejoin="round"/><path d="M49 24v60M22 31h15M22 42h15M22 54h15M62 56h15M62 68h15" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round"/><rect x="60" y="29" width="20" height="17" rx="3" fill="currentColor"/>');
    this.registerView(STUDIO_TYPE, leaf => new StudioView(leaf, this));
    this.addSettingTab(new PreloSettings(this.app, this));
    this.addCommand({ id: "check-updates", name: "Comprobar actualizaciones", callback: () => void this.checkForUpdates(true) });
    this.registerInterval(window.setInterval(() => {
      if (this.state.settings.checkUpdates) void this.checkForUpdates();
    }, UPDATE_INTERVAL));
    this.app.workspace.onLayoutReady(() => {
      if (!this.unloaded && this.state.settings.checkUpdates) void this.checkForUpdates();
    });
    this.ribbon = this.addRibbonIcon(MARGEN_ICON, "Prelo", () => void this.openStudio());
    this.ribbon.addClass("margen-ribbon");
    this.updateRibbon();
    this.addCommand({ id: "create-publication", name: "Crear publicación", callback: () => void this.openStudio("compose") });
    this.addCommand({ id: "open-library", name: "Abrir publicaciones", callback: () => void this.openStudio("library") });
    this.addCommand({ id: "add-current", name: "Añadir nota abierta a la revista", checkCallback: checking => {
      const file = this.app.workspace.getActiveFile();
      if (!this.isEligible(file)) return false;
      if (!checking) this.addNotes([file]);
      return true;
    } });
    this.addCommand({ id: "connect", name: "Conectar con el servidor", callback: () => this.showModal(new ConnectionModal(this)) });
    this.addCommand({ id: "resume-publication", name: "Recuperar publicación en curso", callback: () => void this.run(async () => {
      if (!this.state.activeJob) throw new Error("No hay ninguna publicación pendiente.");
      const notice = new Notice("Recuperando la edición…", 0);
      try {
        const publication = await this.awaitPublication(this.state.activeJob, message => notice.setMessage(message));
        new Notice(`«${publication.title}» está en tu biblioteca compartida.`);
      } finally { notice.hide(); }
    }) });
    this.addCommand({ id: "send-latest-usb", name: "Añadir última publicación a la cola del Kobo", callback: () => void this.run(async () => {
      const publications = (await this.api("/v1/publications")).json as Publication[];
      const publication = publications.find(p => p.available !== false);
      if (!publication) throw new Error("Crea una publicación antes de enviarla al Kobo.");
      await this.queuePublication(publication);
    }) });
    this.addCommand({ id: "import-highlights", name: "Sincronizar Kobo conectado al Mac", callback: () => void this.run(async () => {
      await this.api("/v1/device/sync", {});
      new Notice("Solicitud enviada. El Mac sincronizará el Kobo cuando esté conectado.");
    }) });
    this.addCommand({ id: "tidy-highlights", name: "Actualizar nombres y fechas de subrayados", callback: () => void this.run(() => this.tidyHighlights()) });
    this.registerEvent(this.app.workspace.on("file-menu", (menu, file) => {
      const notes = this.notesFrom([file]);
      if (!notes.length) return;
      const selected = notes.length === 1 && this.state.composer.paths.includes(notes[0].path);
      menu.addItem(item => item.setTitle(selected ? "Quitar de la revista de Prelo" : notes.length === 1 ? "Añadir a Prelo" : `Añadir ${notes.length} notas a Prelo`)
        .setIcon(MARGEN_ICON).onClick(() => selected ? this.removeNote(notes[0].path) : this.addNotes(notes)));
    }));
    this.registerEvent(this.app.workspace.on("files-menu", (menu, files) => {
      const notes = this.notesFrom(files);
      if (notes.length) menu.addItem(item => item.setTitle(`Añadir ${notes.length} notas a Prelo`).setIcon(MARGEN_ICON).onClick(() => this.addNotes(notes)));
    }));
    this.registerEvent(this.app.workspace.on("editor-menu", (menu, _editor, info) => {
      if (this.isEligible(info.file)) menu.addItem(item => item.setTitle("Añadir a Prelo").setIcon(MARGEN_ICON).onClick(() => this.addNotes([info.file!])));
    }));
    this.registerEvent(this.app.workspace.on("file-open", file => {
      if (this.isEligible(file)) this.lastNote = file;
      this.updateNoteActions();
    }));
    this.registerEvent(this.app.workspace.on("layout-change", () => this.updateNoteActions()));
    this.app.workspace.onLayoutReady(() => {
      const file = this.app.workspace.getActiveFile();
      if (this.isEligible(file)) this.lastNote = file;
      this.updateNoteActions();
      if (!reloading) void this.leftStudio();
      if (!this.state.visualWelcomeSeen) {
        this.state.visualWelcomeSeen = true;
        void this.save().then(() => this.openStudio("compose")).catch(() => new Notice("No se ha podido guardar el estado de Prelo."));
      }
    });
    this.register(() => {
      this.unloaded = true;
      for (const modal of this.modals) modal.close();
      this.modals.clear();
      for (const leaf of this.app.workspace.getLeavesOfType("markdown"))
        leaf.view.containerEl.querySelectorAll(".margen-note-action").forEach(el => el.remove());
    });
    this.registerEvent(this.app.vault.on("rename", (file, oldPath) => {
      // Includes folder renames.
      for (const key of Object.keys(this.state.sources)) {
        if (key === oldPath || key.startsWith(oldPath + "/")) {
          this.state.sources[file.path + key.slice(oldPath.length)] = this.state.sources[key];
          delete this.state.sources[key];
        }
      }
      for (const [id, importPath] of Object.entries(this.state.importNotes)) {
        if (importPath === oldPath || importPath.startsWith(oldPath + "/"))
          this.state.importNotes[id] = file.path + importPath.slice(oldPath.length);
      }
      this.state.composer.paths = renamePaths(this.state.composer.paths, oldPath, file.path);
      if (this.state.previousComposer) this.state.previousComposer.paths = renamePaths(this.state.previousComposer.paths, oldPath, file.path);
      this.notifySelection();
      void this.save();
    }));
    this.registerEvent(this.app.vault.on("delete", () => this.notifySelection()));
  }
  isEligible(file: TAbstractFile | null | undefined): file is TFile {
    return file instanceof TFile && file.extension === "md" && !file.name.includes("sync-conflict");
  }
  eligibleNotes() { return this.app.vault.getMarkdownFiles().filter(file => this.isEligible(file)); }
  private notesFrom(files: TAbstractFile[]) {
    const selected = new Map<string, TFile>();
    for (const file of files) {
      if (this.isEligible(file)) selected.set(file.path, file);
      else if (file instanceof TFolder)
        for (const note of this.eligibleNotes()) if (file.path === "/" || note.path.startsWith(file.path + "/")) selected.set(note.path, note);
    }
    return [...selected.values()];
  }
  addNotes(files: TFile[], announce = true) {
    if (this.busy) { this.notifySelection(); return void new Notice("Espera a que termine la operación actual antes de cambiar la selección."); }
    try {
      const previous = this.state.composer.paths.length;
      const paths = addPaths(this.state.composer.paths, files.filter(f => this.isEligible(f)).map(f => f.path));
      if (paths.length === previous) {
        if (announce) new Notice("Estas notas ya están en tu selección.");
        return;
      }
      const starting = !this.state.composer.active;
      this.changeComposer({ paths, active: true }, true);
      if (starting && !this.app.workspace.getLeavesOfType(STUDIO_TYPE).length) void this.openStudio("compose", true);
      if (announce) {
        const added = paths.length - previous;
        new Notice(added ? `${added === 1 ? "Nota añadida" : `${added} notas añadidas`}. Pulsa el icono de Prelo para preparar tu revista.` : "Estas notas ya están en tu selección.");
      }
    } catch (error) { this.notifySelection(); new Notice(error instanceof Error ? error.message : String(error)); }
  }
  removeNote(path: string) { this.changeComposer({ paths: this.state.composer.paths.filter(p => p !== path) }, true); }
  changeComposer(patch: Partial<Composer>, remember = false) {
    if (this.busy) { this.notifySelection(); return void new Notice("Espera a que termine la operación actual antes de cambiar la selección."); }
    if (remember) this.state.previousComposer = structuredClone(this.state.composer);
    this.state.composer = { ...this.state.composer, ...patch };
    void this.save();
    this.notifySelection();
  }
  startComposer() {
    if (!this.state.composer.active) this.changeComposer({ ...emptyComposer(), active: true });
  }
  resumeComposer(composer: Composer) {
    if (this.busy) return void new Notice("Espera a que termine la operación actual antes de retomar otra revista.");
    if (this.state.composer.active && this.state.composer.paths.length)
      return void new Notice("Termina o guarda la revista que estás preparando antes de retomar otra.");
    if (composer.draftId) this.removeParkedDraft(composer.draftId);
    this.changeComposer(composer);
  }
  private localComposers() {
    return parkedComposers(this.state.parked, this.state.parkedDrafts);
  }
  private setParkedDrafts(composers: Composer[]) {
    const [newest, ...others] = composers;
    this.state.parked = newest;
    this.state.parkedDrafts = others;
  }
  removeParkedDraft(id: string, expected?: Composer) {
    this.setParkedDrafts(this.localComposers().filter(c => c.draftId !== id || expected !== undefined && c !== expected));
  }
  discardComposer() {
    const c = this.state.composer;
    this.changeComposer(emptyComposer(), true);
    if (c.draftId) void this.api(`/v1/drafts/${c.draftId}`, undefined, "DELETE").catch(() => undefined);
  }
  // Nothing stays half-done once Prelo is closed: the selection becomes a draft to resume later.
  async parkComposer(announce = true) {
    const c = this.state.composer;
    if (this.busy || this.state.activeJob || !c.active && !c.paths.length) return;
    this.state.composer = emptyComposer();
    if (!c.paths.length) { await this.save(); return this.notifySelection(); }
    const draft = draftFromComposer(c, c.draftId || randomUUID());
    this.setParkedDrafts([{ ...c, draftId: draft.id, active: false },
      ...this.localComposers().filter(p => p.draftId !== draft.id)]);
    await this.save(); this.notifySelection();
    try {
      await this.shareParked();
    } catch { /* kept on this computer; shared on the next refresh */ }
    if (announce) new Notice("Tu revista a medias se ha guardado. Retómala desde Preparar revista.");
    this.notifySelection();
  }
  async leftStudio() {
    if (this.unloaded || this.app.workspace.getLeavesOfType(STUDIO_TYPE).length) return;
    await this.parkComposer();
  }
  async shareParked() {
    if (this.sharingParked) return this.sharingParked;
    this.sharingParked = this.flushParked();
    try { await this.sharingParked; }
    finally { this.sharingParked = undefined; }
  }
  private async flushParked() {
    while (this.localComposers().length) {
      const parked = this.localComposers()[0];
      await this.api("/v1/drafts", draftFromComposer(parked, parked.draftId!));
      // An acknowledgement for an older revision must never remove a newer local one.
      this.removeParkedDraft(parked.draftId!, parked);
      await this.save();
    }
  }
  async cancelJob() {
    const id = this.state.activeJob;
    if (!id) return;
    try {
      await this.api(`/v1/jobs/${id}/cancel`, {});
      new Notice("Cancelando la edición. Se detendrá al terminar la parte en curso.");
    } catch (error) {
      // A rejected cancellation is not proof that the job was cancelled or lost.
      let absent = false;
      try { await this.api(`/v1/jobs/${id}`); }
      catch (lookupError) { absent = await this.releaseMissingJob(id, lookupError); }
      new Notice(absent ? "El servidor confirma que el trabajo ya no existe. Puedes preparar otra edición." :
        error instanceof Error ? error.message : String(error));
      return;
    }
    // Keep recovery available until the server confirms a terminal state.
    return;
  }

  undoComposer() {
    if (this.busy || !this.state.previousComposer) return;
    const previous = this.state.composer;
    this.state.composer = { ...emptyComposer(), ...this.state.previousComposer };
    this.state.previousComposer = previous;
    void this.save(); this.notifySelection();
  }
  private notifySelection() {
    this.updateRibbon(); this.updateNoteActions();
    for (const leaf of this.app.workspace.getLeavesOfType(STUDIO_TYPE))
      if (leaf.view instanceof StudioView) leaf.view.selectionChanged();
  }
  updateRibbon() {
    if (!this.ribbon) return;
    const count = this.state.composer.paths.length;
    this.ribbon.dataset.count = String(count);
    this.ribbon.setAttribute("aria-label", count ? `Prelo · ${count} notas seleccionadas` : "Prelo · Preparar una revista");
  }
  private updateNoteActions() {
    for (const leaf of this.app.workspace.getLeavesOfType("markdown")) {
      if (!(leaf.view instanceof MarkdownView)) continue;
      const view = leaf.view;
      let action = view.containerEl.querySelector<HTMLElement>(".margen-note-action");
      if (!action) {
        action = view.addAction(MARGEN_ICON, "Añadir nota a Prelo", () => {
          if (!this.isEligible(view.file)) return;
          this.state.composer.paths.includes(view.file.path) ? this.removeNote(view.file.path) : this.addNotes([view.file]);
        });
        action.addClass("margen-note-action");
      }
      const selected = !!view.file && this.state.composer.paths.includes(view.file.path);
      setIcon(action, selected ? "check" : MARGEN_ICON);
      action.setAttribute("aria-label", selected ? "Quitar nota de Prelo" : "Añadir nota a Prelo");
      action.toggleClass("is-selected", selected);
    }
  }
  async openStudio(tab?: StudioTab, background = false) {
    const file = this.app.workspace.getActiveFile();
    if (this.isEligible(file)) this.lastNote = file;
    let leaf = this.app.workspace.getLeavesOfType(STUDIO_TYPE)[0];
    if (!leaf) {
      leaf = this.app.workspace.getLeaf("tab");
      await leaf.setViewState({ type: STUDIO_TYPE, active: !background, state: { tab: tab || "compose" } });
      if (background) return;
    }
    await this.app.workspace.revealLeaf(leaf);
    if (tab && leaf.view instanceof StudioView) leaf.view.selectTab(tab);
  }
  showModal(modal: Modal) {
    this.modals.add(modal);
    const onClose = modal.onClose.bind(modal);
    modal.onClose = () => { this.modals.delete(modal); onClose(); };
    modal.open();
  }
  async checkForUpdates(manual = false) {
    if (this.checkingUpdates || this.unloaded || !manual && Date.now() - this.lastUpdateCheck < UPDATE_INTERVAL) return;
    this.checkingUpdates = true;
    this.lastUpdateCheck = Date.now();
    try {
      // Public request: never attach the private server credential or vault data.
      const response = await requestUrl({ url: RELEASES_API, headers: { Accept: "application/vnd.github+json" }, throw: false });
      if (response.status !== 200) throw new Error("No se pudo consultar GitHub. Comprueba la conexión o inténtalo más tarde.");
      const update = findUpdate(response.json, this.manifest.version);
      if (this.unloaded) return;
      this.update = update;
      this.updateMessage = update ? `Disponible Prelo ${update.version}${update.beta ? " (beta)" : ""}.` : `No hay una versión publicada más reciente que ${this.manifest.version}.`;
      if (manual || update && this.notifiedVersion !== update.version) {
        new Notice(this.updateMessage + (update ? " Pulsa «Actualizar ahora» en Prelo o en sus ajustes." : ""), 10000);
        if (update) this.notifiedVersion = update.version;
      }
    } catch (error) {
      if (this.unloaded) return;
      this.updateMessage = "No se pudieron comprobar las actualizaciones. Inténtalo más tarde.";
      if (manual) new Notice(this.updateMessage);
    } finally {
      this.checkingUpdates = false;
      if (!this.unloaded) for (const leaf of this.app.workspace.getLeavesOfType(STUDIO_TYPE))
        if (leaf.view instanceof StudioView) leaf.view.updateVersionNotice();
    }
  }
  openUpdates() { window.open(this.update?.url ?? RELEASES_URL); }
  async installUpdate() {
    if (!this.update) await this.checkForUpdates(true);
    const update = this.update;
    if (!update) return;
    if (!installable(update)) return this.openUpdates();
    let transaction: UpdateTransaction | undefined;
    await this.run(async () => {
      const notice = new Notice(`Descargando Prelo ${update.version}…`, 0);
      try {
        const files: Record<string, ArrayBuffer> = {};
        for (const name of [...PLUGIN_FILES, "SHA256SUMS"]) {
          const response = await requestUrl({ url: update.downloads[name], throw: false });
          if (response.status !== 200) throw new Error("No se pudo descargar la actualización. Comprueba la conexión e inténtalo de nuevo.");
          files[name] = response.arrayBuffer;
        }
        const { minAppVersion } = verifyUpdate(files, { id: this.manifest.id, version: update.version });
        if (!requireApiVersion(minAppVersion)) throw new Error(`Prelo ${update.version} necesita Obsidian ${minAppVersion} o posterior. Actualiza Obsidian primero.`);
        await this.shareParked().catch(() => undefined);
        await this.save();
        if (!(this.app.vault.adapter instanceof FileSystemAdapter)) throw new Error("Instala esta actualización manualmente en este equipo.");
        const dir = this.manifest.dir ?? `${this.app.vault.configDir}/plugins/${this.manifest.id}`;
        transaction = await installPluginFiles(path.join(this.app.vault.adapter.getBasePath(), dir), files);
      } finally { notice.hide(); }
    });
    if (transaction) await this.reloadAfterUpdate(update.version, transaction);
  }
  private async reloadAfterUpdate(version: string, transaction: UpdateTransaction) {
    const registry: unknown = Reflect.get(this.app, "plugins");
    if (!isPluginRegistry(registry)) {
      // Activation has not happened; retain the journal across the restart.
      return void new Notice(`Prelo ${version} instalado. Reinicia Obsidian para usarlo.`, 0);
    }
    const id = this.manifest.id;
    try {
      await registry.disablePlugin(id);
      // main.js is read from disk on enable, but manifests are cached until reloaded.
      if (typeof registry.loadManifests === "function") await registry.loadManifests();
      if (!await registry.enablePlugin(id)) throw new Error("enable");
      await transaction.commit();
      new Notice(`Prelo ${version} instalado y en marcha.`, 8000);
    } catch {
      await transaction.rollback();
      try {
        if (typeof registry.loadManifests === "function") await registry.loadManifests();
        await registry.enablePlugin(id);
      } catch { /* Files are restored; a full Obsidian restart may still be necessary. */ }
      new Notice("La actualización no se pudo activar. Se ha restaurado la versión anterior; reinicia Obsidian si es necesario.", 0);
    }
  }
  preview(publication: Publication) { this.showModal(new PreviewModal(this, publication)); }
  showHighlights(book: KoboBook) { this.showModal(new HighlightsModal(this, book)); }
  // The connector files each quote under its marker; the note may still be travelling through sync.
  async highlightNote(key: string): Promise<TFile | undefined> {
    const folder = safeRelative(this.state.settings.highlightsFolder);
    for (const file of this.app.vault.getMarkdownFiles())
      if (file.path.startsWith(folder + "/") && (await this.app.vault.cachedRead(file)).includes(`<!-- margen:${key}:`)) return file;
  }
  save() {
    const snapshot = JSON.parse(JSON.stringify(this.state));
    this.saveQueue = this.saveQueue.catch(() => {}).then(() => this.saveData(snapshot));
    return this.saveQueue;
  }
  async run(action: () => Promise<void>) {
    if (this.busy) return void new Notice("Prelo está terminando la operación anterior.");
    this.busy = true;
    try { await action(); } catch (error) { new Notice(error instanceof Error ? error.message : String(error), 12000); }
    finally { this.busy = false; }
  }
  async api(endpoint: string, body?: unknown, method?: string, candidate?: Connection) {
    const s = candidate ?? this.state.settings;
    if (!s.token) throw new Error("Añade la credencial del servicio en Ajustes → Prelo.");
    validateConnection({ serverUrl: s.serverUrl, token: s.token });
    const binary = body instanceof ArrayBuffer;
    const response = await requestUrl({
      url: s.serverUrl.replace(/\/$/, "") + endpoint,
      method: method || (body === undefined ? "GET" : "POST"),
      headers: { Authorization: `Bearer ${s.token}`, "Content-Type": binary ? "application/epub+zip" : "application/json" },
      body: body === undefined ? undefined : binary ? body : JSON.stringify(body), throw: false,
    });
    if (response.status >= 400) {
      let message = `El servicio respondió ${response.status}.`;
      try { message = apiErrorMessage(response.status, response.json.detail); } catch {}
      throw new ServiceError(response.status, message);
    }
    return response;
  }
  private async releaseMissingJob(id: string, error: unknown): Promise<boolean> {
    if (!(error instanceof ServiceError) || error.status !== 404) return false;
    if (this.state.activeJob === id) {
      this.state.activeJob = undefined;
      await this.save();
      this.notifySelection();
    }
    return true;
  }
  async awaitPublication(jobId: string, progress: (message: string) => void): Promise<Publication> {
    // Long editions are written in parts; wait up to an hour before handing off to the library.
    for (let attempt = 0; attempt < 1800; attempt++) {
      let response;
      try { response = await this.api(`/v1/jobs/${jobId}`); }
      catch (error) { await this.releaseMissingJob(jobId, error); throw error; }
      const job = response.json;
      progress(job.message);
      if (["complete", "failed", "cancelled"].includes(job.state)) {
        this.state.activeJob = undefined; await this.save();
        if (job.state !== "complete") throw new Error(job.message);
        return (await this.api(`/v1/publications/${job.publication_id}`)).json as Publication;
      }
      await new Promise(resolve => window.setTimeout(resolve, 2000));
    }
    throw new Error("La edición sigue en el servidor. Puedes recuperarla desde Mis publicaciones.");
  }
  async createPublication(payload: unknown, progress: (message: string) => void) {
    if (this.state.activeJob) throw new Error("Hay una edición en curso. Recupérala desde Mis publicaciones.");
    const id = randomUUID();
    this.state.activeJob = id; await this.save();
    try { await this.api("/v1/jobs", { id, publication: payload }); }
    catch (error) {
      // Keep the identifier if the response was lost after the server accepted it.
      try { await this.api(`/v1/jobs/${id}`); }
      catch (lookupError) { await this.releaseMissingJob(id, lookupError); }
      throw error;
    }
    return this.awaitPublication(id, progress);
  }
  async ensureFolder(folder: string) {
    const parts = safeRelative(folder).split("/");
    for (let i = 1; i <= parts.length; i++) {
      const current = parts.slice(0, i).join("/");
      if (!this.app.vault.getAbstractFileByPath(current)) {
        try { await this.app.vault.createFolder(current); }
        catch (e) { if (!this.app.vault.getAbstractFileByPath(current)) throw e; }
      }
    }
  }
  async prepare(files: TFile[]): Promise<{ notes: Source[]; assets: Asset[] }> {
    const idByPath = new Map<string, string>();
    const rawNotes = await Promise.all(files.map(file => this.app.vault.read(file)));
    validateNoteSizes(rawNotes);
    const identities = await Promise.all(files.map(async (file, index) => ({
      path: file.path, sha256: hash(rawNotes[index]),
      id: this.app.metadataCache.getFileCache(file)?.frontmatter?.margen_id || this.state.sources[file.path] || null,
    })));
    const registered = (await this.api("/v1/sources", { notes: identities })).json.notes as { id: string; path: string }[];
    for (const source of registered) {
      this.state.sources[source.path] = source.id;
      idByPath.set(source.path, source.id);
    }
    await this.save();
    const assets = new Map<string, Asset>();
    const notes: Source[] = [];
    const mime: Record<string, string> = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif", webp: "image/webp" };
    for (const file of files) {
      const raw = await this.app.vault.read(file);
      const cache = this.app.metadataCache.getFileCache(file);
      const replacements: { start: number; end: number; value: string }[] = [];
      // Obsidian's parser supplies offsets, so code blocks and literal examples stay intact.
      for (const embed of cache?.embeds ?? []) {
        if (/^https?:\/\//i.test(embed.link)) continue;
        if (raw.slice(embed.position.start.offset, embed.position.end.offset) !== embed.original)
          throw new Error(`Obsidian está actualizando «${file.basename}». Espera un momento y vuelve a publicar.`);
        const destination = this.app.metadataCache.getFirstLinkpathDest(embed.link.split("#")[0], file.path);
        if (!destination) throw new Error(`No se encuentra el adjunto «${embed.link}» en ${file.basename}.`);
        if (destination.extension === "md") throw new Error(`«${file.basename}» contiene una nota incrustada. En esta versión, selecciónala como artículo separado y retira la incrustación de la selección.`);
        if (!mime[destination.extension.toLowerCase()])
          throw new Error(`Adjunto no compatible: ${destination.path}. Esta versión admite PNG, JPG, GIF y WebP.`);
        const bytes = await this.app.vault.readBinary(destination);
        const id = hash(new Uint8Array(bytes));
        assets.set(id, { id, media_type: mime[destination.extension.toLowerCase()], data: Buffer.from(bytes).toString("base64") });
        const alt = (embed.displayText || destination.basename).replace(/[\[\]\n]/g, "");
        replacements.push({ start: embed.position.start.offset, end: embed.position.end.offset, value: `![${alt}](margen-asset:${id})` });
      }
      for (const link of cache?.links ?? []) {
        const destination = this.app.metadataCache.getFirstLinkpathDest(link.link.split("#")[0], file.path);
        if (!destination || !idByPath.has(destination.path)) continue;
        if (raw.slice(link.position.start.offset, link.position.end.offset) !== link.original)
          throw new Error(`Obsidian está actualizando «${file.basename}». Espera un momento y vuelve a publicar.`);
        const label = (link.displayText || destination.basename).replace(/[\[\]\n]/g, "");
        replacements.push({ start: link.position.start.offset, end: link.position.end.offset,
          value: `[${label}](margen-note:${idByPath.get(destination.path)})` });
      }
      let markdown = raw;
      for (const replacement of replacements.sort((a, b) => b.start - a.start))
        markdown = markdown.slice(0, replacement.start) + replacement.value + markdown.slice(replacement.end);
      // A malformed first heading must not reject the whole edition.
      const title = noteTitle(cache?.headings?.find(h => h.level === 1)?.heading, file.basename).slice(0, 200);
      notes.push({ id: idByPath.get(file.path)!, path: file.path, title, markdown, original_sha256: hash(raw) });
    }
    validateNoteSizes(notes.map(note => note.markdown));
    // Persist identity with the note so moves and another computer keep its provenance.
    // Do this after resolving link offsets from the original metadata cache.
    for (const file of files) {
      const identity = idByPath.get(file.path)!;
      if (this.app.metadataCache.getFileCache(file)?.frontmatter?.margen_id !== identity) {
        await this.app.fileManager.processFrontMatter(file, fm => { fm.margen_id = identity; });
        notes.find(n => n.id === identity)!.original_sha256 = hash(await this.app.vault.read(file));
      }
    }
    return { notes, assets: [...assets.values()] };
  }
  async queuePublication(publication: Publication) {
    await this.api(`/v1/publications/${publication.id}/action`, { action: "queue" });
    new Notice("En cola. Se copiará al conectar el Kobo al Mac mini.");
  }
  async saveEpub(publication: Publication) {
    const folder = safeRelative(this.state.settings.outputFolder);
    await this.ensureFolder(folder);
    const target = normalizePath(folder + "/" + publication.filename);
    if (!this.app.vault.getAbstractFileByPath(target)) {
      const response = await this.api(`/v1/publications/${publication.id}/epub`);
      await this.app.vault.createBinary(target, response.arrayBuffer);
    }
    return target;
  }
  async sendUsb(publication: Publication) {
    if (!/^margen-[0-9a-f-]{36}\.epub$/.test(publication.filename)) throw new Error("Nombre de publicación no válido.");
    const mount = this.state.settings.koboPath;
    await this.verifyKobo();
    const local = await this.saveEpub(publication);
    if (!(this.app.vault.adapter instanceof FileSystemAdapter)) throw new Error("Se necesita Obsidian de escritorio.");
    const target = path.join(mount, publication.filename);
    try {
      await fs.copyFile(path.join(this.app.vault.adapter.getBasePath(), local), target, fsConstants.COPYFILE_EXCL);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "EEXIST")
        throw new Error("Esta edición ya está en el Kobo.");
      throw error;
    }
    new Notice("Publicación copiada al Kobo. Expulsa el lector de forma segura antes de desconectarlo.", 8000);
  }
  async verifyKobo() {
    try {
      await fs.access(path.join(this.state.settings.koboPath, ".kobo", "KoboReader.sqlite"));
    } catch {
      throw new Error("Conecta el Kobo por USB y acepta la conexión en su pantalla. Si ya está conectado, revisa su ruta en Ajustes → Prelo.");
    }
  }
  async findSource(h: ResolvedHighlight): Promise<string | null> {
    if (!h.source) return null;
    const byId = Object.entries(this.state.sources).find(([, id]) => id === h.source!.id)?.[0];
    for (const candidate of [byId, h.source.path])
      if (candidate && this.app.vault.getAbstractFileByPath(candidate) instanceof TFile) return candidate;
    // Resolve a move that happened while Obsidian/plugin was closed only if the content is unique.
    const matches: TFile[] = [];
    for (const file of this.app.vault.getMarkdownFiles()) {
      if (hash(await this.app.vault.cachedRead(file)) === h.source.sha256) matches.push(file);
    }
    if (matches.length !== 1) return null;
    this.state.sources[matches[0].path] = h.source.id;
    await this.save();
    return matches[0].path;
  }
  availableHighlightPath(title: string, current?: TFile) {
    const folder = safeRelative(this.state.settings.highlightsFolder);
    const stem = highlightFilename(title).replace(/\.md$/, "");
    for (let suffix = 1; suffix < 10000; suffix++) {
      const candidate = `${folder}/${stem}${suffix === 1 ? "" : "-" + suffix}.md`;
      const existing = this.app.vault.getAbstractFileByPath(candidate);
      if (!existing || existing === current) return candidate;
    }
    throw new Error("Hay demasiadas notas con el mismo título.");
  }
  importNoteFor(groupId: string) {
    const folder = safeRelative(this.state.settings.highlightsFolder);
    const saved = this.state.importNotes[groupId];
    const candidates = this.app.vault.getMarkdownFiles().filter(f =>
      f.path.startsWith(folder + "/") && this.app.metadataCache.getFileCache(f)?.frontmatter?.margen_lectura === groupId);
    if (candidates.length > 1) throw new Error("Hay dos notas con el mismo identificador de lectura. Conserva ambas y revisa el conflicto.");
    if (candidates.length === 1) return candidates[0];
    const legacy = this.app.vault.getAbstractFileByPath(saved || `${folder}/lectura-${groupId}.md`);
    return legacy instanceof TFile ? legacy : null;
  }
  async tidyHighlights() {
    const folder = safeRelative(this.state.settings.highlightsFolder);
    const planned: { file: TFile; id: string; title: string; content: string }[] = [];
    for (const file of this.app.vault.getMarkdownFiles().filter(f => f.path.startsWith(folder + "/"))) {
      if (file.name.includes("sync-conflict")) continue;
      const legacy = /^lectura-([a-zA-Z0-9_-]+)\.md$/.exec(file.name)?.[1];
      const id = this.app.metadataCache.getFileCache(file)?.frontmatter?.margen_lectura || legacy;
      if (typeof id !== "string" || !/^[a-zA-Z0-9_-]{1,80}$/.test(id)) continue;
      const content = await this.app.vault.read(file);
      if (!content.includes("<!-- margen:")) continue;
      const title = /^# Subrayados — (.+)$/m.exec(content)?.[1];
      if (title) planned.push({ file, id, title, content });
    }
    const backupDir = `${this.manifest.dir}/backups`;
    if (!await this.app.vault.adapter.exists(backupDir)) await this.app.vault.adapter.mkdir(backupDir);
    const backup = `${backupDir}/subrayados-${Date.now()}.json`;
    await this.app.vault.adapter.write(backup, JSON.stringify(planned.map(n => ({
      from: n.file.path, id: n.id, content: n.content,
    })), null, 2));
    let renamed = 0, dates = 0;
    const moves: { from: string; to: string; id: string }[] = [];
    for (const item of planned) {
      const from = item.file.path;
      await this.app.vault.process(item.file, current => {
        if (current !== item.content) throw new Error(`«${item.file.basename}» cambió durante la migración; vuelve a ejecutarla.`);
        const updated = modernizeHighlightDates(current);
        if (updated !== current) dates++;
        return updated;
      });
      await this.app.fileManager.processFrontMatter(item.file, fm => { fm.margen_lectura = item.id; });
      const target = this.availableHighlightPath(item.title, item.file);
      if (item.file.path !== target) {
        await this.app.fileManager.renameFile(item.file, target);
        renamed++;
      }
      this.state.importNotes[item.id] = item.file.path;
      moves.push({ from, to: item.file.path, id: item.id });
    }
    await this.app.vault.adapter.write(backup.replace(/\.json$/, "-paths.json"), JSON.stringify(moves, null, 2));
    this.state.lastMigration = { completedAt: new Date().toISOString(), notes: planned.length, renamed, dates, backup };
    await this.save();
    new Notice(`${renamed} notas renombradas y ${dates} con fechas actualizadas. Copia de respaldo guardada.`, 8000);
  }
  async importUsb() {
    await this.verifyKobo();
    const dbPath = path.join(this.state.settings.koboPath, ".kobo", "KoboReader.sqlite");
    const wal = await fs.stat(dbPath + "-wal").catch(() => null);
    if (wal && wal.size > 0) throw new Error("La base del Kobo tiene cambios pendientes (WAL). Expulsa y vuelve a conectar el lector antes de importar.");
    if (!(this.app.vault.adapter instanceof FileSystemAdapter)) throw new Error("Se necesita Obsidian de escritorio.");
    const db = await openKoboDatabase(await fs.readFile(dbPath));
    let highlights;
    try { highlights = readHighlights(db); } finally { db.close(); }
    if (!highlights.length) return void new Notice("No se han encontrado subrayados en el Kobo.");
    const folder = safeRelative(this.state.settings.highlightsFolder);
    await this.ensureFolder(folder);
    let imported = 0;
    let unresolved = 0;
    for (let offset = 0; offset < highlights.length; offset += 100) {
      const response = await this.api("/v1/highlights/resolve", { highlights: highlights.slice(offset, offset + 100) });
      for (const h of response.json.highlights as ResolvedHighlight[]) {
        const sourcePath = await this.findSource(h);
        if (h.match === "unresolved" || (h.source && !sourcePath)) unresolved++;
        const groupId = h.source ? h.source.id : hash(h.volume_id).slice(0, 20);
        const title = h.source?.title || h.publication_title || h.title || "Lectura";
        const existingQuote = await this.highlightNote(h.key);
        let file = existingQuote || this.importNoteFor(groupId);
        if (!file) {
          const target = this.availableHighlightPath(title);
          const properties = this.state.settings.frontmatter.trim();
          const sourceField = sourcePath ? `\nfuente_nota: ${JSON.stringify("[[" + sourcePath.replace(/\.md$/i, "") + "]]")}` : "";
          const authorField = h.author ? `\nfuente_autor: ${JSON.stringify(h.author)}` : "";
          const header = `---\n${properties}${sourceField}${authorField}\nmargen_lectura: ${JSON.stringify(groupId)}\n---\n\n# Subrayados — ${title.replace(/\n/g, " ")}\n`;
          try { file = await this.app.vault.create(target, header); }
          catch (e) { throw new Error(`No se pudo crear ${target}. Repite la importación cuando termine la sincronización.`); }
        }
        if (!existingQuote) this.state.importNotes[groupId] = file.path;
        await this.app.vault.process(file, current => {
          const next = appendHighlight(current, h, sourcePath);
          if (next !== current) imported++;
          return next;
        });
      }
    }
    this.state.lastImport = { completedAt: new Date().toISOString(), examined: highlights.length, added: imported, unresolved };
    await this.save();
    new Notice(`${imported} subrayados nuevos o actualizados. ${unresolved} pendientes de vincular.`, 10000);
  }
}

type KoboHighlight = { key: string; text: string; annotation: string; created_at: string };

class HighlightsModal extends Modal {
  constructor(private plugin: Prelo, private book: KoboBook) { super(plugin.app); }
  async onOpen() {
    this.modalEl.addClass("margen-modal");
    this.contentEl.createEl("p", { text: "PRELO / SUBRAYADOS DEL KOBO", cls: "margen-kicker" });
    this.contentEl.createEl("h1", { text: this.book.title || "Libro sin título" });
    const status = this.contentEl.createEl("p", { cls: "margen-intro", text: "Cargando subrayados…" });
    const list = this.contentEl.createDiv({ cls: "margen-highlight-list" });
    try {
      const { highlights } = (await this.plugin.api(`/v1/kobo/highlights?volume=${encodeURIComponent(this.book.id)}`)).json as { highlights: KoboHighlight[] };
      status.setText(`${highlights.length} ${highlights.length === 1 ? "subrayado" : "subrayados"} recogidos por el Mac. Se guardan en tu vault, en ${this.plugin.state.settings.highlightsFolder}.`);
      if (highlights.length) new Setting(this.contentEl).addButton(b => b.setButtonText("Abrir la nota de subrayados").setCta().onClick(async () => {
        b.setDisabled(true);
        const note = await this.plugin.highlightNote(highlights[highlights.length - 1].key);
        b.setDisabled(false);
        if (!note) return void new Notice("La nota aún no está en este equipo. Espera a que termine la sincronización del vault.");
        this.close();
        await this.app.workspace.getLeaf("tab").openFile(note);
      }));
      for (const h of highlights) {
        const item = list.createDiv({ cls: "margen-highlight" });
        item.createEl("blockquote", { text: h.text || "Anotación sin texto subrayado" });
        if (h.annotation) item.createEl("p", { text: h.annotation });
        if (h.created_at) item.createEl("small", { text: new Date(h.created_at).toLocaleDateString("es-ES") });
      }
    } catch (error) {
      status.setText(error instanceof Error ? error.message : "No se pudieron cargar los subrayados.");
    }
  }
  onClose() { this.contentEl.empty(); }
}

class PreviewModal extends Modal {
  private imageUrls: string[] = [];
  private closed = false;
  constructor(private plugin: Prelo, private publication: Publication) { super(plugin.app); }
  onOpen() {
    this.modalEl.addClass("margen-modal");
    this.contentEl.createEl("p", { text: "PRELO / VISTA DE LA EDICIÓN", cls: "margen-kicker" });
    this.contentEl.createEl("h1", { text: this.publication.title });
    const grid = this.contentEl.createDiv("margen-preview");
    const artwork = grid.createDiv("margen-preview-art");
    const info = grid.createDiv();
    info.createEl("p", { text: this.publication.subtitle, cls: "margen-intro" });
    info.createEl("small", { text: `${this.publication.created_at.slice(0, 10)} · ${writingModes[this.publication.writing_mode ?? "original"].label} · ${studyAids[this.publication.study_aids ?? "none"].label}`, cls: "margen-status" });
    const chapters = info.createEl("ol", { cls: "margen-chapters" });
    void Promise.all([
      this.plugin.api(`/v1/publications/${this.publication.id}`),
      this.plugin.api(`/v1/publications/${this.publication.id}/cover`),
    ]).then(([detail, cover]) => {
      if (this.closed) return;
      const imageUrl = URL.createObjectURL(new Blob([cover.arrayBuffer], { type: "image/svg+xml" }));
      this.imageUrls.push(imageUrl);
      artwork.createEl("img", { attr: { src: imageUrl, alt: "Portada de " + this.publication.title } });
      const book = detail.json as PublicationDetail;
      for (const chapter of book.plan.chapters) {
        const item = chapters.createEl("li");
        item.createEl("strong", { text: chapter.title });
        for (const id of chapter.source_ids) {
          const source = book.sources.find(s => s.id === id);
          if (source) item.createEl("p", { text: source.title, cls: "margen-status" });
        }
      }
      const interiors = (book.artwork ?? []).filter(v => v.placement === "inside");
      if (interiors.length) {
        this.contentEl.createEl("h2", { text: "Ideas ilustradas" });
        const gallery = this.contentEl.createDiv("margen-artwork-gallery");
        for (const visual of interiors) {
          const figure = gallery.createEl("figure");
          figure.createEl("figcaption", { text: visual.caption || visual.concept });
          void this.plugin.api(`/v1/publications/${this.publication.id}/artwork/${visual.id}`).then(response => {
            if (this.closed) return;
            const url = URL.createObjectURL(new Blob([response.arrayBuffer], { type: "image/jpeg" }));
            this.imageUrls.push(url);
            const image = figure.createEl("img", { attr: { src: url, alt: visual.concept } });
            figure.prepend(image);
          }).catch(() => { if (!this.closed) figure.createEl("p", { text: "No se pudo cargar esta vista previa." }); });
        }
      }
      if (book.warnings.length) {
        const warnings = this.contentEl.createEl("details", { cls: "margen-warnings" });
        warnings.createEl("summary", { text: `${book.warnings.length} detalles de conversión para revisar` });
        for (const warning of book.warnings) warnings.createEl("p", { text: warning });
      }
    }).catch(error => { if (!this.closed) info.createEl("p", { text: error.message }); });
    new Setting(this.contentEl)
      .addButton(b => b.setButtonText("Guardar EPUB").onClick(() => void this.plugin.run(async () => {
        new Notice("Guardado en " + await this.plugin.saveEpub(this.publication));
      })))
      .addButton(b => b.setButtonText("Enviar al Kobo").setCta().onClick(() => void this.plugin.run(() => this.plugin.queuePublication(this.publication))));
  }
  onClose() {
    this.closed = true;
    for (const url of this.imageUrls) URL.revokeObjectURL(url);
    this.contentEl.empty();
  }
}

class PreloSettings extends PluginSettingTab {
  constructor(app: App, private plugin: Prelo) { super(app, plugin); }
  display() {
    const container = this.containerEl;
    container.empty();
    container.addClass("margen-settings");
    container.createEl("h2", { text: "Prelo" });
    container.createEl("h3", { text: "Versiones y actualizaciones" });
    const versions = container.createEl("p");
    const refreshVersions = () => versions.setText(`Plugin en este equipo: ${this.plugin.manifest.version} · Servidor: ${this.plugin.serverVersion ?? "sin comprobar"}. ${this.plugin.updateMessage}`);
    refreshVersions();
    new Setting(container).setName("Buscar nuevas versiones automáticamente")
      .setDesc("Consulta las releases públicas de GitHub al iniciar y cada seis horas, incluidas las betas. No envía notas ni credenciales.")
      .addToggle(t => t.setValue(this.plugin.state.settings.checkUpdates).onChange(async value => {
        this.plugin.state.settings.checkUpdates = value; await this.plugin.save();
        if (value) { await this.plugin.checkForUpdates(true); refreshVersions(); }
      }));
    new Setting(container).setName("Actualizar Prelo")
      .setDesc("«Actualizar ahora» descarga el plugin de la release de GitHub, comprueba sus sumas SHA-256 y lo reinicia en este equipo. Cada equipo se actualiza por separado. El servicio y los conectores del Mac se actualizan con el paquete para macOS.")
      .addButton(b => b.setButtonText("Comprobar versiones").onClick(async () => {
        b.setDisabled(true);
        try {
          await this.plugin.checkForUpdates(true);
          try { this.plugin.serverVersion = (await this.plugin.api("/health")).json.version; } catch { this.plugin.serverVersion = undefined; }
          refreshVersions();
        } finally { b.setDisabled(false); }
      }))
      .addButton(b => b.setButtonText("Ver novedades").onClick(() => this.plugin.openUpdates()))
      .addButton(b => b.setButtonText("Actualizar ahora").setCta().onClick(async () => {
        b.setDisabled(true);
        try { await this.plugin.installUpdate(); refreshVersions(); } finally { b.setDisabled(false); }
      }));
    new Setting(container).setName("Conexión con el servidor")
      .setDesc("Importa conexion-prelo.json, incluido en el paquete privado del panel.")
      .addButton(b => b.setButtonText("Importar conexión").onClick(() => this.plugin.showModal(new ConnectionModal(this.plugin))));
    const fields: [Exclude<keyof Settings, "checkUpdates">, string, string][] = [
      ["serverUrl", "Servicio", "Dirección del servicio en tu Mac mini o servidor."],
      ["token", "Credencial del servicio", "Acceso privado incluido en el archivo de conexión. La clave del proveedor de IA se configura solo en el servidor."],
      ["outputFolder", "Exportaciones manuales", "Carpeta del vault al pulsar Guardar EPUB. La biblioteca permanece en el Mac."],
    ];
    for (const [key, title, description] of fields) {
      new Setting(container).setName(title).setDesc(description).addText(t => {
        t.setValue(this.plugin.state.settings[key]).onChange(async v => {
          this.plugin.state.settings[key] = v.trim(); await this.plugin.save();
        });
        if (key === "token") t.inputEl.type = "password";
      });
    }
    container.createEl("p", { text: "El conector del Mac importa los subrayados automáticamente. Carpeta habitual: " + this.plugin.state.settings.highlightsFolder });
    new Setting(container).addButton(b => b.setButtonText("Comprobar conexión").onClick(() => void this.plugin.run(async () => {
      const response = await this.plugin.api("/v1/status");
      new Notice(response.json.ai_available ? "Servicio e IA configurados." : "Servicio conectado. IA pendiente de configurar.");
    })));
  }
}

class ConnectionModal extends Modal {
  constructor(private plugin: Prelo) { super(plugin.app); }
  onOpen() {
    this.modalEl.addClass("margen-modal");
    this.contentEl.createEl("h2", { text: "Conectar con el servidor" });
    this.contentEl.createEl("p", { text: "Selecciona el archivo privado de conexión de tu servidor. Si está en otro equipo, conecta primero a tu red privada." });
    const input = this.contentEl.createEl("input", { type: "file" });
    input.accept = ".json";
    input.onchange = () => void this.plugin.run(async () => {
      const file = input.files?.[0];
      if (!file) return;
      const value = JSON.parse(await file.text());
      const connection = validateConnection(value);
      await this.plugin.api("/v1/status", undefined, undefined, connection);
      this.plugin.state.settings = { ...this.plugin.state.settings, ...connection };
      await this.plugin.save();
      new Notice("Conectado a tu biblioteca compartida.");
      this.close();
    });
  }
  onClose() { this.contentEl.empty(); }
}
