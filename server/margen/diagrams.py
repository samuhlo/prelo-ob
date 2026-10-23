"""Redraw diagrams read from old notes as clean SVG, laid out deterministically.

Arrowheads are plain polygons: older EPUB engines do not reliably support SVG markers.
"""
import html
import math
import textwrap
from collections import defaultdict
from .models import Diagram

WIDTH, MARGIN, FONT, LINE = 600, 20, 16, 20
INK, SOFT, PAPER = "#1b2426", "#5d6b6e", "#ffffff"
ACCENT = {"study": "#256c70", "retro90": "#053c60"}
FILL = {"box": "#eef3f3", "device": "#ffffff", "network": "#e4eeee", "storage": "#eef3f3",
        "actor": "#ffffff", "note": "#ffffff"}


def wrap(text, chars, limit=4):
    lines = textwrap.wrap(text, max(6, chars), break_long_words=True) or [""]
    if len(lines) > limit:
        lines = lines[:limit]
        lines[-1] = lines[-1].rstrip(" ,.;") + "…"
    return lines


def text_block(lines, cx, top, size=FONT, color=INK, weight="400"):
    return "".join(
        f'<text x="{cx:.1f}" y="{top + (i + 1) * LINE - 5:.1f}" font-size="{size}" font-weight="{weight}" '
        f'fill="{color}" text-anchor="middle">{html.escape(line)}</text>' for i, line in enumerate(lines))


def box(node, x, y, w, h, accent):
    radius = {"device": 12, "network": h / 2, "actor": 12}.get(node.kind, 4)
    stroke = accent if node.kind in {"device", "network", "actor"} else INK
    dash = ' stroke-dasharray="5 4"' if node.kind == "note" else ""
    width = 2.5 if node.kind == "device" else 1.5
    shape = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{radius:.1f}" '
             f'fill="{FILL[node.kind]}" stroke="{stroke}" stroke-width="{width}"{dash}/>')
    if node.kind == "storage":
        shape += f'<path d="M{x:.1f} {y + 8:.1f} H{x + w:.1f}" stroke="{INK}" stroke-width="1"/>'
    return shape


def arrowhead(x, y, dx, dy, color):
    length = math.hypot(dx, dy) or 1
    ux, uy = dx / length, dy / length
    points = [(x, y), (x - 11 * ux + 5 * uy, y - 11 * uy - 5 * ux), (x - 11 * ux - 5 * uy, y - 11 * uy + 5 * ux)]
    return f'<polygon points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in points)}" fill="{color}"/>'


def clip(rect, dx, dy):
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    scale = min(w / 2 / abs(dx) if dx else math.inf, h / 2 / abs(dy) if dy else math.inf)
    return cx + dx * scale, cy + dy * scale


def label_size(text):
    # Labels carry data (addresses, ports): wrap them, never cut them.
    lines = wrap(text, 24, 4)
    return lines, max(len(line) for line in lines) * 7.6 + 10, len(lines) * 16 + 4


def label(text, x, y):
    lines, width, height = label_size(text)
    return (f'<rect x="{x - width / 2:.1f}" y="{y - height / 2:.1f}" width="{width:.1f}" height="{height:.1f}" '
            f'fill="{PAPER}" opacity="0.92"/>'
            + "".join(f'<text x="{x:.1f}" y="{y - height / 2 + 15 + i * 16:.1f}" font-size="13" fill="{SOFT}" '
                      f'text-anchor="middle">{html.escape(line)}</text>' for i, line in enumerate(lines)))


def crosses(rects, e, point):
    """Whether a point of an edge falls inside a box other than its two ends."""
    return any(name not in {e.source, e.target} and r[0] - 4 < point[0] < r[0] + r[2] + 4
               and r[1] - 4 < point[1] < r[1] + r[3] + 4 for name, r in rects.items())


def bezier(start, control, end, t):
    return tuple((1 - t) ** 2 * a + 2 * (1 - t) * t * c + t ** 2 * b for a, c, b in zip(start, control, end))


