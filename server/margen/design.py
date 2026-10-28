"""Deterministic typography around content-specific generated artwork."""
import base64
import html
import io
import textwrap
from functools import cache
from pathlib import Path
from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

# Liberation Sans is installed in the service image; Arial shares its metrics on a Mac.
FONTS = {
    "regular": ["/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf"],
    "bold": ["/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
             "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
             "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
}


def wrapped(text, width, limit=None):
    lines = textwrap.wrap(text, width, break_long_words=True) or [""]
    if limit:
        truncated = len(lines) > limit
        lines = lines[:limit]
        if truncated:
            lines[-1] = lines[-1].rstrip(" ,.;") + "…"
    return lines


def text_lines(text, x, y, width=32, size=42, leading=None, color="#142b36", weight="400", limit=None):
    lines = wrapped(text, width, limit)
    return "".join(
        f'<text x="{x}" y="{y + i * (leading or size * 1.2):.1f}" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}">{html.escape(line)}</text>'
        for i, line in enumerate(lines)
    )


COVER_LABELS = {
    "es": {"study": "REVISTA DE ESTUDIO", "contents": "EN ESTE CUADERNO", "section": "sección", "sections": "secciones",
           "personal": "EDICIÓN PERSONAL", "tagline": "IDEAS · GUÍAS · LECTURAS"},
    "gl": {"study": "REVISTA DE ESTUDO", "contents": "NESTE CADERNO", "section": "sección", "sections": "seccións",
           "personal": "EDICIÓN PERSOAL", "tagline": "IDEAS · GUÍAS · LECTURAS"},
}


def section_count(count, labels):
    return f"{count} {labels['section'] if count == 1 else labels['sections']}"


def cover_svg(plan, issue_date, style, artwork=None, language="es"):
    labels = COVER_LABELS[language]
    date = "/".join(reversed(issue_date.split("-")))
    if style != "retro90":
        title_lines = textwrap.wrap(plan.title, 22, break_long_words=True)
        font_size = min(70, 350 / max(1, len(title_lines)))
        title = text_lines(plan.title, 80, 295, 22, font_size, font_size * 1.2, weight="700")
        subtitle = text_lines(plan.subtitle, 80, 800, 49, 25, 36, color="#475a60", limit=5)
        topics = "".join(text_lines(f"{i+1:02d} / {c.title}", 80, 1072 + i * 46, 64, 18, 21, limit=2)
                         for i, c in enumerate(plan.chapters[:3]))
        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="1260" viewBox="0 0 900 1260">
<rect width="900" height="1260" fill="#faf9f4"/>
<rect x="52" y="60" width="6" height="1140" fill="#244e59"/>
<g font-family="sans-serif" fill="#142b36">
<text x="80" y="110" font-size="24" font-weight="700" letter-spacing="7">PRELO</text>
<text x="80" y="153" font-size="18" letter-spacing="3">{labels["study"]}</text>
<path d="M80 195 H820 M80 1005 H820" stroke="#92a1a4"/>
{title}{subtitle}
<text x="80" y="1040" font-size="14" letter-spacing="3">{labels["contents"]}</text>
{topics}
<text x="80" y="1205" font-size="17">{date} · {section_count(len(plan.chapters), labels)}</text>
</g></svg>"""
    image = ""
    if artwork:
        image = f'<image x="0" y="0" width="900" height="1260" preserveAspectRatio="xMidYMid slice" xlink:href="data:image/jpeg;base64,{artwork["data"]}"/>'
    lines = textwrap.wrap(plan.title, 27, break_long_words=True)
    font_size = min(60, 180 / max(1, len(lines)))
    shadow = text_lines(plan.title, 58, 914 + font_size, 27, font_size, font_size * 1.1, "#021d2e", "900")
    headline = text_lines(plan.title, 55, 910 + font_size, 27, font_size, font_size * 1.1, "#ffe264", "900")
    subtitle = text_lines(plan.subtitle, 55, 1150, 61, 22, 25, "#ffffff", limit=3)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="900" height="1260" viewBox="0 0 900 1260">
<defs><linearGradient id="footer-shade" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#07354e" stop-opacity="0"/>
<stop offset="0.16" stop-color="#07354e" stop-opacity="0.94"/>
<stop offset="1" stop-color="#031e32" stop-opacity="0.99"/>
</linearGradient></defs>
<rect width="900" height="1260" fill="#075579"/>{image}
<rect x="0" y="0" width="900" height="270" fill="#06445f" opacity="0.25"/>
<rect x="0" y="850" width="900" height="410" fill="url(#footer-shade)"/>
<g font-family="sans-serif">
<text x="48" y="40" font-size="18" font-weight="700" fill="#ffffff">{date} · {labels["personal"]}</text>
<rect x="51" y="78" width="798" height="142" rx="52" fill="#e7e6dc" stroke="#033a53" stroke-width="7"/>
<rect x="43" y="68" width="798" height="142" rx="52" fill="#fffdf3" stroke="#e12825" stroke-width="13"/>
<text x="91" y="172" font-size="104" font-weight="900" letter-spacing="3" textLength="703" lengthAdjust="spacingAndGlyphs" fill="#d92724">PRELO</text>
<rect x="49" y="235" width="298" height="39" rx="4" fill="#30b3a3"/>
<text x="67" y="263" font-size="23" font-weight="900" fill="#053b5c">REVISTA 90'S</text>
{shadow}{headline}{subtitle}
<path d="M55 1223 H844" stroke="#3dbbb0" stroke-width="3"/>
<text x="55" y="1250" font-size="16" fill="#c8f3e5">{labels["tagline"]}</text>
<text x="844" y="1250" text-anchor="end" font-size="16" fill="#c8f3e5">{section_count(len(plan.chapters), labels).upper()}</text>
</g></svg>"""


@cache
def font(weight, size):
    for path in FONTS["bold" if weight in {"700", "900"} else "regular"]:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    # Pillow's own face lacks accents, but the page stays readable.
    return ImageFont.load_default(size)


class Canvas:
    """The SVG layout's coordinates, painted at the reader's resolution."""

    def __init__(self, width, height, scale, art=None):
        self.scale = scale
        self.image = Image.new("RGBA", (self.px(width), self.px(height)), "#075579")
        if art:
            with Image.open(io.BytesIO(art)) as picture:
                self.image.paste(ImageOps.fit(picture.convert("RGBA"), self.image.size, Image.LANCZOS))
        self.draw = ImageDraw.Draw(self.image)

    def px(self, value):
        return round(value * self.scale)

    def gradient(self, x, y, width, height, stops):
        """Vertical shade from (offset, colour, opacity) stops, like an SVG linearGradient."""
        rows = max(1, self.px(height))
        column = Image.new("RGBA", (1, rows))
        for row in range(rows):
            t = row / max(1, rows - 1)
            (a, start, alpha), (b, end, beta) = next(
                (stops[i], stops[i + 1]) for i in range(len(stops) - 1) if t <= stops[i + 1][0])
            k = (t - a) / (b - a) if b > a else 1
            first, second = ImageColor.getrgb(start), ImageColor.getrgb(end)
            column.putpixel((0, row), tuple(round(p + (q - p) * k) for p, q in zip(first, second))
                            + (round(255 * (alpha + (beta - alpha) * k)),))
        shade = column.resize((self.px(width), rows), Image.NEAREST)
        top = self.px(y)
        self.image.alpha_composite(shade.crop((0, 0, shade.width, min(rows, self.image.height - top))), (self.px(x), top))

    def box(self, x, y, width, height, colour, opacity=1.0):
        self.gradient(x, y, width, height, [(0, colour, opacity), (1, colour, opacity)])

    def panel(self, x, y, width, height, radius, fill, stroke=None, stroke_width=0):
        # SVG strokes straddle the outline: paint the stroke's outer shape, then the fill inside it.
        half = stroke_width / 2
        if stroke:
            self.draw.rounded_rectangle([self.px(x - half), self.px(y - half), self.px(x + width + half), self.px(y + height + half)],
                                        radius=self.px(radius + half), fill=stroke)
        self.draw.rounded_rectangle([self.px(x + half), self.px(y + half), self.px(x + width - half), self.px(y + height - half)],
                                    radius=self.px(radius - half), fill=fill)

    def lines(self, lines, x, y, size, leading, colour, weight="400", anchor="ls"):
        face = font(weight, self.px(size))
        for i, line in enumerate(lines):
            self.draw.text((self.px(x), self.px(y + i * leading)), line, font=face, fill=colour, anchor=anchor)

    def stretched(self, text, x, y, size, length, colour):
        """Text squeezed or widened to an exact length, as SVG textLength does."""
        face = font("900", self.px(size))
        left, top, right, bottom = face.getbbox(text, anchor="ls")
        layer = Image.new("RGBA", (right - left, bottom - top))
        ImageDraw.Draw(layer).text((-left, -top), text, font=face, fill=colour, anchor="ls")
        layer = layer.resize((self.px(length), layer.height), Image.LANCZOS)
        self.image.alpha_composite(layer, (self.px(x), self.px(y) + top))

    def jpeg(self, quality):
        output = io.BytesIO()
        self.image.convert("RGB").save(output, format="JPEG", quality=quality, optimize=True)
        return output.getvalue()


def cover_jpeg(plan, issue_date, artwork=None, language="es"):
    """Revista 90's cover as one picture, the layout of cover_svg. E-readers show a JPEG
    cover everywhere; an SVG one depends on each reader's fonts and image support."""
    labels = COVER_LABELS[language]
    date = "/".join(reversed(issue_date.split("-")))
    canvas = Canvas(900, 1260, 1.4, base64.b64decode(artwork["data"]) if artwork else None)
    canvas.box(0, 0, 900, 270, "#06445f", 0.25)
    canvas.gradient(0, 850, 900, 410, [(0, "#07354e", 0), (0.16, "#07354e", 0.94), (1, "#031e32", 0.99)])
    canvas.lines([f"{date} · {labels['personal']}"], 48, 40, 18, 0, "#ffffff", "700")
    canvas.panel(51, 78, 798, 142, 52, "#e7e6dc", "#033a53", 7)
    canvas.panel(43, 68, 798, 142, 52, "#fffdf3", "#e12825", 13)
    canvas.stretched("PRELO", 91, 172, 104, 703, "#d92724")
    canvas.panel(49, 235, 298, 39, 4, "#30b3a3")
    canvas.lines(["REVISTA 90'S"], 67, 263, 23, 0, "#053b5c", "900")
    lines = wrapped(plan.title, 27)
    size = min(60, 180 / max(1, len(lines)))
    canvas.lines(lines, 58, 914 + size, size, size * 1.1, "#021d2e", "900")
    canvas.lines(lines, 55, 910 + size, size, size * 1.1, "#ffe264", "900")
    canvas.lines(wrapped(plan.subtitle, 61, 3), 55, 1150, 22, 25, "#ffffff")
    canvas.box(55, 1221.5, 789, 3, "#3dbbb0")
    canvas.lines([labels["tagline"]], 55, 1250, 16, 0, "#c8f3e5")
    canvas.lines([section_count(len(plan.chapters), labels).upper()], 844, 1250, 16, 0, "#c8f3e5", anchor="rs")
    return canvas.jpeg(85)


def opener_jpeg(eyebrow, title, art):
    """Art, section and title composed into one page picture, so a portrait illustration
    never leaves its title alone on another page."""
    lines = textwrap.wrap(title, 24, break_long_words=True)[:3]
    size = min(64, 190 / max(1, len(lines)))
    top = 1170 - len(lines) * size * 1.1
    canvas = Canvas(900, 1200, 1.2, art)
    canvas.box(0, 0, 900, 74, "#06445f", 0.88)
    canvas.gradient(0, top - 70, 900, 1270 - top, [(0, "#07354e", 0), (0.3, "#07354e", 0.9), (1, "#031e32", 0.98)])
    canvas.lines(wrapped(eyebrow, 60, 1), 40, 49, 26, 30, "#ffffff", "700")
    canvas.lines(lines, 53, top + size + 3, size, size * 1.1, "#021d2e", "900")
    canvas.lines(lines, 50, top + size, size, size * 1.1, "#ffe264", "900")
    return canvas.jpeg(78)
