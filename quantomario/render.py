"""Low-level terminal rendering: pixel canvas, half-block cells, ANSI output."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
import shutil
import sys
from typing import Iterable, Sequence

from .fonts import FONT_5x7, draw_text as draw_bitmap_text

RGB = tuple[int, int, int]

UP = "\u2580"
FULL = "\u2588"
LOWER = "\u2584"


class PixelCanvas:
    __slots__ = ("width", "height", "pixels")

    def __init__(self, width: int, height: int, fill: RGB = (0, 0, 0)) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self.pixels = [fill] * (self.width * self.height)

    def clear(self, color: RGB) -> None:
        self.pixels[:] = [color] * (self.width * self.height)

    def px(self, x: int, y: int, color: RGB) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[y * self.width + x] = color

    def get(self, x: int, y: int) -> RGB:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.pixels[y * self.width + x]
        return (0, 0, 0)

    def hline(self, x: int, y: int, w: int, color: RGB) -> None:
        if y < 0 or y >= self.height:
            return
        x0 = max(0, x)
        x1 = min(self.width, x + w)
        if x1 <= x0:
            return
        base = y * self.width
        self.pixels[base + x0:base + x1] = [color] * (x1 - x0)

    def vline(self, x: int, y: int, h: int, color: RGB) -> None:
        if x < 0 or x >= self.width:
            return
        y0 = max(0, y)
        y1 = min(self.height, y + h)
        for yy in range(y0, y1):
            self.pixels[yy * self.width + x] = color

    def rect(self, x: int, y: int, w: int, h: int, color: RGB) -> None:
        for yy in range(max(0, y), min(self.height, y + h)):
            self.hline(x, yy, w, color)

    def outline(self, x: int, y: int, w: int, h: int, color: RGB) -> None:
        self.hline(x, y, w, color)
        self.hline(x, y + h - 1, w, color)
        self.vline(x, y, h, color)
        self.vline(x + w - 1, y, h, color)

    def dither_rect(self, x: int, y: int, w: int, h: int, color: RGB,
                    step: int = 2, phase: int = 0) -> None:
        for yy in range(max(0, y), min(self.height, y + h)):
            start = max(0, x)
            end = min(self.width, x + w)
            for xx in range(start + ((yy + phase) % step), end, step):
                self.pixels[yy * self.width + xx] = color

    def line(self, x0: int, y0: int, x1: int, y1: int, color: RGB) -> None:
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.px(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def circle(self, cx: int, cy: int, r: int, color: RGB) -> None:
        x = r
        y = 0
        err = 0
        while x >= y:
            for px, py in ((x, y), (y, x), (-y, x), (-x, y),
                           (-x, -y), (-y, -x), (y, -x), (x, -y)):
                self.px(cx + px, cy + py, color)
            y += 1
            if err <= 0:
                err += 2 * y + 1
            if err > 0:
                x -= 1
                err -= 2 * x + 1

    def ellipse(self, cx: int, cy: int, rx: int, ry: int, color: RGB,
                steps: int = 32) -> None:
        for i in range(steps):
            a = 2 * math.pi * i / steps
            self.px(round(cx + rx * math.cos(a)), round(cy + ry * math.sin(a)), color)

    def text(self, x: int, y: int, text: str, color: RGB, scale: int = 1,
             spacing: int = 1, align: str = "left",
             font: dict[str, tuple[str, ...]] = FONT_5x7) -> None:
        draw_bitmap_text(self, x, y, text, color, font=font, scale=scale,
                         spacing=spacing, align=align)

    def sprite(self, art: Sequence[str], x: int, y: int, scale: float,
               palette: dict[str, RGB], flip: bool = False,
               silhouette: RGB | None = None) -> None:
        if not art:
            return
        sw, sh = len(art[0]), len(art)
        dw = max(1, round(sw * scale))
        dh = max(1, round(sh * scale))
        x0 = round(x)
        y0 = round(y)
        # Clip quickly if entirely off-screen.
        if x0 >= self.width or y0 >= self.height or x0 + dw <= 0 or y0 + dh <= 0:
            return
        for dy in range(dh):
            sy = min(sh - 1, int(dy * sh / dh))
            row = art[sy]
            yy = y0 + dy
            if yy < 0 or yy >= self.height:
                continue
            for dx in range(dw):
                sx = min(sw - 1, int(dx * sw / dw))
                if flip:
                    sx = sw - 1 - sx
                ch = row[sx]
                if ch == ".":
                    continue
                color = silhouette if silhouette is not None else palette.get(ch)
                if color is None:
                    continue
                xx = x0 + dx
                if 0 <= xx < self.width:
                    self.pixels[yy * self.width + xx] = color

    def bitmap(self, rows: Sequence[str], x: int, y: int, color: RGB) -> None:
        for dy, row in enumerate(rows):
            for dx, ch in enumerate(row):
                if ch == "1":
                    self.px(x + dx, y + dy, color)


@dataclass
class Cell:
    ch: str = " "
    fg: RGB = (255, 255, 255)
    bg: RGB = (0, 0, 0)


class CellCanvas:
    """Terminal-cell overlay layer.  The playfield is first rasterised as
    half-block cells, then HUD/menu text is written on top."""

    def __init__(self, width: int, height: int, fg: RGB = (255, 255, 255),
                 bg: RGB = (0, 0, 0)) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self.cells = [[Cell(" ", fg, bg) for _ in range(self.width)]
                      for _ in range(self.height)]

    def fill(self, bg: RGB) -> None:
        for row in self.cells:
            for cell in row:
                cell.ch = " "
                cell.bg = bg

    def clear_rect(self, x: int, y: int, w: int, h: int, bg: RGB,
                   fg: RGB = (255, 255, 255)) -> None:
        """Opaque rectangle, used before drawing dialog boxes so the world
        behind them cannot bleed through the panel interior."""
        for yy in range(max(0, y), min(self.height, y + h)):
            row = self.cells[yy]
            for xx in range(max(0, x), min(self.width, x + w)):
                cell = row[xx]
                cell.ch = " "
                cell.fg = fg
                cell.bg = bg

    def put(self, x: int, y: int, ch: str, fg: RGB, bg: RGB | None = None) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            cell = self.cells[y][x]
            cell.ch = ch
            cell.fg = fg
            if bg is not None:
                cell.bg = bg

    def text(self, x: int, y: int, text: str, fg: RGB, bg: RGB | None = None,
             selected: bool = False) -> int:
        """Write one-cell-tall terminal text. Returns the next x."""
        if y < 0 or y >= self.height:
            return x
        cx = x
        for ch in text:
            if 0 <= cx < self.width:
                cell = self.cells[y][cx]
                cell.ch = ch
                if selected:
                    cell.fg = bg if bg is not None else (0, 0, 0)
                    cell.bg = fg
                else:
                    cell.fg = fg
                    if bg is not None:
                        cell.bg = bg
            cx += 1
        return cx

    def center(self, y: int, text: str, fg: RGB, bg: RGB | None = None,
               width: int | None = None) -> None:
        w = width if width is not None else self.width
        x = max(0, (self.width - len(text)) // 2)
        if bg is not None:
            # Paint a clean strip first so centred text is legible.
            for xx in range(self.width):
                cell = self.cells[y][xx] if 0 <= y < self.height else None
                if cell:
                    cell.ch = " "
                    cell.bg = bg
        self.text(x, y, text, fg, bg)

    def hline(self, x: int, y: int, w: int, ch: str, fg: RGB,
              bg: RGB | None = None) -> None:
        for xx in range(max(0, x), min(self.width, x + w)):
            self.put(xx, y, ch, fg, bg)

    def vline(self, x: int, y: int, h: int, ch: str, fg: RGB,
              bg: RGB | None = None) -> None:
        for yy in range(max(0, y), min(self.height, y + h)):
            self.put(x, yy, ch, fg, bg)

    def box(self, x: int, y: int, w: int, h: int, fg: RGB,
            bg: RGB | None = None, double: bool = True, title: str = "") -> None:
        if w < 2 or h < 2:
            return
        if double:
            tl, tr, bl, br, hz, vt = "╔", "╗", "╚", "╝", "═", "║"
        else:
            tl, tr, bl, br, hz, vt = "┌", "┐", "└", "┘", "─", "│"
        self.hline(x + 1, y, w - 2, hz, fg, bg)
        self.hline(x + 1, y + h - 1, w - 2, hz, fg, bg)
        self.vline(x, y + 1, h - 2, vt, fg, bg)
        self.vline(x + w - 1, y + 1, h - 2, vt, fg, bg)
        self.put(x, y, tl, fg, bg)
        self.put(x + w - 1, y, tr, fg, bg)
        self.put(x, y + h - 1, bl, fg, bg)
        self.put(x + w - 1, y + h - 1, br, fg, bg)
        if title:
            label = f" {title} "
            self.text(x + max(2, (w - len(label)) // 2), y, label, fg, bg)
        if bg is not None:
            for yy in range(y + 1, y + h - 1):
                for xx in range(x + 1, x + w - 1):
                    if self.cells[yy][xx].ch == " ":
                        self.cells[yy][xx].bg = bg


def from_pixels(canvas: PixelCanvas, fg_color: RGB | None = None) -> CellCanvas:
    """Rasterise a pixel canvas using the half-block trick: one cell stores
    two vertically stacked pixels in its fg/bg colours."""
    cells = CellCanvas(canvas.width, (canvas.height + 1) // 2)
    w = canvas.width
    for cy in range(cells.height):
        top_y = cy * 2
        bottom_y = top_y + 1
        for cx in range(w):
            top = canvas.pixels[top_y * w + cx]
            bottom = canvas.pixels[bottom_y * w + cx] if bottom_y < canvas.height else top
            cell = cells.cells[cy][cx]
            if top == bottom:
                cell.ch = FULL
                cell.fg = top
                cell.bg = top
            else:
                cell.ch = UP
                cell.fg = top
                cell.bg = bottom
    return cells


# --- ANSI output ---------------------------------------------------------

_BASE16 = [
    (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
    (0, 0, 128), (128, 0, 128), (0, 128, 128), (192, 192, 192),
    (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0),
    (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
]


def _build_256_palette() -> list[RGB]:
    pal = list(_BASE16)
    levels = (0, 95, 135, 175, 215, 255)
    for r in levels:
        for g in levels:
            for b in levels:
                pal.append((r, g, b))
    for i in range(24):
        v = 8 + i * 10
        pal.append((v, v, v))
    return pal


class ColorEncoder:
    def __init__(self, mode: str = "auto") -> None:
        self.mode = self._resolve(mode)
        self._cache: dict[RGB, str] = {}
        self._pair_cache: dict[tuple[RGB, RGB], str] = {}
        self._pal256 = _build_256_palette() if self.mode == "256" else []

    @staticmethod
    def _resolve(mode: str) -> str:
        if mode in ("truecolor", "256", "16"):
            return mode
        colorterm = os.environ.get("COLORTERM", "").lower()
        if "truecolor" in colorterm or "24bit" in colorterm:
            return "truecolor"
        term = os.environ.get("TERM", "")
        if "256color" in term:
            return "256"
        return "16"

    def _nearest(self, color: RGB) -> int:
        best, best_d = 0, 1 << 30
        for i, pal in enumerate(self._pal256):
            d = (color[0] - pal[0]) ** 2 + (color[1] - pal[1]) ** 2 + (color[2] - pal[2]) ** 2
            if d < best_d:
                best, best_d = i, d
        return best

    def _nearest16(self, color: RGB) -> int:
        best, best_d = 0, 1 << 30
        for i, pal in enumerate(_BASE16):
            d = (color[0] - pal[0]) ** 2 + (color[1] - pal[1]) ** 2 + (color[2] - pal[2]) ** 2
            if d < best_d:
                best, best_d = i, d
        return best

    def fg(self, color: RGB) -> str:
        code = self._cache.get(color)
        if code:
            return code
        if self.mode == "truecolor":
            code = f"\x1b[38;2;{color[0]};{color[1]};{color[2]}m"
        elif self.mode == "256":
            code = f"\x1b[38;5;{self._nearest(color)}m"
        else:
            n = self._nearest16(color)
            code = f"\x1b[{30 + n}m" if n < 8 else f"\x1b[{90 + n - 8}m"
        self._cache[color] = code
        return code

    def bg(self, color: RGB) -> str:
        key = ("B", color)  # separate cache naming is not worth another dict
        code = self._cache.get(key)  # type: ignore[arg-type]
        if code:
            return code
        if self.mode == "truecolor":
            code = f"\x1b[48;2;{color[0]};{color[1]};{color[2]}m"
        elif self.mode == "256":
            code = f"\x1b[48;5;{self._nearest(color)}m"
        else:
            n = self._nearest16(color)
            if n < 8:
                code = f"\x1b[4{n}m"
            else:
                code = f"\x1b[{100 + (n - 8)}m"
        self._cache[key] = code  # type: ignore[index]
        return code

    def pair(self, fg: RGB, bg: RGB) -> str:
        key = (fg, bg)
        code = self._pair_cache.get(key)
        if code is None:
            code = self.fg(fg) + self.bg(bg)
            self._pair_cache[key] = code
        return code

    def encode(self, cells: CellCanvas) -> str:
        lines: list[str] = []
        for row in cells.cells:
            parts: list[str] = []
            last: tuple[RGB, RGB] | None = None
            for cell in row:
                key = (cell.fg, cell.bg)
                if key != last:
                    parts.append(self.pair(cell.fg, cell.bg))
                    last = key
                parts.append(cell.ch)
            lines.append("".join(parts))
        return "\x1b[0m" + "\r\n".join(lines) + "\x1b[0m"


class Terminal:
    """Alternate-screen raw terminal.  All state is restored in close()."""

    def __init__(self, color_mode: str = "auto") -> None:
        self.encoder = ColorEncoder(color_mode)
        self.fd = sys.stdin.fileno()
        self.saved = None
        self.active = False

    def __enter__(self) -> "Terminal":
        import termios
        import tty
        self.saved = termios.tcgetattr(self.fd)
        tty.setraw(self.fd)
        sys.stdout.write(
            "\x1b[?1049h"   # alternate screen
            "\x1b[?25l"     # hide cursor
            "\x1b[?7l"      # disable autowrap
            "\x1b[2J\x1b[H"
            "\x1b]0;QUANTOMARIO\x07"
        )
        sys.stdout.flush()
        self.active = True
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if not self.active:
            return
        import termios
        self.active = False
        sys.stdout.write("\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        try:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
        except Exception:
            pass

    def draw(self, cells: CellCanvas) -> None:
        sys.stdout.write("\x1b[H" + self.encoder.encode(cells))
        sys.stdout.flush()

    def size(self) -> tuple[int, int]:
        s = shutil.get_terminal_size(fallback=(100, 30))
        return max(1, s.columns), max(1, s.lines)

    def write(self, text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()
