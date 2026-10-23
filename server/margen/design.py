"""Deterministic typography around content-specific generated artwork."""
import html
import textwrap


def text_lines(text, x, y, width=32, size=42, leading=None, color="#142b36", weight="400", limit=None):
    lines = textwrap.wrap(text, width, break_long_words=True) or [""]
    if limit:
        truncated = len(lines) > limit
        lines = lines[:limit]
        if truncated:
            lines[-1] = lines[-1].rstrip(" ,.;") + "…"
    return "".join(
        f'<text x="{x}" y="{y + i * (leading or size * 1.2):.1f}" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}">{html.escape(line)}</text>'
        for i, line in enumerate(lines)
    )


COVER_LABELS = {
    "es": {"study": "REVISTA DE ESTUDIO", "contents": "EN ESTE CUADERNO", "sections": "secciones",
           "personal": "EDICIÓN PERSONAL", "tagline": "IDEAS · GUÍAS · LECTURAS"},
    "gl": {"study": "REVISTA DE ESTUDO", "contents": "NESTE CADERNO", "sections": "seccións",
           "personal": "EDICIÓN PERSOAL", "tagline": "IDEAS · GUÍAS · LECTURAS"},
}


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
<text x="80" y="1205" font-size="17">{date} · {len(plan.chapters)} {labels["sections"]}</text>
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
<text x="844" y="1250" text-anchor="end" font-size="16" fill="#c8f3e5">{len(plan.chapters)} {labels["sections"].upper()}</text>
</g></svg>"""



def opener_svg(eyebrow, title, image_href):
    """Inline SVG page: art, section and title composed together, so a portrait
    illustration never leaves its title or caption alone on another page."""
    lines = textwrap.wrap(title, 24, break_long_words=True)[:3]
    font_size = min(64, 190 / max(1, len(lines)))
    top = 1170 - len(lines) * font_size * 1.1
    shadow = text_lines(" ".join(lines), 53, top + font_size + 3, 24, font_size, font_size * 1.1, "#021d2e", "900", 3)
    headline = text_lines(" ".join(lines), 50, top + font_size, 24, font_size, font_size * 1.1, "#ffe264", "900", 3)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" width="100%" height="100%" viewBox="0 0 900 1200" preserveAspectRatio="xMidYMid meet">
<defs><linearGradient id="opener-shade" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#07354e" stop-opacity="0"/>
<stop offset="0.3" stop-color="#07354e" stop-opacity="0.9"/>
<stop offset="1" stop-color="#031e32" stop-opacity="0.98"/>
</linearGradient></defs>
<rect width="900" height="1200" fill="#075579"/>
<image x="0" y="0" width="900" height="1200" preserveAspectRatio="xMidYMid slice" xlink:href="{html.escape(image_href, quote=True)}"/>
<rect x="0" y="0" width="900" height="74" fill="#06445f" opacity="0.88"/>
<rect x="0" y="{top - 70:.0f}" width="900" height="{1270 - top:.0f}" fill="url(#opener-shade)"/>
<g font-family="sans-serif">
{text_lines(eyebrow, 40, 49, 60, 26, 30, "#ffffff", "700", 1)}
{shadow}{headline}
</g></svg>"""
