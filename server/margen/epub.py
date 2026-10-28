"""EPUB 3 reflowable. Every source keeps its own XHTML and stable provenance."""
import base64
import hashlib
import html
import io
import re
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from lxml import etree, html as lhtml
from markdown_it import MarkdownIt
from PIL import Image, ImageDraw
from .models import PublicationRequest, EditorialPlan
from .design import cover_jpeg, cover_svg, opener_jpeg

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
p.figure { text-align:center; text-indent:0; margin:1em 0; page-break-inside:avoid; }
p, li { orphans:2; widows:2; }
.article + .article { margin-top:2.5em; padding-top:1em; border-top:1px solid #aaa; }
body.opener-page { margin:0; padding:0; }
.opener { margin:0; padding:0; text-align:center; }
.opener img { display:block; width:100%; height:auto; margin:0 auto; }
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
.retro90 p.retro-figure { font-family:sans-serif; font-size:0.8em; line-height:1.4; text-align:center; text-indent:0; margin:1.2em 0; page-break-inside:avoid; }
.retro90 p.retro-figure img { max-width:100%; height:auto; }
.retro90 .retro-label { color:#b82c22; font-weight:bold; letter-spacing:0.1em; }
.retro90 .article-meta { font-family:sans-serif; font-size:0.75em; color:#455563; margin-bottom:1.5em; }
"""


LABELS = {
    "es": {"cover": "Portada", "aids": "Apoyos de estudio · IA", "illustration": "Ilustración",
           "adapted": "Texto adaptado con IA a partir de la nota original.", "issue": "En este número",
           "toc": "Índice", "image": "Imagen", "no_description": "sin descripción"},
    "gl": {"cover": "Portada", "aids": "Apoios de estudo · IA", "illustration": "Ilustración",
           "adapted": "Texto adaptado con IA a partir da nota orixinal.", "issue": "Neste número",
           "toc": "Índice", "image": "Imaxe", "no_description": "sen descrición"},
}
# Below roughly one e-reader page of text a note shares its file with its
# neighbours instead of opening a new, mostly blank page.
SHORT_NOTE = 1500


# Alt texts that only say "an image" make no caption.
GENERIC_ALT = re.compile(r"^(esquema o captura|imagen|imaxe|image|captura|esquema|figura)?$|\.(png|jpe?g|gif|webp)$", re.I)
PIXEL_WIDTH = 640
# Kobo Libra Colour, portrait.
SCREEN_WIDTH = 1264


def lossless_png(raw: bytes) -> bytes:
    """WebP is not reliably shown by e-reader engines; PNG keeps every pixel."""
    with Image.open(io.BytesIO(raw)) as image:
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def retro_image(raw: bytes, media_type: str):
    """Revista 90's: the original picture inside a bevelled 16-bit console frame painted
    around it. Small pictures first grow by a whole factor with nearest neighbour, so the
    reader shows crisp pixels instead of a blur; wider ones narrow to the reader's screen.
    Animated GIFs stay as they are."""
    if media_type == "image/gif":
        return raw, media_type
    with Image.open(io.BytesIO(raw)) as source:
        source.load()
        picture = source.convert("RGB")
    upscaled = picture.width < PIXEL_WIDTH
    if upscaled:
        factor = min(4, -(-PIXEL_WIDTH // picture.width))
        picture = picture.resize((picture.width * factor, picture.height * factor), Image.NEAREST)
    elif picture.width > SCREEN_WIDTH:
        picture = picture.resize((SCREEN_WIDTH, max(1, round(picture.height * SCREEN_WIDTH / picture.width))), Image.LANCZOS)
    mat, bevel = frame_sizes(picture.width)
    edge = mat + bevel
    framed = Image.new("RGB", (picture.width + 2 * edge, picture.height + 2 * edge), "#fffdf7")
    w, h = framed.size
    draw = ImageDraw.Draw(framed)
    # Light top-left and dark bottom-right faces, like a raised 16-bit button.
    draw.polygon([(0, 0), (w, 0), (w - bevel, bevel), (bevel, bevel), (bevel, h - bevel), (0, h)], fill="#6fd0c4")
    draw.polygon([(w, 0), (w, h), (0, h), (bevel, h - bevel), (w - bevel, h - bevel), (w - bevel, bevel)], fill="#053c60")
    draw.rectangle([0, 0, w - 1, h - 1], outline="#021d2e", width=max(1, bevel // 4))
    framed.paste(picture, (edge, edge))
    output = io.BytesIO()
    if media_type == "image/jpeg" and not upscaled:
        framed.save(output, format="JPEG", quality=92, optimize=True)
        return output.getvalue(), "image/jpeg"
    framed.save(output, format="PNG", optimize=True)
    if framed.getcolors(256) is None:
        # Screenshots and photos: a 256-colour palette usually weighs far less.
        palette = io.BytesIO()
        framed.quantize(256, method=Image.Quantize.MEDIANCUT).save(palette, format="PNG", optimize=True)
        if palette.tell() < output.tell():
            output = palette
    return output.getvalue(), "image/png"


def frame_sizes(width: int):
    """(mat, bevel) in pixels around a picture of this width."""
    return max(6, round(width * 0.025)), max(6, round(width * 0.02))


def retro_frames(body: str) -> str:
    """Revista 90's: a figure number under each note image, in the same paragraph so that
    image and label are one unbreakable two-line block (orphans and widows of 2)."""
    content = lhtml.fragment_fromstring(body or "<p/>", create_parent="div")
    for number, node in enumerate(content.xpath(".//p[@class='figure']"), 1):
        node.set("class", "retro-figure")
        alt = (node[0].get("alt") or "").strip()
        node[0].tail = None
        etree.SubElement(node, "br")
        label = etree.SubElement(node, "span")
        label.set("class", "retro-label")
        label.text = f"FIG. {number:02d}"
        if not GENERIC_ALT.search(alt):
            label.tail = " · " + alt
    return "".join(etree.tostring(n, encoding="unicode", method="xml") for n in content)


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


def render_note(source, hrefs, assets, warnings, labels=LABELS["es"]):
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
            node.text = f"[{labels['image']}: " + node.get("alt", labels["no_description"]) + "]"
            node.attrib.clear()
    for node in fragment.xpath(".//p[img]"):
        if len(node) == 1 and not (node.text or "").strip() and not (node[0].tail or "").strip():
            node.set("class", "figure")
    for node in fragment.xpath(".//a"):
        href = node.get("href", "")
        target = href.removeprefix("margen-note:").split("#")[0]
        if href.startswith("margen-note:") and target in hrefs:
            node.set("href", hrefs[target])
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
    assets = {}
    cover_art = next((v for v in illustrations if v["placement"] == "cover"), None)
    preview = cover_svg(plan, now.date().isoformat(), request.style, cover_art, request.language)
    # Revista 90's carries its cover as a picture; the SVG stays as the library preview.
    if request.style == "retro90":
        cover_file, cover_type = "cover.jpg", "image/jpeg"
        cover = cover_jpeg(plan, now.date().isoformat(), cover_art, request.language)
    else:
        cover_file, cover_type, cover = "cover.svg", "image/svg+xml", preview
    files = {"EPUB/style.css": CSS, "EPUB/" + cover_file: cover}
    manifest_items = [
        ("css", "style.css", "text/css", ""),
        ("cover-image", cover_file, cover_type, "cover-image"),
        ("cover", "text/cover.xhtml", "application/xhtml+xml", ""),
        ("nav", "text/nav.xhtml", "application/xhtml+xml", "nav"),
    ]
    files["EPUB/text/cover.xhtml"] = xhtml(plan.title, f'<img src="../{cover_file}" alt="{LABELS[request.language]["cover"]}"/>',
                                           "cover", request.language)
    for asset in request.assets:
        data, media_type = base64.b64decode(asset.data), asset.media_type
        if media_type == "image/webp":
            data, media_type = lossless_png(data), "image/png"
        if request.style == "retro90":
            data, media_type = retro_image(data, media_type)
        assets[asset.id] = asset.id + "." + extensions[media_type]
        files["EPUB/assets/" + assets[asset.id]] = data
        manifest_items.append(("a_" + asset.id, "assets/" + assets[asset.id], media_type, ""))
    labels = LABELS[request.language]
    openers = {}
    for illustration in illustrations:
        source_id = illustration["source_ids"][0]
        if illustration["placement"] == "inside" and not illustration.get("anchor_heading") and source_id not in openers:
            openers[source_id] = illustration
    for illustration in illustrations:
        # Opening art only appears composed into its opener page.
        if illustration["placement"] == "cover" or illustration in openers.values():
            continue
        image_file = "art/" + illustration["id"] + ".jpg"
        files["EPUB/" + image_file] = base64.b64decode(illustration["data"], validate=True)
        manifest_items.append(("art_" + illustration["id"], image_file, "image/jpeg", ""))
    entries = []
    for index, chapter in enumerate(plan.chapters, 1):
        for source_id in chapter.source_ids:
            note = notes[source_id]
            article = articles.get(source_id)
            reading = note.model_copy(update={"markdown": article.markdown}) if article and request.writing_mode != "original" else note
            text = clean_markdown(reading.markdown) + (article.aids if article else "")
            short = (source_id not in openers and "margen-asset:" not in text and len(text) < SHORT_NOTE
                     and not any(v["source_ids"][0] == source_id for v in illustrations if v["placement"] == "inside"))
            # Rewritten articles may carry a title in the edition's language.
            shown = article.title.strip() if article and article.title.strip() and request.writing_mode != "original" else note.title
            entries.append({"index": index, "chapter": chapter, "id": source_id, "note": note, "title": shown,
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
            body, plain = render_note(entry["reading"], hrefs, assets, warnings, labels)
            if article and article.aids:
                aid_note = note.model_copy(update={"id": note.id + "_aids", "markdown": article.aids})
                aids_body, aids_plain = render_note(aid_note, hrefs, assets, warnings, labels)
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
            if request.style == "retro90":
                body = retro_frames(body)
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
                            f'<h1>{html.escape(entry["title"])}</h1>{head}{body}</div>')
            if source_id in openers:
                opener, picture = f"text/o_{source_id}.xhtml", f"art/o_{source_id}.jpg"
                files["EPUB/" + picture] = opener_jpeg(eyebrow, entry["title"], base64.b64decode(openers[source_id]["data"], validate=True))
                manifest_items.append(("art_o_" + source_id, picture, "image/jpeg", ""))
                files["EPUB/" + opener] = xhtml(entry["title"], f'<div class="opener"><img src="../{picture}" alt="{html.escape(entry["title"], quote=True)}"/></div>',
                    request.style + " opener-page", request.language)
                manifest_items.append(("o_" + source_id, opener, "application/xhtml+xml", ""))
                spine.append("o_" + source_id)
            source_map.append({
                "id": note.id, "path": note.path, "title": note.title, "href": "text/" + files_of[source_id],
                "anchor": f"n_{source_id}",
                "sha256": note.original_sha256 or hashlib.sha256(note.markdown.encode()).hexdigest(),
                "text": plain, "chapter": chapter.title, "adapted": request.writing_mode != "original",
            })
            target = opener_hrefs.get(source_id, hrefs[source_id])
            toc.setdefault(id(chapter), [chapter.title, target, []])[2].append(
                f'<li><a href="{target}">{html.escape(entry["title"])}</a></li>')
        href = "text/" + files_of[group[0]["id"]]
        files["EPUB/" + href] = xhtml(group[0]["title"], "".join(sections), request.style, request.language)
        manifest_items.append(("n_" + group[0]["id"], href, "application/xhtml+xml", ""))
        spine.append("n_" + group[0]["id"])
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
    (directory / "cover.svg").write_text(preview)
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
