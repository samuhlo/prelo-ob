import { ItemView, Menu, Modal, Notice, setIcon, TFile, WorkspaceLeaf } from "obsidian";
import { randomUUID } from "node:crypto";
import type Prelo from "./main";
import type { Draft, Publication } from "./main";
import { deliveryState } from "./delivery";
import { composerFromDraft, emptyComposer, resumable } from "./session";
import { compareVersions } from "./updates";
import { matchesSearch, movePath } from "./selection";
import { appendPreloLogo } from "./brand";
import { writingModes, studyAids, languages, WritingMode, StudyAids, Language, adaptsContent, needsEditorialAI, looksGalician } from "./editorial";

export const STUDIO_TYPE = "margen-studio";
export const MARGEN_ICON = "margen-magazine";
export type StudioTab = "compose" | "library" | "queue";
export type Composer = {
  paths: string[]; title: string; intent: string; style: "study" | "retro90";
  preserveOrder: boolean; writingMode: WritingMode; studyAids: StudyAids;
  // Unset means: follow the language detected in the selected notes.
  language?: Language;
  useAI: boolean; sendToKobo: boolean; step: 1 | 2; draftId?: string;
  // A magazine is being prepared; otherwise Preparar revista shows the start screen.
  active: boolean;
};
export { emptyComposer } from "./session";
type Library = {
  version?: string;
  publications: Publication[];
  device: { state: string; message: string; heartbeat_at?: string; last_sync?: { at: string; added: number; sent: number } };
  storage: { used_bytes: number; limit_bytes: number };
  jobs: { id: string; state: string; message: string; updated_at: string }[];
};
const labelStyle = (style?: string) => style === "retro90" ? "Revista 90’s" : "Revista de estudio";
const date = (value: string) => new Date(value).toLocaleDateString("es-ES");
const size = (bytes: number) => `${(bytes / 1e9).toLocaleString("es-ES", { maximumFractionDigits: 2 })} GB`;

function button(parent: HTMLElement, text: string, action: () => void, icon?: string, cls = "") {
  const el = parent.createEl("button", { cls: `margen-button ${cls}`, attr: { type: "button" } });
  if (icon) setIcon(el.createSpan({ cls: "margen-button-icon" }), icon);
  el.createSpan({ text });
  el.onclick = action;
  return el;
}

function iconButton(parent: HTMLElement, icon: string, label: string, action: (event: MouseEvent) => void) {
  const el = parent.createEl("button", { cls: "margen-icon-button", attr: { type: "button", "aria-label": label, title: label } });
  setIcon(el, icon);
  el.onclick = action;
  return el;
}

export class StudioView extends ItemView {
  tab: StudioTab = "compose";
  private library?: Library;
  private drafts: Draft[] = [];
  private aiAvailable = false;
  private connection = "Conectando con tu biblioteca…";
  private error = "";
  private closed = false;
  private loading = false;
  private covers = new Map<string, string>();
  private page?: HTMLElement;
  private notesEl?: HTMLElement;
  private trayEl?: HTMLElement;
  private query = "";
  private folder = "";
  private onlySelected = false;
  private shown = 80;
  private progress = "";
  private created?: Publication;
  private libraryQuery = "";
  private libraryFilter = "available";
  private visibleBooks = 24;
  private remoteSignature = "";
  private detected = { key: "", galician: false };

