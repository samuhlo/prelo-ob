"""Render EPUB captions at several widths/font sizes (MuPDF, not a Kobo emulator).

Run: uv run --with pymupdf python ../scripts/check_caption_layout.py BOOK --output DIR
"""
import argparse
import json
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
import unicodedata
import pymupdf

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("epub", type=Path)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
expected = 0
caption_texts = []
with zipfile.ZipFile(args.epub) as book:
    for name in book.namelist():
        if name.endswith(".xhtml"):
            root = ET.fromstring(book.read(name))
            elements = root.findall(".//{http://www.w3.org/1999/xhtml}p[@class='illustration-caption']")
            expected += len(elements)
            caption_texts += ["".join(p.itertext()) for p in elements]
if not expected:
    raise SystemExit("El EPUB no contiene los párrafos de pie de foto esperados.")

report = []
normalize = lambda text: " ".join(unicodedata.normalize("NFKC", text).split())
for width, height, font in [(400, 600, 16), (400, 600, 24), (600, 800, 28), (600, 800, 36)]:
    doc = pymupdf.open(args.epub)
    doc.layout(width=width, height=height, fontsize=font)
    gaps, caption_pages, rendered_lines = [], set(), []
    rendered = ""
    for page_number, page in enumerate(doc):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = normalize("".join(span["text"] for span in line["spans"]))
                if not text:
                    continue
                start = len(rendered)
                rendered += text + " "
                rendered_lines.append((start, len(rendered) - 1, page_number, line["bbox"]))
    cursor = 0
    for caption in caption_texts:
        text = normalize(caption)
        start = rendered.find(text, cursor)
        if start < 0:
            raise AssertionError(f"Un pie de foto no aparece completo con letra {font}.")
        end = start + len(text)
        selected = [line for line in rendered_lines if line[0] < end and line[1] > start]
        caption_pages.update(line[2] + 1 for line in selected)
        # Include continuations on later pages, even without the caption prefix.
        for first, second in zip(selected, selected[1:]):
            if first[2] != second[2]:
                continue
            gap = second[3][1] - first[3][3]
            if gap < -0.5:
                raise AssertionError(f"Líneas solapadas: página {first[2] + 1}, letra {font}, separación {gap:.2f}")
            gaps.append(gap)
        cursor = end
    for page_number in sorted(caption_pages):
        doc[page_number - 1].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(
            args.output / f"w{width}-font{font}-page{page_number}.png")
    report.append({"width": width, "height": height, "font_size": font,
                   "captions": expected, "caption_pages": sorted(caption_pages),
                   "minimum_line_gap": round(min(gaps), 2) if gaps else None})
    doc.close()
(args.output / "report.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
