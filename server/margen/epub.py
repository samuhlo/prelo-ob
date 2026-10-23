"""EPUB 3 reflowable. Every source keeps its own XHTML and stable provenance."""
import base64
import hashlib
import html
import re
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from lxml import etree, html as lhtml
from markdown_it import MarkdownIt
from .models import PublicationRequest, EditorialPlan
from .design import cover_svg, opener_svg
from .diagrams import render_diagram
from .figures import apply_figures

XHTML = "http://www.w3.org/1999/xhtml"
EPUB = "http://www.idpf.org/2007/ops"
OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
MD = MarkdownIt("commonmark", {"html": False, "breaks": False, "xhtmlOut": True}).enable("table")
CSS = """
body { font-family:serif; line-height:1.5; margin:5%; color:#1b2426; }
h1,h2,h3,.eyebrow,.source { font-family:sans-serif; line-height:1.2; }
h1,h2,h3 { page-break-inside:avoid; page-break-after:avoid; }
h1 { font-size:2em; margin:0.3em 0 0.7em; }
h2 { font-size:1.35em; margin-top:1.5em; }
.eyebrow { color:#a33d27; text-transform:uppercase; letter-spacing:0.12em; font-size:0.8em; }
.cover { margin:0; text-align:center; }
.cover img { width:100%; max-height:100%; }
img { max-width:100%; height:auto; }
p.figure { text-align:center; text-indent:0; margin:1em 0 0.3em; page-break-inside:avoid; }
img.diagram { width:100%; }
p.figure-caption { font-family:sans-serif; font-size:0.85em; text-align:center; text-indent:0; margin:0 0 1.2em; page-break-before:avoid; }
.original { margin-bottom:2em; page-break-inside:avoid; }
p, li { orphans:2; widows:2; }
.article + .article { margin-top:2.5em; padding-top:1em; border-top:1px solid #aaa; }
body.opener-page { margin:0; padding:0; }
.opener { margin:0; padding:0; text-align:center; height:100%; }
.opener svg { display:block; width:100%; height:100%; }
blockquote { border-left:3px solid #a33d27; margin:1em 0; padding:0.3em 1em; }
pre { font-size:0.8em; white-space:pre-wrap; overflow-wrap:anywhere; padding:0.8em; border:1px solid #b7b7b7; }
code { font-family:monospace; overflow-wrap:anywhere; }
table { border-collapse:collapse; width:100%; font-size:0.85em; }
td,th { border-bottom:1px solid #aaa; padding:0.4em; text-align:left; }
a { color:inherit; } hr { border:0; border-top:1px solid #aaa; }
.study-aids { border-top:2px solid #777; margin-top:2em; padding-top:1em; }
body.study { font-family:sans-serif; line-height:1.6; }
.study h2 { border-bottom:1px solid #94b4b4; padding-bottom:0.35em; }
.study .eyebrow { color:#256c70; }
.study blockquote { border-left-color:#256c70; }
body.retro90 { font-family:sans-serif; color:#16272e; background:#fffdf7; line-height:1.5; }
.retro90 h1 { font-family:sans-serif; color:#053c60; text-transform:uppercase; font-weight:bold; border-bottom:0.18em solid #31a99d; padding-bottom:0.35em; }
.retro90 h2 { font-family:sans-serif; color:#b82c22; border:0; padding:0; }
.retro90 h3 { color:#245d31; }
.retro90 .eyebrow { display:block; background:#b8e4da; color:#053c60; font-weight:bold; padding:0.6em 0.75em; letter-spacing:0.025em; }
.retro90 blockquote { background:#eee8f5; border:0; border-left:0.3em solid #593577; padding:0.7em; }
.retro90 pre { background:#edf5ed; border:1px solid #508b65; }
.retro90 th { background:#0d6669; color:#fff; }
.retro90 nav > ol > li { margin-bottom:1.2em; padding-left:0.25em; }
.retro90 nav > ol > li > a { color:#053c60; font-weight:bold; }
.illustration { display:block; margin:1.5em 0; padding:0; height:auto; }
.illustration-image { display:block; margin:0; padding:0; page-break-inside:avoid; }
.illustration-image img { display:block; max-width:100%; width:100%; height:auto; margin:0 auto; border:0; }
.illustration-caption-box { display:block; clear:both; height:auto; page-break-inside:avoid; margin:0.25em 0 0; padding:0.65em 0.75em; background:#eef7f1; border-left:0.25em solid #31a99d; }
p.illustration-caption { display:block; height:auto; font-family:sans-serif; font-size:1em; line-height:1.5em; margin:0; padding:0; text-indent:0; text-align:left; white-space:normal; }
.retro90 .article-meta { font-family:sans-serif; font-size:0.75em; color:#455563; margin-bottom:1.5em; }
"""


