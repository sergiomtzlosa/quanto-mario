"""Menu, records, controls, and end-of-run screens."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Iterable

from .fonts import FONT_3x5, FONT_5x7, draw_text as draw_font, text_width
from .render import CellCanvas, PixelCanvas, from_pixels
from .scores import Records, format_time, format_short_time
from .quantum import QUBIT_NAMES
from .sprites import SPRITES
from .theme import THEMES, XRAY_MAP, PALETTE

INK = (232, 248, 255)
DIM = (126, 153, 170)
FAINT = (42, 58, 70)
BG = (3, 6, 9)
BG2 = (7, 12, 17)
ACCENT = (89, 227, 255)
VIOLET = (178, 140, 255)
AMBER = (255, 201, 107)
HAZARD = (255, 105, 105)

TITLE_MENU = (
    ("STORY", "FIVE WORLDS. THREE LIVES. ONE MEASUREMENT."),
    ("SPEEDRUN", "FIVE WORLDS. ONE CLOCK. INFINITE RETRIES."),
    ("QUANTUM LAB", "INSPECT THE 14-QUBIT CIRCUIT THAT RUNS EACH FRAME."),
    ("RECORDS", "THE TOP FIVE OBSERVERS OF ALL TIME."),
    ("CONTROLS", "KEYS, QUANTA, AND TERMINAL INPUT MEMORY."),
    ("QUIT", "COLLAPSE THE WAVEFUNCTION."),
)

PAUSE_MENU = ("RESUME", "QUANTUM LAB", "RECORDS", "RESTART LEVEL", "QUIT TO TITLE")


def _starfield(cv: PixelCanvas, t: float, seed: int = 7) -> None:
    rng = random.Random(seed)
    n = max(30, cv.width // 3)
    for i in range(n):
        x = rng.randrange(cv.width)
        y = rng.randrange(cv.height)
        tw = (math.sin(t * 1.7 + i * 1.3) + 1) * 0.5
        if tw < 0.22:
            continue
        col = ACCENT if i % 23 == 0 else (INK if tw > 0.8 else FAINT)
        cv.px(x, y, col)
        if i % 17 == 0 and tw > 0.9:
            cv.px(x + 1, y, DIM)
            cv.px(x, y + 1, DIM)


def _orbit(cv: PixelCanvas, cx: int, cy: int, rx: int, ry: int,
           color, dash: bool = True) -> None:
    steps = max(30, rx * 3)
    for i in range(steps):
        if dash and i % 5 == 0:
            continue
        a = math.tau * i / steps
        cv.px(round(cx + rx * math.cos(a)), round(cy + ry * math.sin(a)), color)


def _title_canvas(cols: int, rows: int, t: float) -> PixelCanvas:
    """A quiet Quandoom scan-field.  Menus and the wordmark are drawn on top;
    no sprites are baked in here, so every screen can reuse this cleanly."""
    cv = PixelCanvas(cols, rows * 2, BG)
    cv.rect(0, 0, cols, rows * 2, BG)
    # slow vertical phosphor bands
    for y in range(0, rows * 2, 3):
        shade = BG2 if (y // 3) % 2 == 0 else BG
        cv.hline(0, y, cols, shade)
    _starfield(cv, t)
    for x in range(0, cols, 12):
        for y in range(0, rows * 2, 12):
            cv.px(x, y, FAINT)
    # Animated quantum orbitals, mostly off to the right.
    for i, (rx, ry) in enumerate(((36, 12), (22, 7), (50, 17))):
        _orbit(cv, int(cols * 0.76), int(rows * 0.42),
               max(8, int(rx * cols / 120)), max(4, int(ry * rows / 40)),
               ACCENT if i == 0 else FAINT)
    # A few drifting particles add life without competing with the logo.
    for i in range(3):
        x = int((t * (7 + i * 4) + i * 31) % max(1, cols))
        y = int((t * (3 + i * 2) + i * 17) % max(1, rows * 2))
        cv.px(x, y, ACCENT if i == 0 else DIM)
    return cv


def _title_background(cols: int, rows: int, t: float) -> CellCanvas:
    return from_pixels(_title_canvas(cols, rows, t))


def _wrap_text(text: str, width: int, max_lines: int = 3) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = (line + " " + word).strip()
        if len(candidate) <= width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
            if len(lines) >= max_lines - 1:
                break
    if line and len(lines) < max_lines:
        lines.append(line)
    if lines and len(" ".join(lines)) < len(" ".join(words)):
        # Keep the final line unambiguous rather than silently dropping words.
        lines[-1] = (lines[-1][:max(1, width - 1)] + "·")[:width]
    return lines or [""]


def _format_score_row(rank: int, entry: dict | None, width: int) -> str:
    if not entry:
        return f"{rank}  ---  ------  ---"
    name = str(entry.get("name", "---"))[:3].ljust(3)
    score = int(entry.get("score", 0))
    level = str(entry.get("level", "---"))[:3]
    if width < 30:
        return f"{rank} {name} {score:06d}"
    return f"{rank}  {name}  {score:06d}  {level}"


def _top5_box(cells: CellCanvas, x: int, y: int, w: int,
              records: Records, t: float, show_best: bool = True) -> int:
    title = " TOP 5 SCORES "
    cells.hline(x, y, w, "═", FAINT)
    cells.text(x + 1, y, title, ACCENT, BG)
    yy = y + 1
    for i in range(5):
        row = records.top_scores(5)
        entry = row[i] if i < len(row) else None
        text = _format_score_row(i + 1, entry, w)
        cells.text(x + 1, yy, text[:w - 2], INK if entry else DIM, BG)
        yy += 1
    best = records.best_time()
    if show_best and best is not None:
        cells.text(x + 1, yy, f"BEST {format_time(best)}"[:w - 2], AMBER, BG)
    return yy


class Screens:
    def __init__(self) -> None:
        self.title_selected = 0
        self.last_title_cells: CellCanvas | None = None

    # ------------------------------------------------------------------
    def title(self, cols: int, rows: int, records: Records, selected: int,
              t: float, xray: bool = True) -> CellCanvas:
        cv = _title_canvas(cols, rows, t)
        if rows >= 30 and cols >= 72:
            scale = 2 if cols >= 76 else 1
            w1 = text_width("QUANTO", FONT_5x7, scale, 1)
            w2 = text_width("MARIO", FONT_5x7, scale, 1)
            y1 = 4
            y2 = y1 + 7 * scale + 3
            draw_font(cv, (cols - w1) // 2, y1, "QUANTO", INK,
                      font=FONT_5x7, scale=scale, spacing=1)
            draw_font(cv, (cols - w2) // 2, y2, "MARIO", ACCENT,
                      font=FONT_5x7, scale=scale, spacing=1)
            if cols >= 108:
                # little quantum ? block in the left margin
                q = 9
                qx, qy = 5, max(6, y1 + 4)
                cv.rect(qx, qy, q, q, BG)
                cv.outline(qx, qy, q, q, ACCENT)
                pat = ("01110", "10001", "00001", "00010", "00100", "00000", "00100")
                cv.bitmap(pat, qx + 2, qy + 1, ACCENT)
            if cols >= 136 and rows >= 30:
                art = SPRITES["mario_big_idle"]
                mscale = 1.6
                mw = len(art[0]) * mscale
                mh = len(art) * mscale
                mx = cols - int(mw) - 9
                my = max(4, (y2 + 7 * scale) // 2 - int(mh) // 2)
                cv.sprite(art, mx, my, mscale, XRAY_MAP)
                cv.hline(mx - 2, my + int(mh) + 1, int(mw) + 4, FAINT)
            header_h = (y2 + 7 * scale + 1) // 2 + 2
        else:
            if cols >= 70:
                logo = "QUANTO"
                w = text_width(logo, FONT_5x7, 1, 1)
                x0 = (cols - 66) // 2
                draw_font(cv, x0, 3, logo, INK)
                draw_font(cv, x0 + w + 1, 3, "MARIO", ACCENT)
                header_h = 5
            else:
                y1 = 1 if rows < 20 else 2
                for i, (word, color) in enumerate((("QUANTO", INK), ("MARIO", ACCENT))):
                    w = text_width(word, FONT_5x7, 1, 1)
                    draw_font(cv, (cols - w) // 2, y1 + i * 8, word, color)
                header_h = (y1 + 8 + 7 + 1) // 2
        cells = from_pixels(cv)
        subtitle = "A QUANDOOM-INSPIRED QUANTUM PLATFORMER"
        if len(subtitle) <= cols - 2 and rows >= 18:
            cells.text((cols - len(subtitle)) // 2, header_h, subtitle, DIM, BG)
            header_h += 1
        wide = cols >= 92 and rows >= 22 and header_h + 12 < rows
        if wide:
            menu_x = max(3, cols // 12)
            menu_w = min(38, max(28, cols // 2 - 4))
            score_w = min(max(30, cols - menu_x - menu_w - 6), cols - 4)
            score_x = cols - score_w - 3
            start_y = header_h + 2
        else:
            menu_w = min(cols - 4, 44)
            menu_x = max(2, (cols - menu_w) // 2)
            score_x = menu_x
            score_w = menu_w
            start_y = header_h + 1
        for i, (label, desc) in enumerate(TITLE_MENU):
            y = start_y + i
            if y >= rows - 1:
                break
            sel = i == selected
            prefix = "> " if sel else "  "
            text = (prefix + label).ljust(menu_w - 2)
            cells.text(menu_x, y, text, BG if sel else INK,
                       ACCENT if sel else BG, selected=sel)
            if not sel:
                cells.text(menu_x + menu_w - 2, y, " ", DIM, BG)
        desc_y = start_y + len(TITLE_MENU) + 1
        score_y = start_y if wide else desc_y + 1
        info_y = -1
        if score_y + 7 < rows:
            info_y = _top5_box(cells, score_x, score_y, score_w, records, t)
        elif score_y < rows - 1:
            cells.text(score_x + 1, score_y, "TOP 5 IN RECORDS", DIM, BG)
        if desc_y < rows - 2:
            desc = TITLE_MENU[min(selected, len(TITLE_MENU) - 1)][1]
            lines = _wrap_text(desc, max(10, cols - 6), 1)
            cells.text(max(2, (cols - len(lines[0])) // 2), desc_y,
                       lines[0], DIM, BG)
        info_start = max(desc_y + 2, info_y + 1)
        if wide and info_start + 1 < rows - 1:
            cells.text(score_x + 1, info_start, "14 LOGICAL QUBITS", DIM, BG)
            cells.text(score_x + 1, info_start + 1, "ONE MEASUREMENT PER FRAME", DIM, BG)
        footer = "UP/DOWN SELECT   ENTER CONFIRM   C SCAN/COLOUR   Q QUIT"
        if len(footer) > cols - 2:
            footer = "UP/DOWN  ENTER  C COLOUR  Q QUIT"
        if len(footer) > cols - 2:
            footer = "ENTER SELECT   Q QUIT"
        menu_last = start_y + min(len(TITLE_MENU), max(0, rows - 1 - start_y)) - 1
        if rows >= 16 and rows - 1 > menu_last:
            cells.text(max(0, (cols - len(footer)) // 2), rows - 1,
                       footer[:cols], FAINT, BG)
        return cells

    def records(self, cols: int, rows: int, records: Records, t: float,
                xray: bool = True) -> CellCanvas:
        cells = _title_background(cols, rows, t)
        title = "HALL OF COLLAPSE"
        cells.text(max(1, (cols - len(title)) // 2), 2, title, INK, BG)
        cells.hline(max(2, (cols - len(title)) // 2), 3, min(len(title), cols - 2),
                    "═", ACCENT)
        wide = cols >= 86 and rows >= 22
        y = 5
        if wide:
            left_w = min(48, (cols - 6) // 2)
            right_x = left_w + 6
            right_w = cols - right_x - 2
            self._score_table(cells, 2, y, left_w, records, rows)
            self._run_table(cells, right_x, y, right_w, records, rows)
        else:
            yy = _top5_box(cells, 2, y, cols - 4, records, t, show_best=False)
            y2 = yy + 1
            if rows - y2 >= 9:
                self._run_table(cells, 2, y2, cols - 4, records, rows)
            else:
                best = records.best_time()
                if best is not None and y2 < rows - 2:
                    name = ""
                    runs = records.top_speedruns(1)
                    if runs:
                        name = str(runs[0].get("name", ""))[:3]
                    line = f"BEST SPEEDRUN  {name:<3} {format_time(best)}"
                    cells.text(2, y2, line[:cols - 4], AMBER, BG)
        cells.text(2, rows - 1, "P/ESC/ENTER BACK", FAINT, BG)
        return cells

    def _score_table(self, cells: CellCanvas, x: int, y: int, w: int,
                     records: Records, rows: int) -> None:
        cells.hline(x, y, w, "═", FAINT)
        cells.text(x + 1, y, " TOP 5 SCORES ", ACCENT, BG)
        entries = records.top_scores(5)
        for i in range(5):
            entry = entries[i] if i < len(entries) else None
            row = _format_score_row(i + 1, entry, w)
            cells.text(x + 1, y + 1 + i, row[:w - 2], INK if entry else DIM, BG)
        best = records.best_score()
        cells.text(x + 1, y + 7, f"PERSONAL BEST  {best:06d}" if best else "NO RUNS YET",
                   AMBER, BG)
        if rows > y + 11:
            cells.text(x + 1, y + 9, "STORY RUNS ARE RANKED BY SCORE.", DIM, BG)
            cells.text(x + 1, y + 10, "SPEEDRUNS ARE RANKED BY IGT.", DIM, BG)

    def _run_table(self, cells: CellCanvas, x: int, y: int, w: int,
                   records: Records, rows: int) -> None:
        if w < 10 or y >= rows:
            return
        cells.hline(x, y, w, "═", FAINT)
        cells.text(x + 1, y, " TOP 5 SPEEDRUNS ", AMBER, BG)
        entries = records.top_speedruns(5)
        for i in range(5):
            entry = entries[i] if i < len(entries) else None
            if entry:
                name = str(entry.get("name", "---"))[:3].ljust(3)
                line = f"{i + 1}  {name}  {format_time(float(entry.get('time', 0)))}"
            else:
                line = f"{i + 1}  ---  --:--.---"
            cells.text(x + 1, y + 1 + i, line[:w - 2], INK if entry else DIM, BG)
        if y + 7 < rows:
            cells.text(x + 1, y + 7, "CATEGORY: ANY% / 5 WORLDS", DIM, BG)
            best = records.best_time()
            if best is not None:
                cells.text(x + 1, y + 8, f"WORLD RECORD {format_time(best)}", AMBER, BG)

    # ------------------------------------------------------------------
    def controls(self, cols: int, rows: int, t: float) -> CellCanvas:
        cells = _title_background(cols, rows, t)
        title = "OBSERVER MANUAL"
        cells.text(max(1, (cols - len(title)) // 2), 1, title, INK, BG)
        cells.hline(max(2, (cols - len(title)) // 2), 2, min(len(title), cols - 2),
                    "═", ACCENT)
        if cols < 64:
            lines = [
                ("A/D", "MOVE"), ("W/SPACE", "JUMP"), ("S", "DROP/FASTFALL"),
                ("E", "QUANTUM DASH"), ("X", "TOGGLE SPRINT"),
                ("P/ESC", "PAUSE"), ("G", "CIRCUIT LAB"),
                ("C", "X-RAY / COLOUR"), ("Q", "QUIT TO TITLE"),
            ]
            y = 4
            for key, desc in lines:
                if y >= rows - 3:
                    break
                cells.text(2, y, key.ljust(9), ACCENT, BG)
                cells.text(12, y, desc[:cols - 13], INK, BG)
                y += 1
            note = "PRESS-ONLY INPUT / 0.3S MEMORY"
            if y < rows - 1:
                cells.text(2, y + 1, note[:cols - 4], DIM, BG)
        else:
            lines = [
                ("A / D  or  ARROWS", "RUN LEFT / RIGHT"),
                ("W / SPACE / UP", "JUMP (NO KEY-UP EVENT EXISTS)"),
                ("S / DOWN", "DROP THROUGH / FAST-FALL"),
                ("E", "QUANTUM DASH - 40 FLUX, PHASES ENEMIES"),
                ("X", "TOGGLE SPRINT"),
                ("P / ESC", "PAUSE / OBSERVER MENU"),
                ("G", "OPEN THE QUANTUM CIRCUIT LAB"),
                ("C", "TOGGLE X-RAY / CLASSIC RENDER"),
                ("Q", "QUIT FROM TITLE OR PAUSE"),
            ]
            y = 4
            for key, desc in lines:
                if y >= rows - 7:
                    break
                cells.text(3, y, key.ljust(20), ACCENT, BG)
                cells.text(25, y, desc[:max(0, cols - 27)], INK, BG)
                y += 1
            info = [
                "TERMINAL INPUT IS PRESS-ONLY. MOVEMENT USES A SHORT",
                "INPUT-MEMORY WINDOW; AIR MOMENTUM KEEPS JUMPS FLOWING.",
            ]
            yy = y + 1
            for line in info:
                if yy < rows - 1:
                    cells.text(3, yy, line[:cols - 4], DIM, BG)
                    yy += 1
            if yy + 1 < rows - 1:
                cells.text(3, yy + 1, "ENTANGLED COINS COLLAPSE IN PAIRS.", VIOLET, BG)
            if yy + 2 < rows - 1:
                cells.text(3, yy + 2, "? BLOCKS USE A MEASURED QUBIT FOR THEIR REWARD.",
                           VIOLET, BG)
            if yy + 3 < rows - 1:
                cells.text(3, yy + 3, "H IN THE LAB EXPLAINS EVERY PANEL.", VIOLET, BG)
        cells.text(2, rows - 1, "P/ESC/ENTER BACK", FAINT, BG)
        return cells

    # ------------------------------------------------------------------
    # in-game overlays
    # ------------------------------------------------------------------
    def pause(self, base: CellCanvas, cols: int, rows: int, game, selected: int,
              t: float) -> CellCanvas:
        cells = dim_cells(base, 0.14)
        w = min(cols - 4, 58)
        h = 13
        x = (cols - w) // 2
        y = max(1, (rows - h) // 2)
        cells.clear_rect(x, y, w, h, BG)
        cells.box(x, y, w, h, ACCENT, BG, double=True, title="OBSERVER PAUSED")
        if w >= 50:
            world = f"WORLD {game.level.key}  {game.level.name}"
        else:
            world = f"{game.level.key}  {game.level.name}"
        cells.text(x + 3, y + 2, world[:w - 6], DIM, BG)
        cells.text(x + 3, y + 3,
                   f"SCORE {max(0, game.run.score):06d}   COINS {game.run.coins:02d}"[:w - 6],
                   INK, BG)
        for i, label in enumerate(PAUSE_MENU):
            yy = y + 5 + i
            sel = i == selected
            text = ("> " if sel else "  ") + label
            if sel:
                text = text.ljust(w - 8)
            cells.text(x + 4, yy, text, BG if sel else INK,
                       ACCENT if sel else BG, selected=sel)
        if w >= 46:
            hint = "ENTER SELECT   P RESUME   G LAB   Q TITLE"
        else:
            hint = "ENTER  P RESUME  G LAB  Q"
        cells.text(x + 3, y + h - 2, hint[:w - 6], FAINT, BG)
        return cells

    def intro(self, base: CellCanvas, cols: int, rows: int, game, t: float) -> CellCanvas:
        cells = dim_cells(base, 0.15)
        w = min(cols - 4, 70)
        sub_lines = _wrap_text(game.level.subtitle, max(10, w - 8), 2)
        h = min(rows - 2, max(9, 6 + len(sub_lines)))
        x = (cols - w) // 2
        y = max(1, (rows - h) // 2)
        cells.clear_rect(x, y, w, h, BG)
        cells.box(x, y, w, h, ACCENT, BG, double=True, title=game.level.world)
        name = game.level.name[:w - 8]
        cells.text((cols - len(name)) // 2, y + 2, name, INK, BG)
        for i, line in enumerate(sub_lines):
            cells.text((cols - len(line)) // 2, y + 3 + i, line, DIM, BG)
        if w >= 52:
            cues = "MOVE A/D   JUMP W/SPACE   DASH E   PAUSE P"
        else:
            cues = "A/D MOVE   W JUMP   E DASH"
        cells.text((cols - len(cues)) // 2, y + h - 3, cues[:w - 6], FAINT, BG)
        prompt = "ENTER / SPACE TO COLLAPSE"
        if len(prompt) > w - 4:
            prompt = "ENTER TO COLLAPSE"
        cells.text((cols - len(prompt)) // 2, y + h - 2, prompt, ACCENT, BG)
        return cells

    def toast(self, cells: CellCanvas, text: str, color=ACCENT) -> None:
        x = max(1, (cells.width - len(text)) // 2)
        if 1 <= cells.height:
            for xx in range(max(0, x - 2), min(cells.width, x + len(text) + 2)):
                cells.cells[1][xx].ch = " "
                cells.cells[1][xx].bg = BG
            cells.text(x, 1, text[:cells.width - 2], color, BG)

    def level_clear(self, cols: int, rows: int, game, t: float,
                    next_level: int, total_levels: int, pb_before: float | None,
                    speedrun: bool) -> CellCanvas:
        cv = _title_canvas(cols, rows, t)
        if rows >= 32 and cols >= 100:
            scale, words = 2, ("COURSE", "CLEAR")
            y0, gap = 4, 3
        elif rows >= 22 and cols >= 64:
            scale, words = 1, ("COURSE CLEAR",)
            y0, gap = 4, 2
        else:
            scale, words = 1, ("COURSE", "CLEAR")
            y0, gap = 1, 1
        ty = y0
        for word in words:
            w = text_width(word, FONT_5x7, scale, 1)
            if w <= cols - 2:
                draw_font(cv, (cols - w) // 2, ty, word,
                          ACCENT if word == "CLEAR" else INK,
                          font=FONT_5x7, scale=scale, spacing=1)
            ty += 7 * scale + gap
        cells = from_pixels(cv)
        header = ty // 2 + 2
        cells.hline(max(2, cols // 8), header - 1, max(4, cols - cols // 4),
                    "─", FAINT, BG)
        run = game.run
        full = f"{game.level.world}  {game.level.name}"
        if len(full) > cols - 2:
            full = game.level.name
        lines: list[tuple[str, tuple[int, int, int]]] = [
            (full[:cols - 2], INK),
            (f"LEVEL TIME  {format_time(game.level_time)}", ACCENT),
            (f"SCORE {max(0, run.score):06d}   COINS {run.coins:02d}", INK),
            (f"QPU COLLAPSES  {game.qresult.frame if game.qresult else 0:05d}", DIM),
        ]
        if speedrun:
            lines.append((f"RUN TIME  {format_time(run.run_time)}   DEATHS {run.deaths:02d}",
                          AMBER))
            if next_level >= total_levels and pb_before is not None:
                delta = run.run_time - pb_before
                lines.append((f"PB {format_time(pb_before)}   DELTA {delta:+.3f}S",
                              ACCENT if delta < 0 else DIM))
        y = header
        for text, color in lines:
            if y >= rows - 2:
                break
            if len(text) <= cols - 2:
                cells.text(max(1, (cols - len(text)) // 2), y, text, color, BG)
            y += 1
        # A compact split ribbon when there is room for it.
        if rows >= 28 and speedrun and run.splits:
            pieces = [f"{i + 1}:{format_time(v)}" for i, v in enumerate(run.splits[-5:])]
            ribbon = "Splits " + "  ".join(pieces)
            if len(ribbon) <= cols - 4:
                cells.text(max(2, (cols - len(ribbon)) // 2), y + 1, ribbon, DIM, BG)
        if next_level < total_levels:
            prompt = "ENTER: NEXT WORLD"
        else:
            prompt = "ENTER: FINAL OBSERVATION"
        cells.text(max(1, (cols - len(prompt)) // 2), rows - 2, prompt, INK, BG)
        if rows >= 18:
            hint = "ENTER / SPACE TO CONTINUE"
            cells.text(max(1, (cols - len(hint)) // 2), rows - 1, hint, FAINT, BG)
        return cells

    def results(self, cols: int, rows: int, records: Records, run, game,
                t: float, victory: bool, qualified: bool,
                next_hint: str = "ENTER: RETURN TO TITLE") -> CellCanvas:
        title = "VICTORY" if victory else "GAME OVER"
        cells: CellCanvas
        if rows < 20:
            cells = _title_background(cols, rows, t)
            cells.hline(1, 2, cols - 2, "─", FAINT, BG)
            cells.text(max(1, (cols - len(title)) // 2), 1,
                       title, ACCENT if victory else HAZARD, BG)
            header = 3
        else:
            cv = _title_canvas(cols, rows, t)
            scale = 2 if cols >= 88 and rows >= 24 else 1
            y0 = 4
            w = text_width(title, FONT_5x7, scale, 1)
            # Put a quiet opaque band behind the wordmark; the starfield is
            # charming around it, but specks inside the glyphs hurt reading.
            cv.rect(max(0, (cols - w) // 2 - 4), max(0, y0 - 2),
                    w + 8, 7 * scale + 4, BG)
            draw_font(cv, (cols - w) // 2, y0, title,
                      ACCENT if victory else HAZARD,
                      font=FONT_5x7, scale=scale, spacing=1)
            cells = from_pixels(cv)
            cells.hline(max(2, cols // 8), (y0 + 7 * scale + 1) // 2 + 1,
                        max(4, cols - cols // 4), "─", FAINT, BG)
            header = (y0 + 7 * scale + 1) // 2 + 3
        mode = "SPEEDRUN" if run.speedrun else "STORY"
        if run.speedrun:
            stats = [f"SPEEDRUN   TIME {format_time(run.run_time)}   DEATHS {run.deaths:02d}",
                     f"SCORE {max(0, run.score):07d}   COINS {run.coins:02d}   "
                     f"WORLD {run.level_index + 1}/5"]
        else:
            stats = [f"STORY   SCORE {max(0, run.score):07d}   COINS {run.coins:02d}",
                     f"LIVES {max(0, run.lives)}   WORLD {run.level_index + 1}/5"]
        stats.append(f"QPU COLLAPSES {game.qresult.frame if game and game.qresult else 0:05d}")
        y = header
        for line in stats:
            if y >= rows - 2:
                break
            if len(line) <= cols - 2:
                cells.text(max(1, (cols - len(line)) // 2), y,
                           line, INK if line.startswith(("STORY", "SPEEDRUN")) else DIM, BG)
            y += 1
        if qualified and y < rows - 3:
            text = "TOP-FIVE RECORD"
            cells.text(max(1, (cols - len(text)) // 2), y, text, AMBER, BG)
            y += 1
        if rows < 20:
            table_y = max(y + 1, 5)
            w = cols - 4
            yy = (_top5_box(cells, 2, table_y, w, records, t, show_best=False)
                  if table_y + 6 < rows else table_y)
            if yy + 1 < rows - 1:
                best = records.best_time()
                if best is not None:
                    runs = records.top_speedruns(1)
                    name = str(runs[0].get("name", ""))[:3] if runs else ""
                    line = f"BEST RUN  {name:<3} {format_time(best)}"
                    cells.text(2, yy + 1, line[:cols - 4], AMBER, BG)
        elif cols >= 92 and rows >= 32:
            left_w = min(48, (cols - 10) // 2)
            right_x = left_w + 7
            right_w = cols - right_x - 3
            table_y = max(y + 2, rows - 20)
            self._score_table(cells, 2, table_y, left_w, records, rows)
            self._run_table(cells, right_x, table_y, right_w, records, rows)
            if run.speedrun and run.splits and table_y + 10 < rows - 2:
                pieces = [f"{i + 1}:{format_time(v)}" for i, v in enumerate(run.splits[-5:])]
                ribbon = "SPLITS  " + "  ".join(pieces)
                if len(ribbon) <= cols - 4:
                    cells.text(max(2, (cols - len(ribbon)) // 2), table_y + 11,
                               ribbon, DIM, BG)
        else:
            table_y = max(y + 1, 10) if rows >= 22 else y + 1
            w = min(60, cols - 4)
            x = (cols - w) // 2
            if table_y + 6 < rows:
                yy = _top5_box(cells, x, table_y, w, records, t, show_best=False)
                best = records.best_time()
                if best is not None and yy + 1 < rows - 1:
                    runs = records.top_speedruns(1)
                    name = str(runs[0].get("name", ""))[:3] if runs else ""
                    line = f"BEST RUN  {name:<3} {format_time(best)}"
                    if len(line) <= w - 2:
                        cells.text(x + 1, yy + 1, line, AMBER, BG)
        cells.text(max(1, (cols - len(next_hint)) // 2), rows - 1,
                   next_hint[:cols - 2], FAINT, BG)
        return cells

    def name_entry(self, cols: int, rows: int, name: str, score: int,
                   time_value: float | None, t: float,
                   rank_hint: str = "") -> CellCanvas:
        cells = _title_background(cols, rows, t)
        box_w = min(cols - 4, 46)
        box_h = min(11, rows - 4)
        x = (cols - box_w) // 2
        y = max(4, (rows - box_h) // 2 + 1)
        title_y = max(1, y - 3)
        title = "NEW OBSERVER"
        cells.text(max(1, (cols - len(title)) // 2), title_y, title, INK, BG)
        cells.hline(max(2, (cols - len(title)) // 2), title_y + 1,
                    min(len(title), cols - 2), "═", ACCENT)
        cells.clear_rect(x, y, box_w, box_h, BG)
        cells.box(x, y, box_w, box_h, ACCENT, BG, double=True, title="INITIALS")
        shown = name.ljust(3, "_")
        cells.text(max(1, (cols - 7) // 2), y + 2, " ".join(shown), INK, BG)
        if rank_hint:
            cells.text(max(1, (cols - len(rank_hint)) // 2), y + 4,
                       rank_hint[:box_w - 4], AMBER, BG)
        if time_value is not None:
            line = f"TIME  {format_time(time_value)}"
        else:
            line = f"SCORE {score:07d}"
        cells.text(max(1, (cols - len(line)) // 2), y + 5, line[:box_w - 4], DIM, BG)
        hint = "A-Z   BACKSPACE   ENTER SAVE"
        if len(hint) > box_w - 4:
            hint = "A-Z  BKSP  ENTER"
        cells.text(max(1, (cols - len(hint)) // 2), y + box_h - 2, hint, FAINT, BG)
        return cells

    # ------------------------------------------------------------------
    # quantum lab
    # ------------------------------------------------------------------
    def lab(self, base: CellCanvas, cols: int, rows: int, game, t: float,
            message: str = "") -> CellCanvas:
        # The lab is a read-only instrument panel.  A flat background keeps
        # every wire and bit legible, even in a 40x16 terminal.
        cells = CellCanvas(cols, rows, INK, BG)
        oracle = game.oracle
        q = oracle.last_result
        compact = rows < 21 or cols < 52
        footer_y = rows - 1 if rows >= 18 else None
        title = (f"QUANTUM LAB / FRAME {q.frame:05d}" if cols >= 60 and q
                 else "QUANTUM LAB")
        cells.text(1, 0, title[:cols - 2], ACCENT, BG)
        if cols >= 60:
            stats = (f"QUBITS 14   GATES {q.gate_count if q else 0:02d}   "
                     f"DEPTH {q.depth if q else 0:02d}   "
                     f"SAMPLE {q.sample_time_ms if q else 0.0:.2f}MS")
        else:
            stats = (f"14Q G{q.gate_count if q else 0:02d} "
                     f"D{q.depth if q else 0:02d} "
                     f"{q.sample_time_ms if q else 0.0:.1f}MS")
        cells.text(1, 1, stats[:cols - 2], DIM, BG)
        if compact and cols >= 34:
            cells.text(cols - 7, 1, "G BACK", FAINT, BG)
        wide = cols >= 100
        right_w = 32 if wide else 0
        left_w = cols - right_w - 4
        if compact:
            left_x = 1
            panel_y = 2
            panel_h = 0
        else:
            left_x = 2
            panel_y = 3
            panel_h = rows - panel_y - (1 if footer_y is not None else 0)
            cells.clear_rect(1, panel_y, left_w, panel_h, BG)
            cells.box(1, panel_y, left_w, panel_h, FAINT, BG,
                      double=False, title="FRAME CIRCUIT")
        if wide:
            rx = left_w + 2
            cells.clear_rect(rx, panel_y, right_w, panel_h, BG)
            cells.box(rx, panel_y, right_w, panel_h, FAINT, BG,
                      double=False, title="OBSERVABLES")
        layers = oracle.last_circuit.layers() if oracle.last_circuit else []
        label_w = 8
        layer_w = 4
        qy = panel_y if compact else panel_y + 2
        base_x = left_x + label_w
        line_w = max(8, left_w - label_w - (1 if compact else 4))
        max_layers = max(1, (line_w - 3) // layer_w)
        show = layers[-max_layers:] if layers else []
        for qi in range(14):
            row = qy + qi
            if row >= rows:
                break
            cells.text(left_x, row, f"q{qi:<2}", DIM, BG)
            role = QUBIT_NAMES[qi]
            cells.text(left_x + 4, row, role[:4], FAINT if qi not in (12, 13) else ACCENT, BG)
            cells.hline(base_x, row, line_w, "─", FAINT, BG)
        for li, layer in enumerate(show):
            cx = base_x + li * layer_w + 1
            if cx >= base_x + line_w - 1:
                break
            for gate in layer:
                if gate.name in ("cx", "cz", "ccx"):
                    for qq in gate.qubits[:-1]:
                        if qy + qq < rows:
                            cells.put(cx, qy + qq, "●", ACCENT, BG)
                    target = gate.qubits[-1]
                    if qy + target < rows:
                        cells.put(cx, qy + target, "●" if gate.name == "cz" else "⊕",
                                  INK, BG)
                    lo, hi = min(gate.qubits), max(gate.qubits)
                    for qq in range(lo + 1, hi):
                        if qy + qq < rows:
                            cells.put(cx, qy + qq, "│", FAINT, BG)
                else:
                    row = qy + gate.qubits[0]
                    if row < rows:
                        cells.put(cx, row, gate.symbol()[:1], INK, BG)
        mx = base_x + len(show) * layer_w + 1
        if mx < left_x + left_w - 1:
            if not compact and panel_y + 1 < rows:
                cells.put(mx, panel_y + 1, "M", DIM, BG)
                label = "MEASURED"
                cells.text(max(left_x + 1, left_x + left_w - len(label) - 2),
                           panel_y + 1, label, DIM, BG)
            for qi in range(14):
                row = qy + qi
                if row >= rows:
                    break
                bit = q.bits[qi] if q else 0
                cells.put(mx, row, "1" if bit else "0",
                          ACCENT if bit else FAINT, BG)
        circuit_bottom = qy + 13
        note_y = circuit_bottom + 2
        if note_y < rows - (1 if footer_y is not None else 0):
            cells.text(left_x + 1, note_y,
                       f"LAST {len(show)} OF {len(layers)} LAYERS"[:left_w - 3],
                       FAINT, BG)
        qasm_top = note_y + 3
        if not compact and rows >= 28 and qasm_top < rows - 3:
            cells.hline(2, qasm_top - 1, left_w - 2, "─", FAINT, BG)
            cells.text(3, qasm_top - 1, " OPENQASM 2.0 / CURRENT FRAME ",
                       DIM, BG)
            qasm_lines = oracle.qasm().splitlines()
            max_lines = max(0, rows - qasm_top - 2)
            for i, line in enumerate(qasm_lines[:max_lines]):
                color = ACCENT if i == 3 else (FAINT if line.startswith("//") else DIM)
                cells.text(3, qasm_top + i, line[:left_w - 5], color, BG)
        if wide:
            content_x = left_w + 4
            ry = panel_y + 2
            bitstring = q.bitstring if q else "0" * 14
            if ry < rows:
                cells.text(content_x, ry, "|psi> " + bitstring[:right_w - 8],
                           INK, BG)
            hy = ry + 2
            if hy < rows:
                cells.text(content_x, hy, "MARGINAL P(1)", ACCENT, BG)
            picks = [12, 13, 8, 9, 10, 11]
            for i, qi in enumerate(picks):
                row = hy + 1 + i
                if row >= rows:
                    break
                p = q.marginals[qi] if q else 0.5
                bar = "#" * int(round(p * 9))
                line = f"{QUBIT_NAMES[qi]:<5}{p * 100:5.1f}% [{bar:<9}]"
                cells.text(content_x, row, line[:right_w - 4],
                           INK if qi in (12, 13) else DIM, BG)
            hist_y = hy + 8
            if hist_y + 1 < rows:
                cells.text(content_x, hist_y, "ENTROPY 4-BIT / 96 SHOTS", ACCENT, BG)
                hist = oracle.histogram(range(8, 12))
                maxv = max(hist.values()) if hist else 1
                def draw_bin(x: int, bin_index: int, row: int) -> None:
                    count = hist.get(bin_index, 0)
                    bar = "█" * max(0, min(7, round(count / maxv * 7)))
                    cells.text(x, row, f"{bin_index:02d}", FAINT, BG)
                    cells.text(x + 3, row, f"{count:02d}", INK, BG)
                    cells.text(x + 6, row, bar, ACCENT if count == maxv else DIM, BG)
                for i in range(8):
                    row = hist_y + 1 + i
                    if row >= rows:
                        break
                    draw_bin(content_x, i, row)
                    draw_bin(content_x + 14, i + 8, row)
                meta_row = hist_y + 10
                if meta_row < rows - 1:
                    cells.text(content_x, meta_row,
                               f"FRAME {q.frame if q else 0:05d}  /  SHOTS 96", FAINT, BG)
        if footer_y is not None:
            if message:
                hint = message
                color = AMBER
            elif cols >= 84:
                hint = "G/ESC RESUME   X EXPORT FRAME.QASM   C SCAN/COLOUR   H HELP"
                color = FAINT
            elif cols >= 56:
                hint = "G/ESC BACK   X QASM   C COLOUR   H HELP"
                color = FAINT
            else:
                hint = "G BACK   X QASM   C COLOR   H HELP"
                color = FAINT
            cells.text(max(1, (cols - len(hint)) // 2), footer_y,
                       hint[:cols - 2], color, BG)
        elif message and rows >= 2:
            cells.text(1, 1, message[:cols - 2], AMBER, BG)
        return cells


    def lab_help(self, cols: int, rows: int, t: float,
                 xray: bool = True) -> CellCanvas:
        """Explain what the lab is looking at and why it is a freeze-frame."""
        cells = CellCanvas(cols, rows, INK, BG)
        title = "QUANTUM LAB / HELP"
        cells.text(1, 0, title[:cols - 2], ACCENT, BG)
        cells.hline(1, 1, cols - 2, "─", FAINT)
        footer = rows - 1

        if cols < 72 or rows < 24:
            compact_lines: list[tuple[str, tuple[int, int, int]]] = [
                ("SNAPSHOT, NOT LIVE", ACCENT),
                ("Gameplay pauses here, so no new", INK),
                ("circuits run. Frame, bits and", INK),
                ("histogram stay frozen.", INK),
                ("Back out, move, reopen to compare.", DIM),
                ("M = measured bits. HIST = 96", DIM),
                ("sampled shots from the last run.", DIM),
                ("q0-4 input   q5-7 phase", VIOLET),
                ("q8-11 entropy  q12 reward", VIOLET),
                ("q13 echo", VIOLET),
                ("X QASM   C COLOUR   H HELP", FAINT),
            ]
            y = 3
            for text, color in compact_lines:
                if y >= footer:
                    break
                cells.text(2, y, text[:cols - 4], color, BG)
                y += 1
        else:
            def section(x: int, y: int, width: int, heading: str,
                        body: list[str], color: tuple[int, int, int] = INK) -> int:
                if y >= footer:
                    return y
                cells.text(x, y, heading[:width], ACCENT, BG)
                y += 1
                for para in body:
                    for line in _wrap_text(para, max(8, width - 2), 8):
                        if y >= footer:
                            return y
                        cells.text(x + 2, y, line[:width - 2], color, BG)
                        y += 1
                return y + 1

            if cols >= 96 and rows >= 30:
                left_x, right_x = 2, 0
                left_w = (cols - 7) // 2
                right_x = left_x + left_w + 3
                right_w = cols - right_x - 2
                ly = 3
                ly = section(left_x, ly, left_w, "SNAPSHOT, NOT LIVE", [
                    "This is the last simulated frame, not a live loop. "
                    "Gameplay pauses while the lab is open, so the oracle "
                    "does not tick. The frame counter, measured bits and "
                    "histogram stay frozen. Back out, move, then reopen to "
                    "compare frames.",
                ])
                ly = section(left_x, ly, left_w, "WHAT RUNS EACH FRAME", [
                    "Every gameplay step loads controls, speed, flux and world "
                    "into 14 qubits, applies about 40 gates, then samples a "
                    "16,384-amplitude state vector. The measured bits drive "
                    "rewards, enemy moods and visual decoherence.",
                ])
                ly = section(left_x, ly, left_w, "QUBIT ROLES", [
                    "q0-4 input: L R JMP RUN FLX",
                    "q5-7 phase register",
                    "q8-11 entropy register",
                    "q12 reward / ? blocks",
                    "q13 echo / afterimages",
                ], VIOLET)
                ry = 3
                ry = section(right_x, ry, right_w, "READING THE PANEL", [
                    "Gate grid: the last 7 circuit layers.",
                    "M: measured 0/1 bit for each qubit.",
                    "P(1): marginal probability for selected qubits.",
                    "HIST: 96 shots sampled from the last distribution.",
                    "SAMPLE: state-vector execution time. GATES/DEPTH "
                    "describe the displayed frame.",
                ])
                ry = section(right_x, ry, right_w, "GAMEPLAY EFFECTS", [
                    "The register is really simulated, but it is game "
                    "instrumentation: it does not make Mario's gravity or "
                    "collisions quantum. It chooses contextual outcomes such "
                    "as block rewards, coin luck, enemy moods and ghost "
                    "trails. Platformer physics remain classical.",
                ])
                ry = section(right_x, ry, right_w, "LAB KEYS", [
                    "X export frame.qasm in the current directory.",
                    "C toggle x-ray / classic rendering.",
                    "H this help. G/ESC/Enter return to the lab.",
                ], DIM)
            else:
                y = 3
                y = section(2, y, cols - 4, "SNAPSHOT, NOT LIVE", [
                    "This is the last simulated frame, not a live loop. "
                    "Gameplay pauses, so no new circuits run. Frame, bits and "
                    "histogram stay frozen; back out, move, reopen to compare.",
                ])
                y = section(2, y, cols - 4, "WHAT RUNS EACH FRAME", [
                    "Controls, speed, flux and world enter 14 qubits. About "
                    "40 gates act on a 16,384-amplitude state vector. The "
                    "measurement drives rewards, enemy moods and decoherence. "
                    "Platformer physics remain classical.",
                ])
                y = section(2, y, cols - 4, "QUBIT ROLES", [
                    "q0-4 input L/R/JMP/RUN/FLX    q5-7 phase",
                    "q8-11 entropy    q12 reward    q13 echo",
                ], VIOLET)
                y = section(2, y, cols - 4, "READING THE PANEL", [
                    "M = measured bits. P(1) = marginal probability. "
                    "HIST = 96 sampled shots. SAMPLE = execution time.",
                ])
                y = section(2, y, cols - 4, "LAB KEYS", [
                    "X export frame.qasm   C colour   G/ESC/Enter back",
                ], DIM)
        hint = "H/G/ESC/ENTER BACK TO LAB"
        if cols >= 64:
            hint += "   C COLOUR"
        cells.text(max(1, (cols - len(hint)) // 2), footer,
                   hint[:cols - 2], FAINT, BG)
        return cells


def dim_cells(cells: CellCanvas, factor: float) -> CellCanvas:
    out = CellCanvas(cells.width, cells.height)
    for y, row in enumerate(cells.cells):
        for x, cell in enumerate(row):
            out.cells[y][x].ch = cell.ch
            out.cells[y][x].fg = tuple(int(c * factor) for c in cell.fg)
            out.cells[y][x].bg = tuple(int(c * factor) for c in cell.bg)
    return out


def cells_to_pixels(cells: CellCanvas) -> PixelCanvas:
    """Development helper used by docs/screenshot tooling."""
    pc = PixelCanvas(cells.width, cells.height * 2)
    for y, row in enumerate(cells.cells):
        for x, cell in enumerate(row):
            pc.px(x, y * 2, cell.fg)
            pc.px(x, y * 2 + 1, cell.bg)
    return pc
