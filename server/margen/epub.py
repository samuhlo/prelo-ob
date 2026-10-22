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
from .design import cover_svg

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
.source { border-top:2px solid #c3b59d; padding-top:1em; font-size:0.8em; margin-top:2em; }
.cover { margin:0; text-align:center; }
.cover img { width:100%; max-height:100%; }
img { max-width:100%; height:auto; }
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


def clean_markdown(text):
    text = text.lstrip("\ufeff")
    if text.startswith("---\n") or text.startswith("---\r\n"):
        text = re.sub(r"\A---\r?\n.*?\r?\n---(?:\r?\n|$)", "", text, count=1, flags=re.S)
    return text


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", text).split()).casefold()


def xhtml(title, body, body_class=""):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="{XHTML}" xmlns:epub="{EPUB}" lang="es" xml:lang="es">
<head><title>{html.escape(title)}</title><link rel="stylesheet" type="text/css" href="../style.css"/></head>
<body class="{body_class}">{body}</body></html>"""


def render_note(source, notes, assets, warnings):
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
        if src.startswith("margen-asset:") and asset_id in assets:
            node.set("src", "../assets/" + assets[asset_id])
        else:
            warnings.append(f"{source.path}: imagen no incluida ({src[:120]}).")
            node.tag = "span"
            node.text = "[Imagen: " + node.get("alt", "sin descripción") + "]"
            node.attrib.clear()
    for node in fragment.xpath(".//a"):
        href = node.get("href", "")
        target = href.removeprefix("margen-note:").split("#")[0]
        if href.startswith("margen-note:") and target in notes:
            node.set("href", f"n_{target}.xhtml")
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
    files = {"EPUB/style.css": CSS, "EPUB/cover.svg": cover_svg(plan, now.date().isoformat(), request.style, cover_art)}
    manifest_items = [
        ("css", "style.css", "text/css", ""),
        ("cover-image", "cover.svg", "image/svg+xml", "cover-image"),
        ("cover", "text/cover.xhtml", "application/xhtml+xml", ""),
        ("nav", "text/nav.xhtml", "application/xhtml+xml", "nav"),
    ]
    files["EPUB/text/cover.xhtml"] = xhtml(plan.title, '<img src="../cover.svg" alt="Portada"/>', "cover")
    for asset in request.assets:
        files["EPUB/assets/" + assets[asset.id]] = base64.b64decode(asset.data)
        manifest_items.append(("a_" + asset.id, "assets/" + assets[asset.id], asset.media_type, ""))
    for illustration in illustrations:
        if illustration["placement"] == "cover":
            continue
        image_file = "art/" + illustration["id"] + ".jpg"
        files["EPUB/" + image_file] = base64.b64decode(illustration["data"], validate=True)
        manifest_items.append(("art_" + illustration["id"], image_file, "image/jpeg", ""))
    source_map, spine, toc = [], ["cover", "nav"], []
    for index, chapter in enumerate(plan.chapters, 1):
        subitems = []
        for source_id in chapter.source_ids:
            note = notes[source_id]
            article = articles.get(source_id)
            reading_note = note.model_copy(update={"markdown": article.markdown}) if article and request.writing_mode != "original" else note
            body, plain = render_note(reading_note, notes, assets, warnings)
            if article and article.aids:
                aid_note = note.model_copy(update={"id": note.id + "_aids", "markdown": article.aids})
                aids_body, aids_plain = render_note(aid_note, notes, assets, warnings)
                body += '<div class="study-aids"><h2>Apoyos de estudio · IA</h2>' + aids_body + '</div>'
                plain += " " + aids_plain
            if request.writing_mode != "original":
                body = '<p class="article-meta">Texto adaptado con IA a partir de la nota original.</p>' + body
            relevant = [v for v in illustrations if v["placement"] == "inside" and v["source_ids"][0] == source_id]
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
                        f'Ilustración: {html.escape(visual["caption"] or visual["concept"])}</p></div></div>')
                    heading = next((h for h in content.xpath(".//h1 | .//h2 | .//h3")
                                    if normalize(h.text_content()) == normalize(visual.get("anchor_heading", ""))), None)
                    if heading is not None:
                        heading.addnext(figure)
                    else:
                        content.insert(0, figure)
                body = "".join(etree.tostring(n, encoding="unicode", method="xml") for n in content)
            href = f"text/n_{source_id}.xhtml"
            files["EPUB/" + href] = xhtml(note.title,
                f'<p class="eyebrow">{index:02d} / {html.escape(chapter.title)}</p>'
                f'<h1>{html.escape(note.title)}</h1>{body}'
                f'<p class="source">Fuente: {html.escape(note.title)}</p>', request.style)
            manifest_items.append(("n_" + source_id, href, "application/xhtml+xml", ""))
            spine.append("n_" + source_id)
            subitems.append(f'<li><a href="n_{source_id}.xhtml">{html.escape(note.title)}</a></li>')
            source_map.append({
                "id": note.id, "path": note.path, "title": note.title, "href": href,
                "sha256": note.original_sha256 or hashlib.sha256(note.markdown.encode()).hexdigest(),
                "text": plain, "chapter": chapter.title, "adapted": request.writing_mode != "original",
            })
        toc.append(f'<li><a href="n_{chapter.source_ids[0]}.xhtml">{html.escape(chapter.title)}</a>'
                   + "<ol>" + "".join(subitems) + "</ol></li>")
    files["EPUB/text/nav.xhtml"] = xhtml("Índice",
        f'<p class="eyebrow">En este número</p><h1>{html.escape(plan.title)}</h1>'
        f'<p>{html.escape(plan.subtitle)}</p><nav epub:type="toc" id="toc"><h2>Índice</h2><ol>'
        + "".join(toc) + "</ol></nav>", request.style)
    package = etree.Element(f"{{{OPF}}}package", nsmap={None: OPF}, version="3.0",
                            attrib={"unique-identifier": "pub-id", "xml:lang".replace("xml:", "{http://www.w3.org/XML/1998/namespace}"): "es"})
    metadata = etree.SubElement(package, "metadata", nsmap={"dc": DC})
    for name, value in [("identifier", "urn:uuid:" + edition_id), ("title", plan.title), ("language", "es"), ("creator", "Prelo")]:
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
        "preserve_order": request.preserve_order,
        "ai_used": request.use_ai or bool(illustrations), "plan": plan.model_dump(), "sources": source_map,
        "artwork": [{k: v.get(k) for k in ["id", "placement", "source_ids", "concept", "description", "caption", "anchor_heading", "cache_hit"]}
                    for v in illustrations],
        "warnings": list(dict.fromkeys(warnings)),
    }