LABELS = {
    "es": {"cover": "Portada", "aids": "Apoyos de estudio · IA", "illustration": "Ilustración",
           "adapted": "Texto adaptado con IA a partir de la nota original.", "issue": "En este número",
           "toc": "Índice", "image": "Imagen", "no_description": "sin descripción",
           "originals": "Imágenes originales"},
    "gl": {"cover": "Portada", "aids": "Apoios de estudo · IA", "illustration": "Ilustración",
           "adapted": "Texto adaptado con IA a partir da nota orixinal.", "issue": "Neste número",
           "toc": "Índice", "image": "Imaxe", "no_description": "sen descrición",
           "originals": "Imaxes orixinais"},
}
# Below roughly one e-reader page of text a note shares its file with its
# neighbours instead of opening a new, mostly blank page.
SHORT_NOTE = 1500


def clean_markdown(text):
    text = text.lstrip("\ufeff")
    if text.startswith("---\n") or text.startswith("---\r\n"):
        text = re.sub(r"\A---\r?\n.*?\r?\n---(?:\r?\n|$)", "", text, count=1, flags=re.S)
    return text


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", text).split()).casefold()


def xhtml(title, body, body_class="", language="es"):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="{XHTML}" xmlns:epub="{EPUB}" lang="{language}" xml:lang="{language}">
<head><title>{html.escape(title)}</title><link rel="stylesheet" type="text/css" href="../style.css"/></head>
<body class="{body_class}">{body}</body></html>"""


def render_note(source, hrefs, assets, warnings, labels=LABELS["es"], figures=frozenset()):
    text = clean_markdown(source.markdown)
    # Legacy/unresolved wiki references remain readable, and are reported.
    def wiki(match):
        target = match.group(2).split("|", 1)
        warnings.append(f"{source.path}: referencia sin resolver «{target[0]}».")
        return target[-1]
    tokens = MD.parse(text)
    # Modify text tokens only; fenced code, inline code, and URLs are not wiki links.
    for token in tokens:
        for child in token.children or []:
            if child.type == "text":
                child.content = re.sub(r"(!?)\[\[([^\]]+)\]\]", wiki, child.content)
    fragment = lhtml.fragment_fromstring(MD.renderer.render(tokens, MD.options, {}), create_parent="div")
    if len(fragment) and fragment[0].tag == "h1" and normalize(fragment[0].text_content()) == normalize(source.title):
        fragment.remove(fragment[0])
    for node in fragment.xpath(".//img"):
        src = node.get("src", "")
        asset_id = src.removeprefix("margen-asset:")
        figure_id = src.removeprefix("margen-figure:")
        if src.startswith("margen-asset:") and asset_id in assets:
            node.set("src", "../assets/" + assets[asset_id])
        elif src.startswith("margen-figure:") and figure_id in figures:
            node.set("src", f"../figures/{figure_id}.svg")
            node.set("class", "diagram")
        else:
            warnings.append(f"{source.path}: imagen no incluida ({src[:120]}).")
            node.tag = "span"
            node.text = f"[{labels['image']}: " + node.get("alt", labels["no_description"]) + "]"
            node.attrib.clear()
    for node in fragment.xpath(".//p[img]"):
        if len(node) == 1 and not (node.text or "").strip() and not (node[0].tail or "").strip():
            node.set("class", "figure")
            caption = node.getnext()
            if caption is not None and caption.tag == "p" and len(caption) and caption[0].tag == "em" \
                    and not (caption.text or "").strip():
                caption.set("class", "figure-caption")
    for node in fragment.xpath(".//a"):
        href = node.get("href", "")
        target = href.removeprefix("margen-note:").split("#")[0]
        original = href.removeprefix("margen-original:")
        if href.startswith("margen-note:") and target in hrefs:
            node.set("href", hrefs[target])
        elif href.startswith("margen-original:") and original in assets:
            node.set("href", f"originales.xhtml#o_{original}")
        elif not href.startswith(("https://", "http://", "mailto:")):
            node.tag = "span"
            node.attrib.clear()
            warnings.append(f"{source.path}: enlace local sin destino exportado ({href[:120]}).")
    for i, node in enumerate(fragment.xpath(".//p | .//h1 | .//h2 | .//h3 | .//li | .//pre")):
        node.set("id", f"b_{source.id}_{i}")
    # lxml serializes HTML entities as actual UTF-8 and void elements as XML.
    body = "".join(etree.tostring(n, encoding="unicode", method="xml") for n in fragment)
    return body, normalize(fragment.text_content())


def build_epub(request: PublicationRequest, plan: EditorialPlan, edition_id: str, directory: Path, illustrations=None):
    plan.verify_visuals(request)
    illustrations = illustrations or []
    if request.artwork == "generated" and {v["id"] for v in illustrations} != {v.id for v in plan.visuals}:
        raise ValueError("Faltan ilustraciones de la edición; no se generará una revista incompleta.")
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    filename = f"margen-{edition_id}.epub"
    warnings = []
    notes = {n.id: n for n in request.notes}
    articles = {a.source_id: a for a in plan.articles}
    extensions = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}
    assets = {a.id: a.id + "." + extensions[a.media_type] for a in request.assets}
    cover_art = next((v for v in illustrations if v["placement"] == "cover"), None)
    files = {"EPUB/style.css": CSS,
             "EPUB/cover.svg": cover_svg(plan, now.date().isoformat(), request.style, cover_art, request.language)}
    manifest_items = [
        ("css", "style.css", "text/css", ""),
        ("cover-image", "cover.svg", "image/svg+xml", "cover-image"),
        ("cover", "text/cover.xhtml", "application/xhtml+xml", ""),
        ("nav", "text/nav.xhtml", "application/xhtml+xml", "nav"),
    ]
    files["EPUB/text/cover.xhtml"] = xhtml(plan.title, f'<img src="../cover.svg" alt="{LABELS[request.language]["cover"]}"/>',
                                           "cover", request.language)
    for asset in request.assets:
        files["EPUB/assets/" + assets[asset.id]] = base64.b64decode(asset.data)
        manifest_items.append(("a_" + asset.id, "assets/" + assets[asset.id], asset.media_type, ""))
    for illustration in illustrations:
        if illustration["placement"] == "cover":
            continue
        image_file = "art/" + illustration["id"] + ".jpg"
        files["EPUB/" + image_file] = base64.b64decode(illustration["data"], validate=True)
        manifest_items.append(("art_" + illustration["id"], image_file, "image/jpeg", ""))
    labels = LABELS[request.language]
    drawn = set()
    for figure in plan.figures:
        svg = render_diagram(figure.diagram, request.style) if figure.action == "diagram" and figure.diagram else None
        if svg:
            files[f"EPUB/figures/{figure.asset_id}.svg"] = svg
            manifest_items.append(("f_" + figure.asset_id, f"figures/{figure.asset_id}.svg", "image/svg+xml", ""))
            drawn.add(figure.asset_id)
    openers = {}
    for illustration in illustrations:
        source_id = illustration["source_ids"][0]
        if illustration["placement"] == "inside" and not illustration.get("anchor_heading") and source_id not in openers:
            openers[source_id] = illustration
    entries = []
    for index, chapter in enumerate(plan.chapters, 1):
        for source_id in chapter.source_ids:
            note = notes[source_id]
            article = articles.get(source_id)
            reading = note.model_copy(update={"markdown": article.markdown}) if article and request.writing_mode != "original" \
                else note.model_copy(update={"markdown": apply_figures(note.markdown, plan.figures, request.language)})
            text = clean_markdown(reading.markdown) + (article.aids if article else "")
            short = (source_id not in openers and "margen-asset:" not in text and len(text) < SHORT_NOTE
                     and not any(v["source_ids"][0] == source_id for v in illustrations if v["placement"] == "inside"))
            entries.append({"index": index, "chapter": chapter, "id": source_id, "note": note,
                            "reading": reading, "article": article, "short": short})
    # Consecutive short notes share one file; each keeps its own anchor and provenance.
    groups = []
    for entry in entries:
        if entry["short"] and groups and groups[-1][0]["short"]:
            groups[-1].append(entry)
        else:
            groups.append([entry])
    hrefs, files_of = {}, {}
    for group in groups:
        file = f"n_{group[0]['id']}.xhtml"
        for position, entry in enumerate(group):
            files_of[entry["id"]] = file
            hrefs[entry["id"]] = file if position == 0 else f"{file}#n_{entry['id']}"
    opener_hrefs = {source_id: f"o_{source_id}.xhtml" for source_id in openers}
    source_map, spine, toc = [], ["cover", "nav"], {}
    for group in groups:
        sections = []
        for entry in group:
            note, article, chapter, source_id = entry["note"], entry["article"], entry["chapter"], entry["id"]
            body, plain = render_note(entry["reading"], hrefs, assets, warnings, labels, drawn)
            if article and article.aids:
                aid_note = note.model_copy(update={"id": note.id + "_aids", "markdown": article.aids})
                aids_body, aids_plain = render_note(aid_note, hrefs, assets, warnings, labels, drawn)
                body += f'<div class="study-aids"><h2>{labels["aids"]}</h2>' + aids_body + '</div>'
                plain += " " + aids_plain
            relevant = [v for v in illustrations if v["placement"] == "inside" and v["source_ids"][0] == source_id
                        and v is not openers.get(source_id)]
            if relevant:
                content = lhtml.fragment_fromstring(body or "<p/>", create_parent="div")
                for visual in relevant:
                    # Older EPUB engines may treat HTML5 figure/figcaption as inline.
                    # Classic block elements keep each caption's line boxes independent
                    # from padding and allow reader font-size overrides to reflow.
                    figure = lhtml.fragment_fromstring(
                        f'<div class="illustration"><div class="illustration-image">'
                        f'<img src="../art/{visual["id"]}.jpg" alt="{html.escape(visual["concept"], quote=True)}"/></div>'
                        f'<div class="illustration-caption-box"><p class="illustration-caption">'
                        f'{labels["illustration"]}: {html.escape(visual["caption"] or visual["concept"])}</p></div></div>')
                    heading = next((h for h in content.xpath(".//h1 | .//h2 | .//h3")
                                    if normalize(h.text_content()) == normalize(visual.get("anchor_heading", ""))), None)
                    if heading is not None:
                        heading.addnext(figure)
                    else:
                        content.insert(0, figure)
                body = "".join(etree.tostring(n, encoding="unicode", method="xml") for n in content)
            head = ""
            if source_id in openers:
                # The art opens the article on its own page; its caption leads the text.
                visual = openers[source_id]
                head += (f'<div class="illustration-caption-box"><p class="illustration-caption">'
                         f'{labels["illustration"]}: {html.escape(visual["caption"] or visual["concept"])}</p></div>')
            if request.writing_mode != "original":
                head += f'<p class="article-meta">{labels["adapted"]}</p>'
            eyebrow = f'{entry["index"]:02d} / {chapter.title}'
            sections.append(f'<div class="article" id="n_{source_id}"><p class="eyebrow">{html.escape(eyebrow)}</p>'
                            f'<h1>{html.escape(note.title)}</h1>{head}{body}</div>')
            if source_id in openers:
                opener = f"text/o_{source_id}.xhtml"
                files["EPUB/" + opener] = xhtml(note.title, '<div class="opener">'
                    + opener_svg(eyebrow, note.title, f'../art/{openers[source_id]["id"]}.jpg') + '</div>',
                    request.style + " opener-page", request.language)
                manifest_items.append(("o_" + source_id, opener, "application/xhtml+xml", "svg"))
                spine.append("o_" + source_id)
            source_map.append({
                "id": note.id, "path": note.path, "title": note.title, "href": "text/" + files_of[source_id],
                "anchor": f"n_{source_id}",
                "sha256": note.original_sha256 or hashlib.sha256(note.markdown.encode()).hexdigest(),
                "text": plain, "chapter": chapter.title, "adapted": request.writing_mode != "original",
            })
            target = opener_hrefs.get(source_id, hrefs[source_id])
            toc.setdefault(id(chapter), [chapter.title, target, []])[2].append(
                f'<li><a href="{target}">{html.escape(note.title)}</a></li>')
        href = "text/" + files_of[group[0]["id"]]
        files["EPUB/" + href] = xhtml(group[0]["note"].title, "".join(sections), request.style, request.language)
        manifest_items.append(("n_" + group[0]["id"], href, "application/xhtml+xml", ""))
        spine.append("n_" + group[0]["id"])
    replaced = [f for f in plan.figures if f.action == "table" or f.asset_id in drawn]
    replaced = [f for f in replaced if f.asset_id in assets]
    if replaced:
        # Every redrawn or transcribed image stays available for checking.
        files["EPUB/text/originales.xhtml"] = xhtml(labels["originals"], f'<h1>{labels["originals"]}</h1>' + "".join(
            f'<div class="original" id="o_{f.asset_id}"><p class="figure"><img src="../assets/{assets[f.asset_id]}" '
            f'alt="{html.escape(f.description, quote=True)}"/></p>'
            f'<p class="figure-caption">{html.escape(f.caption or f.description)}</p></div>' for f in replaced),
            request.style, request.language)
        manifest_items.append(("originales", "text/originales.xhtml", "application/xhtml+xml", ""))
        spine.append("originales")
        toc[id(replaced)] = [labels["originals"], "originales.xhtml", []]
    files["EPUB/text/nav.xhtml"] = xhtml(labels["toc"],
        f'<p class="eyebrow">{labels["issue"]}</p><h1>{html.escape(plan.title)}</h1>'
        f'<p>{html.escape(plan.subtitle)}</p><nav epub:type="toc" id="toc"><h2>{labels["toc"]}</h2><ol>'
        + "".join(f'<li><a href="{target}">{html.escape(title)}</a>{"<ol>" + "".join(items) + "</ol>" if items else ""}</li>'
                  for title, target, items in toc.values())
        + "</ol></nav>", request.style, request.language)
    package = etree.Element(f"{{{OPF}}}package", nsmap={None: OPF}, version="3.0",
                            attrib={"unique-identifier": "pub-id", "xml:lang".replace("xml:", "{http://www.w3.org/XML/1998/namespace}"): request.language})
    metadata = etree.SubElement(package, "metadata", nsmap={"dc": DC})
    for name, value in [("identifier", "urn:uuid:" + edition_id), ("title", plan.title), ("language", request.language), ("creator", "Prelo")]:
        el = etree.SubElement(metadata, f"{{{DC}}}{name}")
        el.text = value
        if name == "identifier":
            el.set("id", "pub-id")
    etree.SubElement(metadata, "meta", property="dcterms:modified").text = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    etree.SubElement(metadata, "meta", name="cover", content="cover-image")
    manifest = etree.SubElement(package, "manifest")
    for id_, href, mime, properties in manifest_items:
        attrs = {"id": id_, "href": href, "media-type": mime}
        if properties:
            attrs["properties"] = properties
        etree.SubElement(manifest, "item", **attrs)
    spine_el = etree.SubElement(package, "spine")
    for id_ in spine:
        etree.SubElement(spine_el, "itemref", idref=id_)
    files["EPUB/package.opf"] = etree.tostring(package, encoding="utf-8", xml_declaration=True)
    files["META-INF/container.xml"] = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""
    with zipfile.ZipFile(directory / filename, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, value in files.items():
            archive.writestr(name, value, compress_type=zipfile.ZIP_DEFLATED)
    (directory / "cover.svg").write_text(files["EPUB/cover.svg"])
    return {
        "id": edition_id, "filename": filename, "created_at": now.isoformat(),
        "title": plan.title, "subtitle": plan.subtitle, "style": request.style,
        "writing_mode": request.writing_mode, "study_aids": request.study_aids,
        "language": request.language, "preserve_order": request.preserve_order,
        "ai_used": request.use_ai or bool(illustrations), "plan": plan.model_dump(), "sources": source_map,
        "artwork": [{k: v.get(k) for k in ["id", "placement", "source_ids", "concept", "description", "caption", "anchor_heading", "cache_hit"]}
                    for v in illustrations],
        "warnings": list(dict.fromkeys(warnings)),
    }