def edge(rects, e, accent):
    """(line, label) markup; labels are drawn after every line so none hides them."""
    a, b = rects[e.source], rects[e.target]
    (ax, ay), (bx, by) = [(r[0] + r[2] / 2, r[1] + r[3] / 2) for r in (a, b)]
    dx, dy = bx - ax, by - ay
    start, end = clip(a, dx, dy), clip(b, -dx, -dy)
    straight = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    control = straight
    length = math.hypot(dx, dy) or 1
    if any(crosses(rects, e, bezier(start, straight, end, i / 20)) for i in range(1, 20)):
        # Bend around boxes in between; keep the first bend that clears them all.
        for offset in (70, -70, 130, -130, 200, -200):
            candidate = (straight[0] - dy / length * offset, straight[1] + dx / length * offset)
            if not any(crosses(rects, e, bezier(start, candidate, end, i / 20)) for i in range(1, 20)):
                control = candidate
                break
    middle = bezier(start, control, end, 0.5)
    if e.label.strip():
        # Slide the label along its line until it covers no box.
        _, width, height = label_size(e.label)
        for t in (0.5, 0.38, 0.62, 0.28, 0.72, 0.2, 0.8):
            x, y = bezier(start, control, end, t)
            if not any(x - width / 2 - 4 < r[0] + r[2] and r[0] < x + width / 2 + 4 and
                       y - height / 2 - 4 < r[1] + r[3] and r[1] < y + height / 2 + 4 for r in rects.values()):
                middle = (x, y)
                break
    svg = (f'<path d="M{start[0]:.1f} {start[1]:.1f} Q{control[0]:.1f} {control[1]:.1f} {end[0]:.1f} {end[1]:.1f}" '
           f'fill="none" stroke="{INK}" stroke-width="1.6"/>')
    if e.style in {"arrow", "double"}:
        svg += arrowhead(*end, end[0] - control[0], end[1] - control[1], accent)
    if e.style == "double":
        svg += arrowhead(*start, start[0] - control[0], start[1] - control[1], accent)
    return svg, label(e.label, *middle) if e.label.strip() else ""


def ranks(diagram):
    ids = [n.id for n in diagram.nodes]
    successors = defaultdict(list)
    for e in diagram.edges:
        if e.source != e.target:
            successors[e.source].append(e.target)
    # Depth-first order; edges back into the current path are ignored (cycles).
    state, order, dag = {}, [], defaultdict(list)
    def visit(node):
        state[node] = "open"
        for target in successors[node]:
            if state.get(target) == "open":
                continue
            dag[node].append(target)
            if target not in state:
                visit(target)
        state[node] = "done"
        order.append(node)
    for node in ids:
        if node not in state:
            visit(node)
    rank = {node: 0 for node in ids}
    for node in reversed(order):
        for target in dag[node]:
            rank[target] = max(rank[target], rank[node] + 1)
    return rank


def flow(diagram, accent, horizontal):
    rank = ranks(diagram)
    columns = defaultdict(list)
    for node in diagram.nodes:
        columns[rank[node.id]].append(node)
    levels = [columns[r] for r in sorted(columns)]
    widest = max(map(len, levels))
    if horizontal and (len(levels) > 4 or widest > 10):
        horizontal = False
    elif not horizontal and widest > 6 and len(levels) <= 4:
        # Columns hold many siblings without wrapping them into crossing rows.
        horizontal = True
    if not horizontal:
        # Wide levels continue on the next row.
        levels = [level[i:i + 6] for level in levels for i in range(0, len(level), 6)]
    predecessors = defaultdict(list)
    for e in diagram.edges:
        predecessors[e.target].append(e.source)
    rects, position, parts = {}, {}, []
    if horizontal:
        gap = 46
        column = (WIDTH - 2 * MARGIN - (len(levels) - 1) * gap) / len(levels)
        sizes = [[(n, wrap(n.label, int(column / 8.4))) for n in level] for level in levels]
        heights = [sum(16 + len(lines) * LINE for _, lines in level) + (len(level) - 1) * 28 for level in sizes]
        total = max(heights)
        for i, level in enumerate(sizes):
            y = MARGIN + (total - heights[i]) / 2
            x = MARGIN + i * (column + gap)
            for node, lines in level:
                h = 16 + len(lines) * LINE
                rects[node.id] = (x, y, column, h)
                parts.append((node, lines))
                y += h + 28
        height = total + 2 * MARGIN
    else:
        y = MARGIN
        for level in levels:
            level.sort(key=lambda n: sum(position.get(p, 0) for p in predecessors[n.id]) /
                       max(1, sum(p in position for p in predecessors[n.id])) if any(p in position for p in predecessors[n.id]) else 0)
            gap = 24
            w = min(180, (WIDTH - 2 * MARGIN - (len(level) - 1) * gap) / len(level))
            x = (WIDTH - len(level) * w - (len(level) - 1) * gap) / 2
            wrapped = [(n, wrap(n.label, int(w / 8.4))) for n in level]
            row = max(16 + len(lines) * LINE for _, lines in wrapped)
            for node, lines in wrapped:
                h = 16 + len(lines) * LINE
                rects[node.id] = (x, y + (row - h) / 2, w, h)
                position[node.id] = x + w / 2
                parts.append((node, lines))
                x += w + gap
            y += row + 70
        height = y - 70 + MARGIN
    drawn = [edge(rects, e, accent) for e in diagram.edges if e.source != e.target]
    svg = [line for line, _ in drawn]
    for node, lines in parts:
        x, y, w, h = rects[node.id]
        svg.append(box(node, x, y, w, h, accent) + text_block(lines, x + w / 2, y + 8, weight="700" if node.kind == "device" else "400"))
    # Lines, then boxes, then edge labels: every text stays readable.
    return height, "".join(svg + [text for _, text in drawn])


