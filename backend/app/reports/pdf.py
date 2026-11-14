"""A small, dependency-free PDF writer for incident reports (PDF 1.4, standard Helvetica fonts).

It supports what the report needs and nothing more: headings, wrapped paragraphs, key/value rows,
simple tables, rules, coloured banners, automatic page breaks and a footer on every page. Text is
encoded as WinAnsi (cp1252); characters outside it are transliterated (e.g. "₂" -> "2").
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

PAGE_W, PAGE_H = 595.28, 841.89  # A4 in points
MARGIN = 50.0
FOOTER_Y = 30.0

# Helvetica advance widths (1/1000 em) for ASCII 32..126, from the standard AFM metrics.
_HELV = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556,
    556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278,
    500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469,
    556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
    278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]
_TRANSLIT = {
    "₂": "2", "₃": "3", "≥": ">=", "≤": "<=", "→": "->", "←": "<-", "≈": "~", "≠": "!=", "Δ": "delta ",
    "σ": "sigma", "µ": "u", "−": "-", "‑": "-", "′": "'", "″": '"', "✓": "v", "⚠": "!", "·": "·",
}


def clean(text: str) -> str:
    out = "".join(_TRANSLIT.get(ch, ch) for ch in str(text))
    return out.encode("cp1252", errors="replace").decode("cp1252")


def _char_width(ch: str) -> int:
    o = ord(ch)
    return _HELV[o - 32] if 32 <= o <= 126 else 556


def text_width(text: str, size: float, bold: bool = False) -> float:
    return sum(_char_width(ch) for ch in text) * size / 1000 * (1.06 if bold else 1.0)


def _break_token(w: str, size: float, width: float, bold: bool) -> list[str]:
    """Split one over-long token into pieces that each fit ``width`` (single pass, linear time)."""
    limit = width * 1000 / size / (1.06 if bold else 1.0)
    pieces, start, used = [], 0, 0
    for i, ch in enumerate(w):
        cw = _char_width(ch)
        if used + cw > limit and i > start:
            pieces.append(w[start:i])
            start, used = i, 0
        used += cw
    pieces.append(w[start:])
    return pieces


def wrap(text: str, size: float, width: float, bold: bool = False) -> list[str]:
    lines: list[str] = []
    for para in clean(text).split("\n"):
        words, line = para.split(" "), ""
        for w in words:
            candidate = f"{line} {w}" if line else w
            if text_width(candidate, size, bold) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
            if text_width(w, size, bold) > width:  # break very long tokens
                *full, w = _break_token(w, size, width, bold)
                lines.extend(full)
            line = w
        lines.append(line)
    return lines


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


@dataclass
class _Page:
    ops: list[str] = field(default_factory=list)


class PdfDocument:
    def __init__(self, title: str, footer: str) -> None:
        self.title = clean(title)
        self.footer = clean(footer)
        self.pages: list[_Page] = []
        self.y = 0.0
        self.new_page()

    # ---------------------------------------------------------------- primitives ----
    def new_page(self) -> None:
        self.pages.append(_Page())
        self.y = PAGE_H - MARGIN

    @property
    def _ops(self) -> list[str]:
        return self.pages[-1].ops

    def ensure(self, height: float) -> None:
        if self.y - height < MARGIN + 20:
            self.new_page()

    def text(self, x: float, y: float, s: str, size: float = 10, bold: bool = False, rgb=(0.1, 0.1, 0.12)) -> None:
        font = "F2" if bold else "F1"
        r, g, b = rgb
        self._ops.append(f"BT {r:.3f} {g:.3f} {b:.3f} rg /{font} {size:.1f} Tf {x:.2f} {y:.2f} Td "
                         f"({_esc(clean(s))}) Tj ET")

    def rect(self, x: float, y: float, w: float, h: float, rgb=(0.9, 0.9, 0.9)) -> None:
        r, g, b = rgb
        self._ops.append(f"{r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")

    def line(self, x1: float, y1: float, x2: float, y2: float, rgb=(0.75, 0.75, 0.78), width: float = 0.6) -> None:
        r, g, b = rgb
        self._ops.append(f"{r:.3f} {g:.3f} {b:.3f} RG {width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    # ------------------------------------------------------------------- blocks ----
    def banner(self, s: str, rgb=(0.72, 0.16, 0.12), size: float = 10) -> None:
        lines = wrap(s, size, PAGE_W - 2 * MARGIN - 16, bold=True)
        h = 10 + 13 * len(lines)
        self.ensure(h + 6)
        self.rect(MARGIN, self.y - h, PAGE_W - 2 * MARGIN, h, rgb)
        ty = self.y - 15
        for ln in lines:
            self.text(MARGIN + 8, ty, ln, size, True, (1, 1, 1))
            ty -= 13
        self.y -= h + 10

    def heading(self, s: str, size: float = 13) -> None:
        self.ensure(size + 18)
        self.y -= 6
        self.text(MARGIN, self.y - size, s, size, True, (0.08, 0.2, 0.38))
        self.y -= size + 5
        self.line(MARGIN, self.y, PAGE_W - MARGIN, self.y)
        self.y -= 8

    def paragraph(self, s: str, size: float = 9.5, bold: bool = False, rgb=(0.1, 0.1, 0.12), indent: float = 0) -> None:
        width = PAGE_W - 2 * MARGIN - indent
        for ln in wrap(s, size, width, bold):
            self.ensure(size + 4)
            self.text(MARGIN + indent, self.y - size, ln, size, bold, rgb)
            self.y -= size + 3.5
        self.y -= 3

    def bullets(self, items: list[str], size: float = 9.5) -> None:
        for item in items:
            lines = wrap(item, size, PAGE_W - 2 * MARGIN - 14)
            for i, ln in enumerate(lines):
                self.ensure(size + 4)
                if i == 0:
                    self.text(MARGIN + 2, self.y - size, "-", size)
                self.text(MARGIN + 14, self.y - size, ln, size)
                self.y -= size + 3.5
        self.y -= 3

    def key_values(self, rows: list[tuple[str, str]], size: float = 9.5, label_w: float = 150) -> None:
        value_w = PAGE_W - 2 * MARGIN - label_w
        for label, value in rows:
            lab = wrap(label, size, label_w - 8, bold=True)
            val = wrap(value if value not in (None, "") else "-", size, value_w)
            n = max(len(lab), len(val))
            self.ensure(n * (size + 3.5) + 2)
            for i in range(n):
                if i < len(lab):
                    self.text(MARGIN, self.y - size, lab[i], size, True, (0.3, 0.3, 0.35))
                if i < len(val):
                    self.text(MARGIN + label_w, self.y - size, val[i], size)
                self.y -= size + 3.5
            self.y -= 2
        self.y -= 3

    def table(self, headers: list[str], rows: list[list[str]], widths: list[float], size: float = 8.5) -> None:
        total = sum(widths)
        scale = (PAGE_W - 2 * MARGIN) / total
        widths = [w * scale for w in widths]

        def draw_row(cells: list[str], bold: bool, shade: bool) -> None:
            wrapped = [wrap(c if c not in (None, "") else "-", size, w - 6, bold) for c, w in zip(cells, widths)]
            n = max(len(w) for w in wrapped)
            h = n * (size + 3) + 5
            if self.y - h < MARGIN + 20:
                self.new_page()
                if not bold:
                    draw_row(headers, True, True)
            if shade:
                self.rect(MARGIN, self.y - h, PAGE_W - 2 * MARGIN, h, (0.93, 0.94, 0.96))
            x = MARGIN
            for lines, w in zip(wrapped, widths):
                ty = self.y - size - 2
                for ln in lines:
                    self.text(x + 3, ty, ln, size, bold)
                    ty -= size + 3
                x += w
            self.y -= h
            self.line(MARGIN, self.y, PAGE_W - MARGIN, self.y, (0.85, 0.86, 0.88), 0.4)

        draw_row(headers, True, True)
        for r in rows:
            draw_row([str(c) for c in r], False, False)
        self.y -= 8

    # ------------------------------------------------------------------- output ----
    def render(self) -> bytes:
        total = len(self.pages)
        for i, page in enumerate(self.pages, start=1):
            page.ops.append(f"0.8 0.8 0.82 RG 0.4 w {MARGIN:.2f} {FOOTER_Y + 12:.2f} m {PAGE_W - MARGIN:.2f} {FOOTER_Y + 12:.2f} l S")
            footer = f"{self.footer}  |  page {i} of {total}"
            page.ops.append(f"BT 0.40 0.40 0.45 rg /F1 7.5 Tf {MARGIN:.2f} {FOOTER_Y:.2f} Td ({_esc(clean(footer))}) Tj ET")

        objects: list[bytes] = []

        def add(obj: bytes) -> int:
            objects.append(obj)
            return len(objects)

        catalog = add(b"")  # placeholder, filled below
        pages_id = add(b"")
        f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        kids = []
        for page in self.pages:
            stream = zlib.compress("\n".join(page.ops).encode("cp1252", errors="replace"))
            content = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream")
            kids.append(add(
                (f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                 f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> /Contents {content} 0 R >>").encode()
            ))
        objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
        objects[pages_id - 1] = (f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] "
                                 f"/Count {len(kids)} >>").encode()
        stamp = datetime.now(UTC).strftime("D:%Y%m%d%H%M%SZ")
        info = add(f"<< /Title ({_esc(self.title)}) /Producer (ASTRA-MED) /CreationDate ({stamp}) >>".encode("cp1252", "replace"))

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, obj in enumerate(objects, start=1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += (f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\n"
                f"startxref\n{xref}\n%%EOF\n").encode()
        return bytes(out)