  constructor(leaf: WorkspaceLeaf, private plugin: Prelo) { super(leaf); }
  getViewType() { return STUDIO_TYPE; }
  getDisplayText() { return "Prelo"; }
  getIcon() { return MARGEN_ICON; }
  getState() { return { tab: this.tab }; }
  async setState(state: unknown, result: { history: boolean }) {
    const tab = (state as { tab?: StudioTab })?.tab;
    if (tab && ["compose", "library", "queue"].includes(tab)) this.tab = tab;
    await super.setState(state, result);
    if (this.page) this.render();
  }
  async onOpen() {
    this.closed = false;
    this.contentEl.addClass("margen-studio");
    this.addAction("refresh-cw", "Actualizar biblioteca", () => void this.refresh(true));
    this.render();
    void this.refresh();
    this.registerInterval(window.setInterval(() => void this.refresh(), 15000));
  }
  async onClose() {
    this.closed = true;
    for (const url of this.covers.values()) URL.revokeObjectURL(url);
    this.covers.clear();
    this.contentEl.empty();
    // Closing the last Prelo tab ends the session; the plugin decides once the layout settles.
    window.setTimeout(() => void this.plugin.leftStudio(), 0);
  }
  selectTab(tab: StudioTab) { this.tab = tab; this.render(); void this.refresh(); }
  selectionChanged() {
    if (this.tab !== "compose") return;
    const c = this.plugin.state.composer;
    if (c.active && !this.plugin.state.activeJob && c.step === 1 && this.notesEl?.isConnected) {
      this.renderNotes();
      this.renderTray();
    } else this.render();
  }
  async refresh(force = false) {
    if (this.loading || this.closed) return;
    this.loading = true;
    try {
      await this.plugin.shareParked().catch(() => undefined);
      const [library, drafts, status] = await Promise.all([
        this.plugin.api("/v1/library"), this.plugin.api("/v1/drafts"), this.plugin.api("/v1/status"),
      ]);
      if (this.closed) return;
      const meaningful = { publications: library.json.publications, jobs: library.json.jobs,
        drafts: drafts.json, device: { state: library.json.device.state, message: library.json.device.message,
          last_sync: library.json.device.last_sync, online: !!library.json.device.heartbeat_at && Date.now() - Date.parse(library.json.device.heartbeat_at) < 45000 } };
      const signature = JSON.stringify(meaningful);
      const changed = this.remoteSignature !== signature;
      this.remoteSignature = signature;
      this.library = library.json as Library;
      this.drafts = drafts.json as Draft[];
      this.aiAvailable = !!status.json.ai_available;
      this.connection = "Biblioteca conectada";
      this.error = "";
      const current = this.library.jobs.find(j => j.id === this.plugin.state.activeJob);
      const finished = current && ["complete", "failed", "cancelled"].includes(current.state);
      if (finished) { this.plugin.state.activeJob = undefined; void this.plugin.save(); }
      // The start screen lists the drafts; an open composer is never redrawn under the user.
      const starting = this.tab === "compose" && !this.plugin.state.composer.active;
      if ((changed && (this.tab !== "compose" || starting)) || force || finished && this.tab === "compose" && !this.plugin.busy) this.render();
      else this.updateConnection();
      if (this.tab === "compose" && this.plugin.state.composer.step === 2) this.updateCreateButton();
    } catch (error) {
      if (this.closed) return;
      this.error = error instanceof Error ? error.message : "No se pudo conectar.";
      this.connection = "Sin conexión al Mac";
      this.updateConnection();
      if (!this.library && this.tab !== "compose") this.render();
    } finally { this.loading = false; }
  }
  private updateConnection() {
    this.updateVersionNotice();
    const badge = this.contentEl.querySelector<HTMLElement>(".margen-connection");
    if (badge) {
      badge.setText(this.connection);
      badge.toggleClass("is-offline", !!this.error);
      badge.title = this.error || "La biblioteca y la cola se comparten entre tus equipos.";
    }
    const queueLabel = this.contentEl.querySelector<HTMLElement>('.margen-tabs [data-tab="queue"] > span:last-child');
    const count = this.library?.publications.filter(p => ["queued", "transferring"].includes(p.delivery || "")).length || 0;
    queueLabel?.setText(count ? `Kobo · ${count}` : "Kobo");
  }
  private render() {
    if (this.closed) return;
    this.contentEl.empty();
    this.notesEl = undefined; this.trayEl = undefined;
    const shell = this.contentEl.createDiv({ cls: "margen-shell" });
    const header = shell.createDiv({ cls: "margen-header" });
    const brand = header.createDiv({ cls: "margen-brand" });
    appendPreloLogo(brand);
    header.createSpan({ text: this.connection, cls: `margen-connection${this.error ? " is-offline" : ""}` });
    const nav = shell.createEl("nav", { cls: "margen-tabs", attr: { "aria-label": "Secciones de Prelo" } });
    const pending = this.library?.publications.filter(p => ["queued", "transferring"].includes(p.delivery || "")).length || 0;
    for (const [tab, text, icon] of [["compose", "Preparar revista", "square-pen"], ["library", "Biblioteca", "library-big"], ["queue", pending ? `Kobo · ${pending}` : "Kobo", "tablet"]] as const) {
      const el = button(nav, text, () => this.selectTab(tab), icon, this.tab === tab ? "is-active" : "");
      el.dataset.tab = tab;
      el.setAttribute("aria-current", this.tab === tab ? "page" : "false");
    }
    shell.createDiv({ cls: "margen-update-notice", attr: { role: "status", "aria-live": "polite" } });
    this.updateVersionNotice();
    this.page = shell.createDiv({ cls: "margen-page" });
    if (this.tab === "compose") this.renderComposer();
    else if (this.tab === "library") this.renderLibrary();
    else this.renderQueue();
    this.updateConnection();
  }
  updateVersionNotice() {
    const notice = this.contentEl.querySelector<HTMLElement>(".margen-update-notice");
    if (!notice) return;
    notice.empty();
    const update = this.plugin.update;
    const server = this.library?.version;
    if (server) this.plugin.serverVersion = server;
    if (update) {
      notice.createEl("p", { text: `Prelo ${update.version}${update.beta ? " (beta)" : ""} disponible · tienes ${this.plugin.manifest.version} en este equipo.` });
      button(notice, "Actualizar ahora", () => void this.plugin.installUpdate(), "download");
      button(notice, "Novedades", () => this.plugin.openUpdates(), "external-link");
    }
    if (server && compareVersions(this.plugin.manifest.version, server) === 1)
      notice.createEl("p", { text: `El servidor usa ${server}; este plugin usa ${this.plugin.manifest.version}. Actualiza el servicio y los conectores del Mac para disponer de las nuevas funciones.` });
    else if (server && compareVersions(server, this.plugin.manifest.version) === 1)
      notice.createEl("p", { text: `El servidor usa ${server}; actualiza este plugin (${this.plugin.manifest.version}) para disponer de sus nuevas opciones.` });
  }
  private heading(kicker: string, title: string, description: string, parent = this.page!) {
    if (kicker) parent.createEl("p", { cls: "margen-kicker", text: kicker });
    parent.createEl("h1", { text: title });
    parent.createEl("p", { cls: "margen-lead", text: description });
  }
  private renderComposer() {
    const c = this.plugin.state.composer;
    if (this.plugin.state.activeJob) {
      this.renderProgress();
      return;
    }
    if (!c.active) { this.renderStart(); return; }
    this.heading("TU PRÓXIMA LECTURA", c.step === 1 ? "Las notas las eliges tú." : "Dale forma a tu revista.",
      c.step === 1 ? "Reúne apuntes, artículos e ideas. Después elegimos cómo leerlos." : "Dos estilos, las mismas ideas. Elige el que te apetezca llevar al Kobo.");
    const steps = this.page!.createDiv({ cls: "margen-steps" });
    button(steps, "1 · Reunir notas", () => this.plugin.changeComposer({ step: 1 }), undefined, c.step === 1 ? "is-active" : "");
    const next = button(steps, "2 · Elegir estilo y crear", () => this.plugin.changeComposer({ step: 2 }), undefined, c.step === 2 ? "is-active" : "");
    next.disabled = !c.paths.length;
    const session = steps.createDiv({ cls: "margen-session-actions" });
    button(session, "Guardar y salir", () => void this.plugin.parkComposer(), "bookmark");
    iconButton(session, "trash-2", "Descartar esta revista", () => this.plugin.discardComposer());
    if (c.step === 2) { this.renderDesign(); return; }
    const layout = this.page!.createDiv({ cls: "margen-compose-grid" });
    const picker = layout.createDiv({ cls: "margen-picker" });
    const toolbar = picker.createDiv({ cls: "margen-searchbar" });
    setIcon(toolbar.createSpan(), "search");
    const search = toolbar.createEl("input", { type: "search", placeholder: "Buscar una nota, un tema o una carpeta…", attr: { "aria-label": "Buscar notas para la revista" } });
    search.value = this.query;
    search.oninput = () => { this.query = search.value; this.shown = 80; this.renderNotes(); };
    const filters = picker.createDiv({ cls: "margen-picker-filters" });
    const folders = filters.createEl("select", { attr: { "aria-label": "Filtrar por carpeta" } });
    folders.createEl("option", { value: "", text: "Todas las carpetas" });
    for (const folder of [...new Set(this.plugin.eligibleNotes().map(f => f.path.split("/").slice(0, -1)[0]).filter(Boolean))].sort())
      folders.createEl("option", { value: folder, text: folder });
    folders.value = this.folder;
    folders.onchange = () => { this.folder = folders.value; this.shown = 80; this.renderNotes(); };
    const selected = button(filters, "Solo seleccionadas", () => {
      this.onlySelected = !this.onlySelected; selected.toggleClass("is-active", this.onlySelected); selected.setAttribute("aria-pressed", String(this.onlySelected)); this.renderNotes();
    });
    selected.toggleClass("is-active", this.onlySelected);
    selected.setAttribute("aria-pressed", String(this.onlySelected));
    this.notesEl = picker.createDiv({ cls: "margen-notes", attr: { "aria-label": "Notas disponibles" } });
    this.trayEl = layout.createEl("aside", { cls: "margen-tray", attr: { "aria-label": "Tu selección" } });
    this.renderNotes(); this.renderTray();
    const tip = this.page!.createDiv({ cls: "margen-tip" });
    setIcon(tip.createSpan(), "mouse-pointer-2");
    tip.createSpan({ text: "También puedes seleccionar notas en el explorador y usar clic derecho → Añadir a Prelo." });
  }
  private title(file: TFile) { return this.app.metadataCache.getFileCache(file)?.headings?.find(h => h.level === 1)?.heading || file.basename; }
  private renderNotes() {
    if (!this.notesEl) return;
    const scroll = this.notesEl.scrollTop;
    const active = this.contentEl.ownerDocument.activeElement as HTMLElement | null;
    const focusedPath = active && this.notesEl.contains(active) ? active.dataset.notePath : undefined;
    this.notesEl.empty();
    const paths = this.plugin.state.composer.paths;
    const files = this.plugin.eligibleNotes().filter(f =>
      (!this.folder || f.path.startsWith(this.folder + "/")) && (!this.onlySelected || paths.includes(f.path)) && matchesSearch(this.title(f), f.path, this.query)
    ).sort((a, b) => b.stat.mtime - a.stat.mtime || a.path.localeCompare(b.path));
    const meta = this.notesEl.createDiv({ cls: "margen-results-meta" });
    meta.createSpan({ text: `${files.length} notas · recientes primero` });
    if (files.length && files.length <= 100)
      button(meta, "Añadir visibles", () => this.plugin.addNotes(files), "plus");
    for (const file of files.slice(0, this.shown)) {
      const row = this.notesEl.createEl("label", { cls: `margen-pick-row${paths.includes(file.path) ? " is-selected" : ""}` });
      const checkbox = row.createEl("input", { type: "checkbox", attr: { "aria-label": `Seleccionar ${this.title(file)}` } });
      checkbox.dataset.notePath = file.path;
      checkbox.checked = paths.includes(file.path);
      const text = row.createDiv({ cls: "margen-pick-copy" });
      text.createEl("strong", { text: this.title(file) });
      text.createEl("small", { text: file.parent?.path || "Raíz", attr: { title: file.path } });
      checkbox.onchange = () => checkbox.checked ? this.plugin.addNotes([file], false) : this.plugin.removeNote(file.path);
    }
    if (!files.length) this.notesEl.createEl("p", { cls: "margen-empty-copy", text: this.onlySelected ? "No hay notas seleccionadas con este filtro." : "No encuentro notas con esa búsqueda. Prueba otro tema o carpeta." });
    if (files.length > this.shown) button(this.notesEl, "Mostrar más notas", () => { this.shown += 80; this.renderNotes(); }, "chevron-down", "margen-load-more");
    this.notesEl.scrollTop = scroll;
    if (focusedPath) Array.from(this.notesEl.querySelectorAll<HTMLInputElement>("input")).find(input => input.dataset.notePath === focusedPath)?.focus({ preventScroll: true });
  }
  private renderTray() {
    if (!this.trayEl) return;
    const active = this.contentEl.ownerDocument.activeElement as HTMLElement | null;
    const focusedRow = active?.closest<HTMLElement>(".margen-selection-item")?.dataset.notePath;
    const focusedAction = active?.getAttribute("aria-label");
    this.trayEl.empty();
    const c = this.plugin.state.composer;
    const top = this.trayEl.createDiv({ cls: "margen-tray-heading" });
    top.createEl("h2", { text: "Tu selección" });
    top.createSpan({ cls: "margen-count-pill", text: String(c.paths.length) });
    if (!c.paths.length) {
      const empty = this.trayEl.createDiv({ cls: "margen-selection-empty" });
      setIcon(empty.createSpan(), "notebook-pen");
      empty.createEl("p", { text: "Una revista empieza con una buena nota." });
      if (this.plugin.lastNote && this.plugin.isEligible(this.plugin.lastNote)) button(empty, "Añadir nota abierta", () => this.plugin.addNotes([this.plugin.lastNote!]), "plus");
    } else {
      this.trayEl.createEl("p", { cls: "margen-hint", text: "Arrastra para ordenar o usa las flechas." });
      const list = this.trayEl.createEl("ol", { cls: "margen-selection-list" });
      for (const [index, path] of c.paths.entries()) {
        const file = this.app.vault.getAbstractFileByPath(path);
        const row = list.createEl("li", { cls: `margen-selection-item${file instanceof TFile ? "" : " is-missing"}` });
        row.dataset.notePath = path;
        row.draggable = true;
        row.ondragstart = event => { event.dataTransfer?.setData("application/x-margen-note", path); };
        row.ondragover = event => { if (event.dataTransfer?.types.includes("application/x-margen-note")) { event.preventDefault(); row.addClass("is-drop-target"); } };
        row.ondragleave = () => row.removeClass("is-drop-target");
        row.ondrop = event => {
          event.preventDefault(); row.removeClass("is-drop-target");
          const source = event.dataTransfer?.getData("application/x-margen-note");
          if (source) this.plugin.changeComposer({ paths: movePath(c.paths, source, path) }, true);
        };
        row.createSpan({ text: String(index + 1).padStart(2, "0"), cls: "margen-note-number" });
        const text = row.createDiv({ cls: "margen-selection-title" });
        text.createSpan({ text: file instanceof TFile ? this.title(file) : path.split("/").pop() || path, attr: { title: path } });
        if (!(file instanceof TFile)) text.createEl("small", { text: "Esta nota no está en el equipo" });
        const actions = row.createDiv({ cls: "margen-selection-actions" });
        const up = iconButton(actions, "chevron-up", "Subir nota", () => this.plugin.changeComposer({ paths: movePath(c.paths, path, c.paths[index - 1]) }, true));
        up.disabled = index === 0;
        const down = iconButton(actions, "chevron-down", "Bajar nota", () => this.plugin.changeComposer({ paths: movePath(c.paths, path, c.paths[index + 1]) }, true));
        down.disabled = index === c.paths.length - 1;
        iconButton(actions, "x", "Quitar nota de la revista", () => this.plugin.removeNote(path));
      }
    }
    const footer = this.trayEl.createDiv({ cls: "margen-tray-footer" });
    const next = button(footer, "Elegir estilo", () => this.plugin.changeComposer({ step: 2 }), "arrow-right", "margen-primary");
    next.disabled = !c.paths.length || c.paths.some(p => !(this.app.vault.getAbstractFileByPath(p) instanceof TFile));
    const tools = footer.createDiv({ cls: "margen-selection-tools" });
    const undo = button(tools, "Deshacer", () => this.plugin.undoComposer()); undo.disabled = !this.plugin.state.previousComposer;
    if (c.paths.length) button(tools, "Vaciar", () => this.plugin.changeComposer({ paths: [], step: 1 }, true));
    this.contentEl.querySelectorAll<HTMLButtonElement>(".margen-steps button")[1]?.toggleAttribute("disabled", !c.paths.length);
    if (focusedRow && focusedAction) {
      const row = Array.from(this.trayEl.querySelectorAll<HTMLElement>(".margen-selection-item")).find(row => row.dataset.notePath === focusedRow);
      Array.from(row?.querySelectorAll<HTMLButtonElement>("button") || []).find(button => button.getAttribute("aria-label") === focusedAction)?.focus({ preventScroll: true });
    }
  }
  private renderDesign() {
    const c = this.plugin.state.composer;
    const selected = this.page!.createDiv({ cls: "margen-selected-strip" });
    setIcon(selected.createSpan(), "files");
    selected.createSpan({ text: `${c.paths.length} notas listas para tu revista` });
    button(selected, "Revisar selección", () => this.plugin.changeComposer({ step: 1 }));
    const styles = this.page!.createDiv({ cls: "margen-style-grid", attr: { role: "radiogroup", "aria-label": "Estilo de la revista" } });
    for (const style of ["study", "retro90"] as const) {
      const card = styles.createEl("button", { cls: `margen-style-card ${style}${c.style === style ? " is-selected" : ""}`,
        attr: { type: "button", role: "radio", "aria-checked": String(c.style === style) } });
      card.tabIndex = c.style === style ? 0 : -1;
      const sample = card.createDiv({ cls: "margen-style-sample", attr: { "aria-hidden": "true" } });
      sample.createSpan({ text: "PRELO", cls: "sample-masthead" });
      sample.createSpan({ text: style === "study" ? "IDEAS QUE SE QUEDAN" : "IDEAS EN JUEGO", cls: "sample-title" });
      const artwork = sample.createSpan({ cls: "sample-graphic" });
      setIcon(artwork, style === "study" ? "book-open-text" : "gamepad-2");
      sample.createSpan({ text: style === "study" ? "LEER · ENTENDER · REPASAR" : "EXPLORA TU PRÓXIMA LECTURA", cls: "sample-footer" });
      const copy = card.createDiv({ cls: "margen-style-copy" });
      copy.createEl("strong", { text: labelStyle(style) });
      copy.createEl("p", { text: style === "study" ? "Clara, tranquila y centrada en tus apuntes." : "Color, ilustraciones y espíritu de revista de los 90." });
      copy.createSpan({ cls: "margen-style-cost", text: style === "study" ? "Sin imágenes generadas · IA opcional" : "Portada + una carátula retro por nota · usa tu cuota de IA" });
      card.onclick = () => { this.plugin.changeComposer({ style }); };
      card.onkeydown = event => {
        if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
        event.preventDefault();
        const next = style === "study" ? "retro90" : "study";
        this.plugin.changeComposer({ style: next });
        this.contentEl.querySelector<HTMLButtonElement>(`.margen-style-card.${next}`)?.focus({ preventScroll: true });
      };
    }
    const fields = this.page!.createDiv({ cls: "margen-editor-fields" });
    const writing = fields.createEl("label", { cls: "margen-field" });
    writing.createSpan({ text: "Redacción" });
    const writingSelect = writing.createEl("select");
    for (const [value, option] of Object.entries(writingModes)) writingSelect.createEl("option", { value, text: option.label });
    writingSelect.value = c.writingMode;
    writing.createEl("small", { text: writingModes[c.writingMode].description });
    writingSelect.onchange = () => this.plugin.changeComposer({ writingMode: writingSelect.value as WritingMode });
    const aids = fields.createEl("label", { cls: "margen-field" });
    aids.createSpan({ text: "Apoyos para estudiar" });
    const aidsSelect = aids.createEl("select");
    for (const [value, option] of Object.entries(studyAids)) aidsSelect.createEl("option", { value, text: option.label });
    aidsSelect.value = c.studyAids;
    aids.createEl("small", { text: studyAids[c.studyAids].description });
    aidsSelect.onchange = () => this.plugin.changeComposer({ studyAids: aidsSelect.value as StudyAids });
    if (this.detected.key !== c.paths.join("\n")) void this.detectLanguage(c.paths);
    if (this.detected.galician || c.language === "gl") {
      const language = fields.createEl("label", { cls: "margen-field" });
      language.createSpan({ text: "Idioma de la revista" });
      const languageSelect = language.createEl("select");
      for (const [value, option] of Object.entries(languages)) languageSelect.createEl("option", { value, text: option.label });
      languageSelect.value = this.language();
      language.createEl("small", { text: adaptsContent(c) ? "Hemos detectado notas en gallego. La IA escribirá la revista en el idioma elegido."
        : "Hemos detectado notas en gallego. Con «Notas originales» el texto se conserva; el idioma se aplica a la portada, el índice y los textos de la IA." });
      languageSelect.onchange = () => this.plugin.changeComposer({ language: languageSelect.value as Language });
    }
    fields.createEl("p", { cls: "margen-hint", text: "La redacción y los apoyos se pueden combinar con ambos tipos de revista. Adaptar el texto o añadir apoyos usa IA. Tus notas del vault no se modifican." });
    const title = fields.createEl("label", { cls: "margen-field" });
    title.createSpan({ text: "Un título para esta lectura" });
    const input = title.createEl("input", { type: "text", placeholder: "Opcional · podemos proponerlo por ti", attr: { maxlength: "160" } });
    input.value = c.title;
    input.oninput = () => { c.title = input.value; void this.plugin.save(); };
    const intention = fields.createEl("label", { cls: "margen-field" });
    intention.createSpan({ text: "Instrucciones extra (opcional)" });
    const area = intention.createEl("textarea", { placeholder: "Después de cada tema de redes, coloca inmediatamente su examen resuelto. Ordena las parejas de lo básico a lo avanzado.", attr: { rows: "4", maxlength: "2000" } });
    area.value = c.intent;
    area.oninput = () => { c.intent = area.value; void this.plugin.save(); this.updateCreateButton(); };
    intention.createEl("small", { text: "Se aplican con IA y tienen prioridad sobre la organización automática. Puedes indicar orden, agrupaciones y enfoque. Se guardan en el borrador." });
    const order = fields.createEl("label", { cls: "margen-toggle-row" });
    const orderCheckbox = order.createEl("input", { type: "checkbox" }); orderCheckbox.checked = c.preserveOrder;
    orderCheckbox.onchange = () => { c.preserveOrder = orderCheckbox.checked; void this.plugin.save(); };
    const orderCopy = order.createDiv();
    orderCopy.createEl("strong", { text: "Respetar exactamente el orden de mi selección" });
    orderCopy.createEl("small", { text: "Coloca los temas y sus exámenes en Revisar selección. Este orden queda bloqueado, incluso si las instrucciones extra piden otro." });
    if (c.style === "study" && !adaptsContent(c)) {
      const row = fields.createEl("label", { cls: "margen-toggle-row" });
      const checkbox = row.createEl("input", { type: "checkbox" }); checkbox.checked = c.useAI;
      checkbox.onchange = () => { c.useAI = checkbox.checked; void this.plugin.save(); this.updateCreateButton(); };
      const copy = row.createDiv(); copy.createEl("strong", { text: "Organizar con IA" }); copy.createEl("small", { text: "Propone el título y las secciones. El texto de tus notas se conserva." });
    }
    const delivery = fields.createEl("label", { cls: "margen-toggle-row" });
    const send = delivery.createEl("input", { type: "checkbox" }); send.checked = c.sendToKobo;
    send.onchange = () => { c.sendToKobo = send.checked; void this.plugin.save(); };
    const copy = delivery.createDiv(); copy.createEl("strong", { text: "Prepararla para el Kobo" }); copy.createEl("small", { text: "Se enviará cuando conectes el lector al Mac." });
    const actions = this.page!.createDiv({ cls: "margen-create-footer" });
    actions.createSpan({ cls: "margen-create-summary", text: `${c.paths.length} notas · ${adaptsContent(c) ? `${writingModes[c.writingMode].label} · ${studyAids[c.studyAids].label} · IA` : c.style === "retro90" ? `Portada + ${c.paths.length} carátulas con IA` : c.intent.trim() ? "Instrucciones extra con IA" : c.useAI ? "Organización con IA" : "Sin IA"}` });
    button(actions, "Crear mi revista", () => void this.create(), "sparkles", "margen-primary margen-create-button");
    this.page!.createEl("p", { cls: "margen-create-hint margen-hint" });
    this.updateCreateButton();
  }
  private language(): Language {
    return this.plugin.state.composer.language ?? (this.detected.galician ? "gl" : "es");
  }
  private async detectLanguage(paths: string[]) {
    const key = paths.join("\n");
    this.detected = { key, galician: this.detected.galician };
    const files = paths.map(path => this.app.vault.getAbstractFileByPath(path)).filter((f): f is TFile => f instanceof TFile);
    const texts = await Promise.all(files.slice(0, 40).map(async file => (await this.app.vault.cachedRead(file)).slice(0, 6000)));
    if (this.detected.key !== key) return;
    const galician = looksGalician(texts);
    const changed = galician !== this.detected.galician;
    this.detected = { key, galician };
    if (changed && this.tab === "compose" && this.plugin.state.composer.step === 2 && !this.plugin.busy) this.render();
  }
  private updateCreateButton() {
    const c = this.plugin.state.composer;
    const needsAI = needsEditorialAI(c);
    const blocked = !!this.error || !this.library || needsAI && !this.aiAvailable || !c.paths.length || c.paths.some(p => !(this.app.vault.getAbstractFileByPath(p) instanceof TFile));
    const button = this.contentEl.querySelector<HTMLButtonElement>(".margen-create-button");
    if (button) button.disabled = blocked;
    const summary = this.contentEl.querySelector<HTMLElement>(".margen-create-summary");
    if (summary) summary.setText(this.error ? "Sin conexión al Mac" : `${c.paths.length} notas · ${adaptsContent(c) ? `${writingModes[c.writingMode].label} · ${studyAids[c.studyAids].label} · IA` : c.style === "retro90" ? `Portada + ${c.paths.length} carátulas con IA` : c.intent.trim() ? "Instrucciones extra con IA" : c.useAI ? "Organización con IA" : "Sin IA"}`);
    const hint = this.contentEl.querySelector<HTMLElement>(".margen-create-hint");
    if (hint) hint.setText(this.error ? this.error : needsAI && !this.aiAvailable ? "La IA del Mac no está disponible. Puedes usar Revista de estudio sin IA."
      : c.intent.trim() ? "Se aplicarán tus instrucciones extra con IA, respetando la redacción elegida y el orden si lo has bloqueado."
      : adaptsContent(c) ? "La IA preparará la redacción y los apoyos elegidos. Revisa la adaptación antes de estudiar; puede tardar unos minutos."
      : c.style === "retro90" ? "Se creará una portada y una carátula retro por nota. Cuantas más notas, mayor tiempo y consumo de IA."
      : c.useAI ? "La IA organizará las secciones conservando el texto de tus notas." : "Se conservará el orden que has elegido, sin llamadas a la IA.");
  }
  private async create() {
    if (this.plugin.busy) return;
    const c = structuredClone(this.plugin.state.composer);
    const language = this.language();
    await this.plugin.run(async () => {
      const chosen = c.paths.map(path => this.app.vault.getAbstractFileByPath(path)).filter((f): f is TFile => f instanceof TFile);
      if (!chosen.length || chosen.length !== c.paths.length) throw new Error("Revisa la selección: falta alguna nota en este equipo.");
      this.progress = "Preparando tus notas…"; this.renderProgress();
      try {
        const prepared = await this.plugin.prepare(chosen);
        const result = await this.plugin.createPublication({
          title: c.title, intent: c.intent, preserve_order: c.preserveOrder, style: c.style, use_ai: needsEditorialAI(c),
          writing_mode: c.writingMode, study_aids: c.studyAids, language,
          artwork: c.style === "retro90" ? "generated" : "none", send_to_kobo: c.sendToKobo, ...prepared,
        }, message => { this.progress = message; this.renderProgress(); });
        this.created = result;
        this.plugin.state.previousComposer = c;
        this.plugin.state.composer = emptyComposer();
        if (c.draftId) void this.plugin.api(`/v1/drafts/${c.draftId}`, undefined, "DELETE").catch(() => undefined);
        await this.plugin.save();
        this.plugin.updateRibbon();
        this.tab = "library"; await this.refresh(true);
        new Notice(`«${result.title}» está lista${c.sendToKobo ? " y en la cola del Kobo" : ""}.`);
      } catch (error) { this.render(); throw error; }
    });
    if (!this.closed && this.tab === "compose") this.render();
  }
  private renderProgress() {
    if (this.closed || !this.page || this.tab !== "compose") return;
    this.page.empty();
    this.heading("TU REVISTA ESTÁ EN MARCHA", "Tus ideas están tomando forma.", "Puedes seguir trabajando o cerrar esta pestaña. El Mac continuará con la edición.");
    const progress = this.page.createDiv({ cls: "margen-progress-card", attr: { role: "status", "aria-live": "polite" } });
    setIcon(progress.createSpan({ cls: "margen-progress-icon" }), "loader-circle");
    progress.createEl("strong", { text: this.progress || "El servidor está preparando la publicación." });
    const actions = progress.createDiv({ cls: "margen-progress-actions" });
    button(actions, "Ver mi biblioteca", () => this.selectTab("library"), "arrow-right");
    button(actions, "Cancelar edición", () => void this.plugin.cancelJob(), "circle-stop");
  }
  private renderStart() {
    this.heading("TU PRÓXIMA LECTURA", "Las notas las eliges tú.", "Empieza una revista nueva o retoma una que dejaste a medias.");
    const start = this.page!.createDiv({ cls: "margen-start" });
    button(start, "Empezar una revista", () => this.plugin.startComposer(), "plus", "margen-primary");
    const previous = this.plugin.state.previousComposer;
    if (previous?.paths.length)
      button(start, `Recuperar la última selección (${previous.paths.length} ${previous.paths.length === 1 ? "nota" : "notas"})`, () => this.plugin.undoComposer(), "undo-2");
    const pending = resumable(this.drafts, this.plugin.state.parked);
    const list = this.page!.createDiv({ cls: "margen-drafts" });
    list.createEl("h2", { text: "Para retomar" });
    if (!pending.length) list.createEl("p", { cls: "margen-hint", text: "Cuando salgas de una revista sin terminarla, aparecerá aquí, en cualquiera de tus equipos." });
    for (const { draft, local } of pending) {
      const row = list.createDiv({ cls: "margen-draft-row" });
      setIcon(row.createSpan(), "bookmark");
      const text = row.createDiv();
      const first = draft.paths[0]?.split("/").pop()?.replace(/\.md$/, "");
      text.createEl("strong", { text: draft.title || (first ? `${first}${draft.paths.length > 1 ? ` y ${draft.paths.length - 1} más` : ""}` : "Una lectura por preparar") });
      text.createEl("small", { text: [`${draft.paths.length} ${draft.paths.length === 1 ? "nota" : "notas"}`, labelStyle(draft.style),
        draft.updated_at ? date(draft.updated_at) : "", local ? "Solo en este equipo" : ""].filter(Boolean).join(" · ") });
      button(row, "Retomar", () => this.plugin.resumeComposer(composerFromDraft(draft)), "arrow-right");
      iconButton(row, "trash-2", "Descartar borrador", () => void this.plugin.run(async () => {
        if (local) { this.plugin.state.parked = undefined; await this.plugin.save(); }
        else await this.plugin.api(`/v1/drafts/${draft.id}`, undefined, "DELETE");
        await this.refresh(true);
        this.render();
      }));
    }
  }
  private renderLibrary() {
    const heading = this.page!.createDiv({ cls: "margen-library-heading" });
    this.heading("", "Lecturas para llevar.", "Tu estantería personal, compartida entre equipos.", heading.createDiv());
    button(heading, "Nueva revista", () => { this.plugin.startComposer(); this.selectTab("compose"); }, "plus", "margen-primary");
    if (this.created) {
      const notice = this.page!.createDiv({ cls: "margen-success" });
      setIcon(notice.createSpan(), "circle-check");
      notice.createSpan({ text: `Ya está lista: ${this.created.title}` });
      button(notice, "Ver portada e índice", () => this.plugin.preview(this.created!));
    }
    this.renderJobs();
    const toolbar = this.page!.createDiv({ cls: "margen-library-toolbar" });
    const search = toolbar.createEl("input", { type: "search", placeholder: "Buscar una lectura…", attr: { "aria-label": "Buscar en la biblioteca" } });
    search.value = this.libraryQuery;
    const filter = toolbar.createEl("select", { attr: { "aria-label": "Filtrar publicaciones" } });
    for (const [value, text] of [["available", "Disponibles"], ["pinned", "Conservadas"], ["all", "Todo el historial"]]) filter.createEl("option", { value, text });
    filter.value = this.libraryFilter;
    const grid = this.page!.createDiv({ cls: "margen-books" });
    const render = () => {
      grid.empty();
      const publications = (this.library?.publications || []).filter(p => matchesSearch(p.title, p.subtitle, this.libraryQuery) && (this.libraryFilter === "all" || this.libraryFilter === "pinned" && p.pinned || this.libraryFilter === "available" && p.available !== false));
      for (const p of publications.slice(0, this.visibleBooks)) this.bookCard(grid, p);
      if (!publications.length) this.emptyState(grid, this.error ? "No podemos abrir la biblioteca." : "Aquí irán tus próximas lecturas.", this.error || "Prepara tu primera revista o cambia el filtro.");
      if (publications.length > this.visibleBooks) button(grid, "Mostrar más publicaciones", () => { this.visibleBooks += 24; render(); });
    };
    search.oninput = () => { this.libraryQuery = search.value; render(); };
    filter.onchange = () => { this.libraryFilter = filter.value; render(); };
    render();
  }
  private bookCard(parent: HTMLElement, p: Publication) {
    const card = parent.createEl("article", { cls: "margen-book-card" });
    const cover = card.createEl("button", { cls: "margen-book-cover", attr: { type: "button", "aria-label": `Ver ${p.title}` } });
    const placeholder = cover.createDiv({ cls: `margen-cover-placeholder ${p.style || "study"}` });
    placeholder.createSpan({ text: "PRELO" }); placeholder.createEl("strong", { text: p.title });
    cover.onclick = () => this.plugin.preview(p);
    cover.disabled = p.available === false;
    if (p.available !== false) void this.loadCover(p.id).then(url => {
      if (!url || !cover.isConnected || this.closed) return;
      placeholder.remove();
      cover.createEl("img", { attr: { src: url, alt: `Portada de ${p.title}`, loading: "lazy" } });
    });
    const copy = card.createDiv({ cls: "margen-book-copy" });
    copy.createEl("small", { text: `${labelStyle(p.style)} · ${date(p.created_at)}` });
    copy.createEl("h2", { text: p.title });
    const state = deliveryState(p);
    const status = copy.createSpan({ text: `${p.pinned ? "★ " : ""}${state.text}`, cls: `margen-book-status ${state.tone}` });
    if (p.on_kobo === "not_imported") status.title = "Desconecta el cable y espera a que el Kobo termine de importar. Si sigue sin aparecer, el lector no ha podido abrir este EPUB.";
    if (p.available === false) return;
    const actions = copy.createDiv({ cls: "margen-book-actions" });
    const queued = ["queued", "transferring"].includes(p.delivery || "");
    button(actions, this.tab === "queue" ? "Ver lectura" : queued ? "Ver cola" : state.resend ? "Volver a enviar" : "Enviar al Kobo",
      () => this.tab === "queue" ? this.plugin.preview(p) : queued ? this.selectTab("queue") : void this.act(p, "queue"),
      this.tab === "queue" ? "book-open" : queued ? "check" : "send");
    iconButton(actions, "ellipsis", `Opciones de ${p.title}`, event => {
      const menu = new Menu();
      menu.addItem(item => item.setTitle("Ver portada e índice").setIcon("book-open").onClick(() => this.plugin.preview(p)));
      menu.addItem(item => item.setTitle(p.pinned ? "Dejar de conservar" : "Conservar esta edición").setIcon("star").onClick(() => void this.act(p, p.pinned ? "unpin" : "pin")));
      menu.addItem(item => item.setTitle("Guardar EPUB en el vault").setIcon("download").onClick(() => void this.plugin.run(async () => { new Notice("Guardado en " + await this.plugin.saveEpub(p)); })));
      if (queued) menu.addItem(item => item.setTitle("Quitar de la cola").setIcon("list-minus").onClick(() => void this.act(p, "cancel")));
      menu.addSeparator();
      menu.addItem(item => item.setTitle("Eliminar EPUB").setIcon("trash-2")
        .setDisabled(p.delivery === "transferring")
        .onClick(() => this.confirmDelete(p)));
      const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
      menu.showAtPosition({ x: box.left, y: box.bottom });
    });
  }
  private confirmDelete(p: Publication) {
    const modal = new Modal(this.app);
    modal.setTitle("Eliminar EPUB");
    modal.contentEl.createEl("p", { text: `Se eliminará «${p.title}» de los archivos disponibles y de la cola de envío. Para volver a tener el EPUB tendrás que generar otra edición o recuperarlo de una copia.` });
    modal.contentEl.createEl("p", { text: "Se conservan tus notas, subrayados y el historial de la edición. Las copias que ya tengas en el Kobo o en el vault no se eliminan." });
    if (p.pinned) modal.contentEl.createEl("p", { text: "Esta edición está marcada como conservada. Al eliminarla también se quitará esa protección." });
    const actions = modal.contentEl.createDiv({ cls: "margen-book-actions" });
    const cancel = button(actions, "Cancelar", () => modal.close());
    button(actions, "Eliminar EPUB", () => {
      modal.close();
      void this.act(p, "delete");
    }, "trash-2", "mod-warning");
    this.plugin.showModal(modal);
    cancel.focus();
  }
  private async loadCover(id: string) {
    if (this.covers.has(id)) return this.covers.get(id);
    try {
      const result = await this.plugin.api(`/v1/publications/${id}/cover`);
      if (this.closed) return;
      if (this.covers.has(id)) return this.covers.get(id);
      const url = URL.createObjectURL(new Blob([result.arrayBuffer], { type: "image/svg+xml" }));
      this.covers.set(id, url); return url;
    } catch { return; }
  }
  private renderQueue() {
    this.heading("DEL MAC A TU KOBO", "Preparado para la próxima conexión.", "El Mac recoge tus subrayados y te entrega las lecturas pendientes.");
    const device = this.library?.device;
    const online = !!device?.heartbeat_at && Date.now() - Date.parse(device.heartbeat_at) < 45000;
    const status = this.page!.createDiv({ cls: "margen-device-card" });
    setIcon(status.createSpan({ cls: "margen-device-icon" }), "tablet");
    const copy = status.createDiv();
    copy.createEl("h2", { text: !online ? "El conector del Mac no responde" : device?.state === "working" ? "Sincronizando tu Kobo" : device?.state === "ready" ? "Todo al día" : device?.state === "error" ? "Hay algo que revisar" : "Conecta el Kobo al Mac" });
    copy.createEl("p", { text: !online ? this.error || "Comprueba que el Mac esté encendido y conectado." : device?.message || "" });
    if (device?.last_sync) copy.createEl("small", { text: `Última sincronización: ${date(device.last_sync.at)} · ${device.last_sync.added} subrayados nuevos · ${device.last_sync.sent} ${device.last_sync.sent === 1 ? "revista copiada" : "revistas copiadas"}.` });
    button(status, "Sincronizar", () => void this.plugin.run(async () => { await this.plugin.api("/v1/device/sync", {}); new Notice("Solicitud enviada al Mac."); await this.refresh(true); }), "refresh-cw");
    const pending = (this.library?.publications || []).filter(p => ["queued", "transferring"].includes(p.delivery || ""));
    this.page!.createEl("h2", { text: `${pending.length} ${pending.length === 1 ? "lectura pendiente" : "lecturas pendientes"}` });
    const grid = this.page!.createDiv({ cls: "margen-books" });
    for (const p of pending) this.bookCard(grid, p);
    if (!pending.length) this.emptyState(grid, "Tu cola está al día.", "Añade una lectura desde la biblioteca. No necesitas tener el Kobo conectado para prepararla.");
    if (this.library) {
      const storage = this.page!.createDiv({ cls: "margen-storage" });
      storage.createSpan({ text: `Biblioteca · ${size(this.library.storage.used_bytes)} de ${size(this.library.storage.limit_bytes)}` });
      const track = storage.createDiv({ cls: "margen-storage-track" });
      track.createDiv().style.width = `${Math.max(1, Math.min(100, this.library.storage.used_bytes / this.library.storage.limit_bytes * 100))}%`;
      storage.createEl("small", { text: "Las ediciones conservadas y pendientes están protegidas de la limpieza." });
    }
  }
  private renderJobs() {
    const jobs = this.library?.jobs || [];
    const running = jobs.filter(j => ["running", "queued"].includes(j.state));
    if (running.length) {
      const box = this.page!.createDiv({ cls: "margen-jobs", attr: { role: "status", "aria-live": "polite" } });
      for (const job of running) box.createEl("p", { text: job.message });
    }
    const failed = jobs.filter(j => j.state === "failed").slice(0, 3);
    if (failed.length) {
      const details = this.page!.createEl("details", { cls: "margen-job-history" });
      details.createEl("summary", { text: "Intentos anteriores que no terminaron" });
      for (const job of failed) details.createEl("p", { text: `${date(job.updated_at)} · ${job.message}` });
    }
  }
  private async act(p: Publication, action: string) {
    await this.plugin.run(async () => {
      await this.plugin.api(`/v1/publications/${p.id}/action`, { action });
      if (action === "delete") {
        const cover = this.covers.get(p.id);
        if (cover) URL.revokeObjectURL(cover);
        this.covers.delete(p.id);
        new Notice("EPUB eliminado. Subrayados e historial conservados.");
      }
      await this.refresh(true);
      if (action === "queue") new Notice("En cola. La recibirás al conectar el Kobo al Mac.");
    });
  }
  private emptyState(parent: HTMLElement, title: string, description: string) {
    const empty = parent.createDiv({ cls: "margen-empty-state" });
    setIcon(empty.createSpan(), this.error ? "wifi-off" : "book-open");
    empty.createEl("h3", { text: title }); empty.createEl("p", { text: description });
    if (this.error) button(empty, "Volver a conectar", () => void this.refresh(true), "refresh-cw");
  }
}