def layers(diagram, accent):
    y, svg = MARGIN, []
    for i, node in enumerate(diagram.nodes):
        lines = wrap(node.label, 60, 3)
        h = 18 + len(lines) * LINE
        svg.append(f'<rect x="{MARGIN}" y="{y}" width="{WIDTH - 2 * MARGIN}" height="{h}" rx="4" '
                   f'fill="{"#e4eeee" if i % 2 else PAPER}" stroke="{accent}" stroke-width="1.5"/>'
                   + text_block(lines, WIDTH / 2, y + 9))
        y += h + 6
    return y - 6 + MARGIN, "".join(svg)


def sequence(diagram, accent):
    actors = diagram.nodes
    step = (WIDTH - 2 * MARGIN) / len(actors)
    centers = {a.id: MARGIN + step * (i + 0.5) for i, a in enumerate(actors)}
    heads = {a.id: wrap(a.label, int((step - 12) / 8.4), 3) for a in actors}
    head = max(16 + len(lines) * LINE for lines in heads.values())
    y, messages = MARGIN + head + 30, []
    for e in diagram.edges:
        if e.source == e.target:
            continue
        span = max(abs(centers[e.target] - centers[e.source]), 250)
        lines = wrap(e.label, int(span / 7.6), 4) if e.label.strip() else []
        y += len(lines) * 16
        x1, x2 = centers[e.source], centers[e.target]
        direction = 1 if x2 > x1 else -1
        messages.append(
            "".join(f'<text x="{(x1 + x2) / 2:.1f}" y="{y - 6 - (len(lines) - 1 - i) * 16:.1f}" font-size="13" '
                    f'fill="{SOFT}" text-anchor="middle">{html.escape(line)}</text>' for i, line in enumerate(lines))
            + f'<path d="M{x1:.1f} {y:.1f} H{x2 - direction * 2:.1f}" stroke="{INK}" stroke-width="1.6"'
            + (' stroke-dasharray="6 4"' if e.style == "line" else "") + "/>"
            + arrowhead(x2, y, direction, 0, accent))
        y += 30
    bottom = y + 4
    svg = []
    for a in actors:
        x = centers[a.id]
        svg.append(f'<path d="M{x:.1f} {MARGIN + head:.1f} V{bottom:.1f}" stroke="{SOFT}" stroke-width="1" stroke-dasharray="4 4"/>'
                   + box(a, x - (step - 12) / 2, MARGIN, step - 12, head, accent)
                   + text_block(heads[a.id], x, MARGIN + (head - len(heads[a.id]) * LINE) / 2, weight="700"))
    return bottom + MARGIN, "".join(svg + messages)


def render_diagram(diagram: Diagram, style: str = "study") -> str | None:
    """SVG for the diagram, or None when it cannot be drawn legibly (keep the original then)."""
    ids = {n.id for n in diagram.nodes}
    if len(ids) != len(diagram.nodes):
        return None
    diagram = diagram.model_copy(update={"edges": [e for e in diagram.edges if e.source in ids and e.target in ids]})
    accent = ACCENT.get(style, ACCENT["study"])
    if diagram.layout == "layers":
        if not 2 <= len(diagram.nodes) <= 12:
            return None
        height, body = layers(diagram, accent)
    elif diagram.layout == "sequence":
        if not 2 <= len(diagram.nodes) <= 5 or not diagram.edges or len(diagram.edges) > 20:
            return None
        height, body = sequence(diagram, accent)
    else:
        if not 2 <= len(diagram.nodes) <= 16:
            return None
        height, body = flow(diagram, accent, diagram.layout == "flow_right")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height:.0f}" '
            f'viewBox="0 0 {WIDTH} {height:.0f}"><rect width="{WIDTH}" height="{height:.0f}" fill="{PAPER}"/>'
            f'<g font-family="sans-serif">{body}</g></svg>')
