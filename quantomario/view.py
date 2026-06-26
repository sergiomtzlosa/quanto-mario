"""Quandoom-flavoured scene renderer: x-ray playfield, scan-line HUD, effects."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Iterable

from .entities import Enemy, Particle
from .fonts import FONT_3x5, FONT_5x7, draw_text as draw_font, text_width
from .game import Game, TILE
from .render import CellCanvas, FULL, PixelCanvas, UP, from_pixels
from .scores import format_short_time
from .sprites import BOSS, SPRITES


@dataclass
class Layout:
    cols: int
    rows: int
    hud_rows: int
    game_cell_rows: int
    game_px_h: int
    tile_px: int
    scale: float
    view_w: float
    view_h: float

    @property
    def big_hud(self) -> bool:
        return self.hud_rows >= 7

    @property
    def playable(self) -> bool:
        return self.cols >= 40 and self.rows >= 16


def compute_layout(cols: int, rows: int) -> Layout:
    big = cols >= 112 and rows >= 32
    if big:
        hud_rows = 7
    elif rows >= 20:
        hud_rows = 3
    else:
        hud_rows = 2
    game_cell_rows = max(1, rows - hud_rows)
    game_px_h = game_cell_rows * 2
    tile_px = int(max(4, min(12, round(game_px_h / 8.6))))
    scale = tile_px / TILE
    view_w = cols * TILE / tile_px
    view_h = game_px_h * TILE / tile_px
    return Layout(cols, rows, hud_rows, game_cell_rows, game_px_h,
                  tile_px, scale, view_w, view_h)


class SceneRenderer:
    def __init__(self, xray: bool = True) -> None:
        self.xray = xray
        self.trail: list[tuple[float, float, float, bool, float]] = []
        self.frame = 0
        self.last_layout: Layout | None = None
        self.star_salt = 17
        self.high_score = 0

    # ------------------------------------------------------------------
    def render(self, game: Game, cols: int, rows: int) -> CellCanvas:
        layout = compute_layout(cols, rows)
        self.last_layout = layout
        self.frame += 1
        canvas = PixelCanvas(cols, rows * 2, game.level.theme.bg)
        self._draw_world(canvas, game, layout)
        if layout.big_hud:
            self._draw_big_hud(canvas, game, layout)
        else:
            self._draw_compact_hud(canvas, game, layout)
        self.last_pixels = canvas
        cells = from_pixels(canvas)
        # HUD text overlays and border are cell-native and stay crisp.
        self._hud_text(cells, game, layout)
        return cells

    # ------------------------------------------------------------------
    # world / background
    # ------------------------------------------------------------------
    def _draw_world(self, cv: PixelCanvas, game: Game, L: Layout) -> None:
        th = game.level.theme
        game_h = L.game_px_h
        self._background(cv, game, L)
        self._draw_tiles(cv, game, L)
        self._draw_flag_and_castle(cv, game, L)
        self._draw_checkpoints(cv, game, L)
        self._draw_platforms(cv, game, L)
        self._draw_beams(cv, game, L)
        for coin in game.coins:
            if not coin.collected:
                self._draw_coin(cv, game, coin, L)
        for m in game.mushrooms:
            if m.alive:
                self._draw_mushroom(cv, game, m, L)
        for e in game.enemies:
            if e.alive:
                self._draw_enemy(cv, game, e, L)
        for f in game.fireballs:
            if f.alive:
                self._draw_fireball(cv, game, f, L)
        for particle in game.particles:
            self._draw_particle(cv, game, particle, L)
        self._draw_player(cv, game, L)
        for popup in game.popups:
            self._draw_popup(cv, game, popup, L)
        if game.boss and game.boss.alive:
            self._draw_boss_hp(cv, game, L)

    def _sx(self, game: Game, L: Layout, wx: float) -> float:
        sx = (wx - game.camera_x) * L.scale
        if game.shake > 0:
            sx += math.sin(game.time * 91.0) * game.shake_mag * game.shake
        return sx

    def _sy(self, game: Game, L: Layout, wy: float) -> float:
        sy = (wy - game.camera_y) * L.scale
        if game.shake > 0:
            sy += math.cos(game.time * 77.0) * game.shake_mag * game.shake
        return sy

    def _tile_rect(self, game: Game, L: Layout, tx: int, ty: int) -> tuple[int, int, int, int]:
        x0 = round((tx * TILE - game.camera_x) * L.scale)
        y0 = round((ty * TILE - game.camera_y) * L.scale)
        x1 = round(((tx + 1) * TILE - game.camera_x) * L.scale)
        y1 = round(((ty + 1) * TILE - game.camera_y) * L.scale)
        return x0, y0, max(1, x1 - x0), max(1, y1 - y0)

    def _background(self, cv: PixelCanvas, game: Game, L: Layout) -> None:
        th = game.level.theme
        gh = L.game_px_h
        band_colors = [th.bg2, th.bg, th.bg, th.bg]
        band_h = max(1, gh // len(band_colors))
        for i, col in enumerate(band_colors):
            cv.rect(0, i * band_h, L.cols, band_h + 1, col)
        # faint horizon grid
        faint = th.faint
        horizon = int(gh * 0.78)
        for yy in range(horizon, gh, 6):
            cv.hline(0, yy, L.cols, faint)
        for xx in range(0, L.cols, 18):
            cv.vline(xx, horizon, gh - horizon, faint)
        self._stars(cv, game, L)

        if game.level.theme_key == "plains":
            self._hills(cv, game, L, y=horizon, color=th.faint)
            self._clouds(cv, game, L, th.dim)
        elif game.level.theme_key == "caverns":
            self._stalactites(cv, game, L, th.faint)
            self._cave_arcs(cv, game, L, th.faint)
        elif game.level.theme_key == "skyway":
            self._clouds(cv, game, L, th.dim, density=1.7)
            self._sky_rings(cv, game, L, th.faint)
        elif game.level.theme_key == "foundry":
            self._foundry(cv, game, L, th)
        else:
            self._void(cv, game, L, th)

    def _stars(self, cv: PixelCanvas, game: Game, L: Layout) -> None:
        th = game.level.theme
        gh = L.game_px_h
        n = max(12, L.cols // 4)
        for i in range(n):
            h = (i * 2654435761 + 1013904223) & 0xFFFFFFFF
            sx = int((h % 997) / 997 * cv.width + 3 - (game.camera_x * 0.06) % 17)
            sx %= max(1, cv.width)
            sy = int((h >> 9) % max(1, int(gh * 0.8)))
            twinkle = (math.sin(game.time * 1.7 + i * 1.13) + 1) * 0.5
            if twinkle < 0.25:
                continue
            color = th.accent if i % 19 == 0 and (game.entropy & 1) else (
                th.star if twinkle > 0.7 else th.faint)
            cv.px(sx, sy, color)
            if i % 13 == 0 and twinkle > 0.9:
                cv.px(sx + 1, sy, th.dim)
        if game.last_echo and L.cols > 60:
            for _ in range(2):
                sx = int((game.time * 37 + _ * 53) % max(1, L.cols))
                sy = int((game.time * 17 + _ * 11) % max(1, gh))
                cv.px(sx, sy, game.level.theme.accent)

    def _hills(self, cv: PixelCanvas, game: Game, L: Layout, y: int,
               color: tuple[int, int, int]) -> None:
        gh = L.game_px_h
        for layer, (par, rad, off) in enumerate(((0.25, 38, 0), (0.42, 27, 41))):
            spacing = 74
            start = int(game.camera_x * par) - spacing
            for hx in range(start - (start % spacing), start + L.cols + spacing, spacing):
                screen_x = int(hx - game.camera_x * par)
                r = int(rad * L.scale * (1 + layer * 0.25))
                base = min(gh - 2, int(gh * 0.82) + layer * 5)
                for a in range(0, 181, 7):
                    angle = math.radians(180 + a)
                    xx = int(screen_x + r * math.cos(angle))
                    yy = int(base - r * 0.7 * math.sin(angle))
                    if 0 <= xx < cv.width and 0 <= yy < gh:
                        cv.px(xx, yy, color if a % 14 else game.level.theme.dim)
            spacing += 0

    def _clouds(self, cv: PixelCanvas, game: Game, L: Layout,
                color: tuple[int, int, int], density: float = 1.0) -> None:
        spacing = int(46 / density)
        start = int(game.camera_x * 0.18) - spacing
        for i in range(start - (start % spacing), start + L.cols + spacing, spacing):
            sx = int(i - game.camera_x * 0.18)
            sy = int((i * 0.37 + 9) % max(6, L.game_px_h * 0.38)) + 4
            r = max(3, int(9 * L.scale))
            for dx, dy, rr in ((-r, 0, r), (0, -r // 2, r + 2), (r, 0, r), (r * 2, 2, r // 2)):
                self._ellipse_outline(cv, sx + dx, sy + dy, rr, max(2, rr // 2), color)
            cv.hline(sx - r, sy + max(2, r // 2), r * 3, color)

    def _ellipse_outline(self, cv: PixelCanvas, cx: int, cy: int, rx: int, ry: int,
                         color) -> None:
        steps = max(12, rx * 4)
        for i in range(steps):
            a = math.tau * i / steps
            cv.px(round(cx + rx * math.cos(a)), round(cy + ry * math.sin(a)), color)

    def _stalactites(self, cv: PixelCanvas, game: Game, L: Layout, color) -> None:
        for i in range(8):
            x = int((i * 137 - game.camera_x * 0.25) % (L.cols + 40)) - 20
            h = 10 + (i * 29) % max(8, L.game_px_h // 3)
            for k in range(h):
                w = max(0, (h - k) // 7)
                cv.hline(x - w, k, w * 2 + 1, color if k % 3 else game.level.theme.dim)
        for i in range(10):
            x = int((i * 97 + 17) % max(1, L.cols))
            y = int((i * 53) % max(1, int(L.game_px_h * 0.6)))
            if i % 3 == 0:
                cv.px(x, y, game.level.theme.accent)

    def _cave_arcs(self, cv: PixelCanvas, game: Game, L: Layout, color) -> None:
        for x in range(-40, L.cols + 80, 90):
            sx = int(x - (game.camera_x * 0.3) % 90)
            self._ellipse_outline(cv, sx, L.game_px_h, 44, 22, color)

    def _sky_rings(self, cv: PixelCanvas, game: Game, L: Layout, color) -> None:
        for i in range(4):
            cx = int((i * 211 - game.camera_x * 0.12) % (L.cols + 120)) - 60
            cy = int(L.game_px_h * (0.2 + 0.12 * (i % 3)))
            self._ellipse_outline(cv, cx, cy, 30 + i * 8, 7 + i * 2, color)

    def _foundry(self, cv: PixelCanvas, game: Game, L: Layout, th) -> None:
        gh = L.game_px_h
        for x in range(-20, L.cols + 60, 64):
            sx = int(x - (game.camera_x * 0.3) % 64)
            self._ellipse_outline(cv, sx, gh, 36, 44, th.faint)
        for x in range(0, L.cols, 29):
            sy = int(gh * 0.15)
            for yy in range(sy, gh, 5):
                cv.px(x, yy, th.faint)
        for i in range(18):
            x = int((i * 83 + game.time * 12) % max(1, L.cols))
            y = int(gh - ((game.time * 22 + i * 41) % max(10, gh * 0.5)))
            cv.px(x, y, th.hazard if i % 3 else th.accent)
        cv.hline(0, int(gh * 0.9), L.cols, th.hazard)

    def _void(self, cv: PixelCanvas, game: Game, L: Layout, th) -> None:
        gh = L.game_px_h
        cx, cy = L.cols // 2, int(gh * 0.55)
        for r in range(10, max(20, L.cols // 2), 14):
            self._ellipse_outline(cv, cx, cy, r, max(3, r // 4), th.faint)
        for i in range(14):
            a = game.time * 0.1 + i
            sx = cx + int(math.cos(a * 1.7) * (L.cols * 0.3))
            sy = cy + int(math.sin(a) * (gh * 0.22))
            cv.px(sx, sy, th.accent if i % 4 == 0 else th.faint)
        # decoherence slices from the measured entropy
        if game.last_entropy & 1:
            y = int(game.time * 40) % max(1, gh)
            cv.hline(0, y, L.cols, th.faint)
        if game.last_echo:
            y = int((game.time * 77 + L.cols) % max(1, gh))
            cv.hline(0, y, max(1, L.cols // 3), th.accent)

    # ------------------------------------------------------------------
    # tiles
    # ------------------------------------------------------------------
    def _draw_tiles(self, cv: PixelCanvas, game: Game, L: Layout) -> None:
        level = game.level
        tx0 = max(0, int(game.camera_x // TILE) - 1)
        tx1 = min(level.width, int((game.camera_x + L.view_w) // TILE) + 2)
        ty0 = max(0, int(game.camera_y // TILE) - 1)
        ty1 = min(level.height, int((game.camera_y + L.view_h) // TILE) + 2)
        th = level.theme
        for ty in range(ty0, ty1):
            for tx in range(tx0, tx1):
                ch = level.tile(tx, ty)
                if ch == ".":
                    continue
                x, y, w, h = self._tile_rect(game, L, tx, ty)
                if ch == "#":
                    self._draw_ground_tile(cv, game, L, tx, ty, x, y, w, h, th)
                elif ch == "B":
                    self._draw_brick(cv, game, tx, ty, x, y, w, h, th)
                elif ch == "?":
                    self._draw_question(cv, game, tx, ty, x, y, w, h, th)
                elif ch == "X":
                    cv.rect(x, y, w, h, th.bg)
                    cv.outline(x, y, w, h, th.faint)
                    cv.rect(x + w // 3, y + h // 2, max(1, w // 4), 1, th.faint)
                elif ch == "P":
                    self._draw_pipe(cv, game, L, tx, ty, x, y, w, h, th)
                elif ch == "=":
                    cv.hline(x, y, w, th.platform)
                    cv.hline(x, y + max(1, int(2 * L.scale)), max(1, w - 1), th.dim)
                    for xx in range(x + 1, x + w, max(3, int(5 * L.scale))):
                        cv.px(xx, y + 1, th.faint)
                elif ch == "^":
                    self._draw_spikes(cv, x, y, w, h, th)
                elif ch == "~":
                    self._draw_lava(cv, game, x, y, w, h, th)
                elif ch == "G":
                    self._draw_gate(cv, game, L, x, y, w, h, th)

    def _draw_ground_tile(self, cv, game, L, tx, ty, x, y, w, h, th) -> None:
        level = game.level
        above = level.is_solid(tx, ty - 1)
        left = level.is_solid(tx - 1, ty)
        right = level.is_solid(tx + 1, ty)
        # interior hatched stone
        cv.dither_rect(x + 1, y + 1, w - 2, h - 1, th.terrain_fill, step=3,
                       phase=tx + ty)
        if not above:
            cv.hline(x, y, w, th.terrain)
            cv.hline(x, y + 1, w, th.dim)
            n = max(2, w // 4)
            for i in range(n):
                cv.px(x + 1 + (i * 7) % max(1, w - 2), y + 2, th.faint)
        if not left:
            cv.vline(x, y + 1, h - 1, th.dim)
        if not right:
            cv.vline(x + w - 1, y + 1, h - 1, th.dim)
        if not level.is_solid(tx, ty + 1):
            cv.hline(x, y + h - 1, w, th.faint)

    def _draw_brick(self, cv, game, tx, ty, x, y, w, h, th) -> None:
        cv.rect(x, y, w, h, th.bg)
        cv.outline(x, y, w, h, th.brick)
        cv.dither_rect(x + 1, y + 1, w - 2, h - 2, th.brick_fill, step=2,
                       phase=tx + ty)
        mid = y + h // 2
        cv.hline(x + 1, mid, w - 2, th.brick_fill)
        for i in range(1, 3):
            xx = x + int(w * i / 3)
            cv.vline(xx, y + 1, max(1, mid - y), th.brick_fill)
            cv.vline(x + w - 1 - xx + x, mid + 1, y + h - mid - 2, th.brick_fill)

    def _draw_question(self, cv, game, tx, ty, x, y, w, h, th) -> None:
        pulse = (math.sin(game.time * 6 + tx * 0.7) + 1) * 0.5
        color = th.accent if pulse > 0.45 else th.ink
        cv.rect(x, y, w, h, th.bg)
        cv.outline(x, y, w, h, color)
        cv.dither_rect(x + 2, y + 2, w - 4, h - 4, th.faint, step=2, phase=tx)
        pat = ("01110", "10001", "00001", "00010", "00100", "00000", "00100")
        gw = 5
        if w >= 7 and h >= 7:
            cv.bitmap(pat, x + (w - gw) // 2, y + (h - 7) // 2, color)
        else:
            cv.px(x + w // 2, y + 2, color)
            cv.px(x + w // 2 + 1, y + 3, color)
            cv.px(x + w // 2, y + 4, color)

    def _draw_pipe(self, cv, game, L, tx, ty, x, y, w, h, th) -> None:
        above = game.level.tile(tx, ty - 1) == "P"
        cv.dither_rect(x + 1, y + 1, w - 2, h - 1, th.dim, step=2, phase=tx)
        cv.vline(x, y, h, th.platform)
        cv.vline(x + w - 1, y, h, th.platform)
        if not above:
            cv.hline(x - 1, y, w + 2, th.platform)
            cv.hline(x - 1, y + 1, w + 2, th.dim)
            cv.vline(x - 1, y, max(2, h // 2), th.platform)
            cv.vline(x + w, y, max(2, h // 2), th.platform)
        cv.hline(x + 1, y + h - 1, w - 2, th.faint)

    def _draw_spikes(self, cv, x, y, w, h, th) -> None:
        step = max(3, w // 3)
        for xx in range(x, x + w, step):
            for k in range(min(h - 1, 4)):
                cv.px(xx + k, y + h - 1 - k, th.hazard)
                cv.px(xx + step - k - 1, y + h - 1 - k, th.hazard)
            cv.hline(xx, y + h - 1, min(step, x + w - xx), th.hazard)

    def _draw_lava(self, cv, game, x, y, w, h, th) -> None:
        cv.rect(x, y, w, h, th.bg)
        cv.dither_rect(x, y + 2, w, h - 2, th.hazard, step=3, phase=int(game.time * 8))
        top = y + 2
        for xx in range(x, x + w):
            wave = int(math.sin(game.time * 4 + xx * 0.35) * 1.5)
            cv.px(xx, top + wave, th.accent if (xx // 3) % 2 else th.hazard)
            cv.px(xx, top + wave + 1, th.hazard)

    def _draw_gate(self, cv, game, L, x, y, w, h, th) -> None:
        cv.rect(x, y, w, h, th.bg)
        if game.level.gate_open:
            # Leave only two collapsed posts behind: the path to the flag
            # must read as open at a glance.
            cv.vline(x, y, h, th.faint)
            cv.vline(x + w - 1, y, h, th.faint)
            cv.hline(x, y + h - 2, w, th.faint)
            spark = (math.sin(game.time * 9) + 1) * 0.5
            if spark > 0.35:
                cv.px(x + w // 2, y + 2, th.accent)
            return
        for i in range(0, h, 3):
            cv.hline(x, y + i, w, th.hazard if i % 6 else th.accent)
        cv.vline(x, y, h, th.hazard)
        cv.vline(x + w - 1, y, h, th.hazard)
        pulse = (math.sin(game.time * 7) + 1) * 0.5
        for yy in range(y + 2, y + h, 6):
            if (yy + int(game.time * 8)) % 12 < 6:
                cv.px(x + w // 2, yy, th.accent)
        if pulse > 0.8:
            cv.outline(x - 1, y - 1, w + 2, h + 2, th.faint)

    # ------------------------------------------------------------------
    # objects
    # ------------------------------------------------------------------
    def _draw_flag_and_castle(self, cv: PixelCanvas, game: Game, L: Layout) -> None:
        level = game.level
        if not level.flag:
            return
        th = level.theme
        fx, fy = level.flag
        px = self._sx(game, L, fx * TILE + TILE / 2)
        top = self._sy(game, L, fy * TILE)
        base = self._sy(game, L, level.flag_base())
        if base < 0:
            return
        # castle at the end of the course
        ground = level.flag_base()
        cx = self._sx(game, L, (level.width - 11) * TILE)
        gy = self._sy(game, L, ground)
        self._castle(cv, int(cx), int(gy), L.scale, th)
        # pole + pennant
        for yy in range(max(0, int(top)), min(L.game_px_h, int(base)), max(1, int(2 * L.scale))):
            cv.px(int(px), yy, th.dim)
        flag_y = int(top) + max(2, int(8 * L.scale))
        fw = max(5, int(13 * L.scale))
        fh = max(3, int(7 * L.scale))
        for yy in range(fh):
            cv.hline(int(px) + 1, flag_y + yy, max(1, fw - abs(yy - fh // 2) * 2), th.accent)
        cv.circle(int(px), int(top), max(1, int(2 * L.scale)), th.ink)
        cv.hline(int(px) - 3, int(base), 7, th.dim)

    def _castle(self, cv: PixelCanvas, cx: int, gy: int, sc: float, th) -> None:
        w = max(24, int(52 * sc))
        h = max(20, int(38 * sc))
        x = cx - w // 2
        y = gy - h
        # main keep outline
        cv.outline(x, y + h // 3, w, h - h // 3, th.faint)
        cv.outline(x + w // 5, y, max(2, w // 6), h // 2 + 2, th.faint)
        cv.outline(x + w - w // 5 - max(2, w // 6), y, max(2, w // 6), h // 2 + 2, th.faint)
        for i in range(4):
            bx = x + int(w * (0.1 + i * 0.23))
            cv.rect(bx, y - max(2, int(3 * sc)), max(2, int(4 * sc)), max(2, int(4 * sc)), th.dim)
        # gate and windows
        cv.outline(x + w // 2 - max(2, w // 12), gy - max(6, h // 3),
                   max(3, w // 6), max(5, h // 3), th.dim)
        for wy in (y + h // 2, y + h // 2 + max(4, h // 6)):
            cv.px(x + w // 4, wy, th.accent)
            cv.px(x + w - w // 4, wy, th.accent)

    def _draw_checkpoints(self, cv: PixelCanvas, game: Game, L: Layout) -> None:
        th = game.level.theme
        for cp in game.level.checkpoints:
            x = self._sx(game, L, cp.x)
            y = self._sy(game, L, cp.y)
            if not (0 <= x < L.cols) or not (0 <= y < L.game_px_h + 20):
                continue
            active = game.checkpoint_active and game.checkpoint_pos is not None and abs(
                game.checkpoint_pos[0] + game.player.w / 2 - cp.x) < 2
            color = th.accent if active else th.dim
            for yy in range(int(y) - max(8, int(16 * L.scale)), int(y), max(1, int(2 * L.scale))):
                cv.px(int(x), yy, color)
            cv.hline(int(x), int(y) - max(8, int(16 * L.scale)), max(3, int(7 * L.scale)), color)
            cv.circle(int(x), int(y) - 1, max(1, int(1.5 * L.scale)), color)
            if active:
                cv.ellipse(int(x), int(y) - 2, max(4, int(10 * L.scale)),
                           max(2, int(4 * L.scale)), th.accent)

    def _draw_platforms(self, cv: PixelCanvas, game: Game, L: Layout) -> None:
        th = game.level.theme
        for plat in game.platforms:
            x = self._sx(game, L, plat.x)
            y = self._sy(game, L, plat.y)
            w = max(2, int(plat.w * L.scale))
            cv.hline(int(x), int(y), w, th.platform)
            cv.hline(int(x), int(y) + 1, w, th.dim)
            cv.dither_rect(int(x), int(y) + 2, w, max(1, int(3 * L.scale)), th.faint, 3)
            for xx in (int(x), int(x + w - 1)):
                cv.px(xx, int(y) + 2, th.accent)
                cv.px(xx, int(y) + 3, th.accent)
            if abs(plat.x - game.player.cx) < 40:
                cv.px(int(x + w / 2), int(y) - 2, th.accent)

    def _draw_coin(self, cv: PixelCanvas, game: Game, coin, L: Layout) -> None:
        th = game.level.theme
        sx = self._sx(game, L, coin.x)
        sy = self._sy(game, L, coin.y)
        if not (-20 < sx < L.cols + 20 and -20 < sy < L.game_px_h + 20):
            return
        if coin.kind == "orb":
            r = max(3, int(5 * L.scale))
            cv.circle(int(sx), int(sy), r, th.accent)
            cv.circle(int(sx), int(sy), max(1, r // 2), th.ink)
            for i in range(4):
                a = game.time * 2 + i * math.pi / 2 + game.entropy
                cv.px(int(sx + math.cos(a) * (r + 2)),
                      int(sy + math.sin(a) * (r + 2)), th.accent)
            return
        art = SPRITES[f"coin{int(coin.anim) % 4}"]
        color = th.accent if coin.kind == "entangled" else (th.ink if self.xray else PALETTE_YELLOW)
        # Draw coin as a simple bright ellipse/line set, independent of palette.
        t = int(coin.anim) % 4
        rx = (3, 2, 1, 2)[t]
        cv.ellipse(int(sx), int(sy), max(1, int(rx * L.scale)),
                   max(2, int(3.6 * L.scale)), color)
        cv.px(int(sx), int(sy), th.bg)
        if coin.kind == "entangled":
            cv.ellipse(int(sx), int(sy), max(2, int(5.5 * L.scale)),
                       max(3, int(4.7 * L.scale)), th.accent)
            cv.px(int(sx), int(sy) - int(6 * L.scale), th.accent)

    def _draw_mushroom(self, cv, game, m, L: Layout) -> None:
        sx = self._sx(game, L, m.x)
        sy = self._sy(game, L, m.y)
        art = SPRITES["mushroom"]
        scale = max(0.5, L.scale)
        cv.sprite(art, int(sx), int(sy), scale, game.level.theme.sprite_palette(self.xray))

    def _sprite_scale(self, art: tuple[str,...], w: float, L: Layout) -> float:
        return L.scale

    def _draw_enemy(self, cv: PixelCanvas, game: Game, e: Enemy, L: Layout) -> None:
        th = game.level.theme
        sx = self._sx(game, L, e.x)
        sy = self._sy(game, L, e.y)
        if sx < -60 or sx > L.cols + 60:
            return
        if e.kind == "goomba":
            art = SPRITES["goomba_flat"] if e.squash > 0 else SPRITES["goomba"]
            self._sprite_at_bottom(cv, game, L, art, sx, e, 1.0)
            if e.mood:
                c = th.accent if e.mood == 2 else th.dim
                cv.px(int(sx + e.w / 2), int(sy - 3), c)
        elif e.kind == "koopa":
            art = SPRITES["koopa"]
            self._sprite_at_bottom(cv, game, L, art, sx, e, 1.0)
            if e.mood == 2:
                cv.px(int(sx + e.w / 2), int(sy - 3), th.accent)
        elif e.kind == "flyer":
            art = SPRITES["flyer"]
            palette = dict(th.sprite_palette(self.xray))
            palette.update({"A": th.accent, "V": th.hazard})
            self._sprite_at_bottom(cv, game, L, art, sx, e, 1.0, palette=palette)
        elif e.kind == "boss":
            if e.invuln > 0 and int(game.time * 18) % 2:
                return
            palette = dict(th.sprite_palette(self.xray))
            if not self.xray:
                palette.update({"G": th.terrain, "Y": th.accent, "W": th.ink,
                                "N": th.dim, "R": th.hazard})
            art = BOSS
            scale = max(1.0, (e.w / len(art[0])) * 1.0)
            cv.sprite(art, int(sx - 2), int(self._sy(game, L, e.bottom)) - int(len(art) * scale),
                      scale, palette, flip=e.dir < 0)

    def _sprite_at_bottom(self, cv, game, L, art, sx, e, scale_mult,
                          palette=None) -> None:
        th = game.level.theme
        eff_scale = L.scale * scale_mult
        pal = palette if palette is not None else th.sprite_palette(self.xray)
        bottom = self._sy(game, L, e.bottom)
        h = len(art) * eff_scale
        w = len(art[0]) * eff_scale
        cv.sprite(art, int(sx + e.w / 2 - w / 2), int(bottom - h),
                  eff_scale, pal, flip=e.dir < 0)

    def _draw_fireball(self, cv, game, f, L: Layout) -> None:
        th = game.level.theme
        sx = self._sx(game, L, f.x)
        sy = self._sy(game, L, f.y)
        r = max(2, int(f.radius * L.scale))
        cv.circle(int(sx), int(sy), r, th.hazard)
        cv.circle(int(sx), int(sy), max(1, r // 2), th.accent)
        for i in range(3):
            a = game.time * 9 + i * 2.1
            cv.px(int(sx + math.cos(a) * (r + 2)), int(sy + math.sin(a) * (r + 2)),
                  th.hazard)

    def _draw_particle(self, cv: PixelCanvas, game: Game, particle, L: Layout) -> None:
        sx = self._sx(game, L, particle.x)
        sy = self._sy(game, L, particle.y)
        if not (0 <= sx < L.cols and 0 <= sy < L.game_px_h):
            return
        if particle.life < 0.08:
            return
        size = max(1, int(particle.size * L.scale))
        cv.rect(int(sx), int(sy), size, size, particle.color)

    def _draw_beams(self, cv: PixelCanvas, game: Game, L: Layout) -> None:
        for beam in game.beams:
            x0, y0 = self._sx(game, L, beam.x0), self._sy(game, L, beam.y0)
            x1, y1 = self._sx(game, L, beam.x1), self._sy(game, L, beam.y1)
            steps = max(2, int(max(abs(x1 - x0), abs(y1 - y0))))
            for i in range(0, steps, 3):
                t = i / steps
                cv.px(int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t),
                      game.level.theme.accent)

    def _draw_player(self, cv: PixelCanvas, game: Game, L: Layout) -> None:
        p = game.player
        th = game.level.theme
        sx = self._sx(game, L, p.x)
        sy = self._sy(game, L, p.y)
        if p.invuln > 0 and p.dead is False and int(game.time * 18) % 2:
            pass
        # afterimages / quantum trail
        if p.dash_time > 0 or p.invuln > 0:
            self.trail.append((p.cx, p.bottom, p.face, p.big, 0.35))
        self.trail = [(x, y, f, b, life - 0.035) for x, y, f, b, life in self.trail if life > 0]
        for tx, ty, tf, tb, life in self.trail[:8]:
            art = SPRITES["mario_big_idle" if tb else "mario_idle"]
            wsx = self._sx(game, L, tx)
            wsy = self._sy(game, L, ty)
            h = len(art) * L.scale
            w = len(art[0]) * L.scale
            cv.sprite(art, int(wsx - w / 2), int(wsy - h), L.scale,
                      {ch: th.faint for ch in set("".join(art)) if ch != "."},
                      flip=tf < 0)
        if p.dead:
            art = SPRITES["mario_big_jump" if p.big else "mario_jump"]
        else:
            if not p.on_ground:
                art = SPRITES["mario_big_jump" if p.big else "mario_jump"]
            elif abs(p.vx) > 10:
                run = int(p.anim) % 2
                art = SPRITES[f"mario_{'big_' if p.big else ''}run{run + 1}"]
            else:
                art = SPRITES["mario_big_idle" if p.big else "mario_idle"]
        scale = L.scale
        w = len(art[0]) * scale
        h = len(art) * scale
        draw_x = int(sx + p.w / 2 - w / 2)
        draw_y = int(self._sy(game, L, p.bottom) - h)
        if p.invuln > 0 and int(game.time * 20) % 2:
            return
        cv.sprite(art, draw_x, draw_y, scale, th.sprite_palette(self.xray), flip=p.face < 0)
        # quantum aura / flux indicator
        if p.qflux > 0:
            q = min(3, 1 + p.qflux // 34)
            for i in range(q):
                a = game.time * 3.2 + i * math.tau / q
                ax = p.cx + math.cos(a) * (7 + 2 * math.sin(game.time * 2 + i))
                ay = p.y + p.h / 2 + math.sin(a) * 5
                cv.px(int(self._sx(game, L, ax)), int(self._sy(game, L, ay)), th.accent)
        if p.dash_time > 0:
            cv.ellipse(int(sx + p.w / 2), int(sy + p.h / 2),
                       max(4, int(13 * scale)), max(2, int(6 * scale)), th.accent)

    def _draw_popup(self, cv, game, popup, L: Layout) -> None:
        sx = self._sx(game, L, popup.x)
        sy = self._sy(game, L, popup.y)
        scale = max(1, int(L.scale))
        w = text_width(popup.text, FONT_3x5, scale, 0)
        draw_font(cv, int(sx - w / 2), int(sy), popup.text, popup.color,
                  font=FONT_3x5, scale=scale, spacing=0)

    def _draw_boss_hp(self, cv, game, L: Layout) -> None:
        if not game.boss or not game.boss.active or game.boss.hp <= 0:
            return
        th = game.level.theme
        x = L.cols // 2 - 18
        y = max(4, int(L.game_px_h * 0.09))
        for i in range(3):
            color = th.hazard if i < game.boss.hp else th.faint
            cv.rect(x + i * 13, y, 10, 3, color)
            cv.outline(x + i * 13 - 1, y - 1, 12, 5, th.dim)
        draw_font(cv, L.cols // 2, y - 10, "BOSS", th.dim, scale=1, spacing=0,
                  align="center")
        for i in range(game.boss.hp):
            cv.px(x + i * 13, y, th.accent)

    # ------------------------------------------------------------------
    # HUD
    # ------------------------------------------------------------------
    def _stat_values(self, game: Game) -> list[tuple[str, str, tuple[int,int,int]]]:
        run = game.run
        th = game.level.theme
        time_val = run.run_time if run.speedrun else game.level_time
        stats = [
            ("SCORE", f"{max(0, run.score):06d}", th.hud_fg),
            ("COINS", f"{run.coins:02d}", th.hud_fg),
            ("DEATHS" if run.speedrun else "LIVES",
             f"{run.deaths:02d}" if run.speedrun else str(max(0, run.lives)),
             th.hazard if not run.speedrun and run.lives <= 1 else th.hud_fg),
            ("WORLD", game.level.key, th.hud_fg),
            ("TIME", format_short_time(time_val),
             th.accent if run.speedrun else th.hud_fg),
        ]
        return stats

    def _draw_big_hud(self, cv: PixelCanvas, game: Game, L: Layout) -> None:
        th = game.level.theme
        top = L.game_px_h
        cv.rect(0, top, L.cols, L.hud_rows * 2, th.hud_bg)
        cv.hline(0, top + 1, L.cols, th.faint)
        stats = self._stat_values(game)
        weights = (0.27, 0.11, 0.13, 0.14, 0.35)
        x = 0
        self.hud_columns = []
        for i, (label, value, color) in enumerate(stats):
            wcol = int(L.cols * weights[i]) if i < 4 else L.cols - x
            x0, x1 = x, x + wcol
            self.hud_columns.append((x0, x1, label, value, color))
            # values live in the pixel canvas for crisp Quandoom-style type
            vw = text_width(value, FONT_5x7, 1, 1)
            if vw > wcol - 2:
                vw = text_width(value, FONT_5x7, 1, 0)
                draw_font(cv, x0 + max(0, (wcol - vw) // 2), top + 2, value, color,
                          font=FONT_5x7, scale=1, spacing=0)
            else:
                draw_font(cv, x0 + (wcol - vw) // 2, top + 2, value, color,
                          font=FONT_5x7, scale=1, spacing=1)
            if i:
                cv.vline(x0, top + 2, 8, th.faint)
            x += wcol
        # flat quantum graph along the bottom of the values area
        q = game.qresult
        gates = q.gate_count if q else 0
        depth = q.depth if q else 0
        flux = max(0, min(5, int(math.ceil(game.player.qflux / 20))))
        coll = q.frame if q else 0
        high = max(self.high_score, game.run.score)
        line = (f"QPU 14Q  G{gates:03d}  D{depth:02d}  ENT {game.entropy:02d}  "
                f"FLUX [{'#' * flux}{'.' * (5 - flux)}]  FRM {coll:05d}  "
                f"HI {high:06d}")
        if game.boss and game.boss.active and game.boss.hp > 0:
            line += f"  BOSS {game.boss.hp}/3"
        maxw = L.cols - 4
        if len(line) > maxw:
            line = line[:maxw]
        self.hud_quantum = line

    def _draw_compact_hud(self, cv: PixelCanvas, game: Game, L: Layout) -> None:
        th = game.level.theme
        top = L.game_px_h
        cv.rect(0, top, L.cols, L.hud_rows * 2, th.hud_bg)
        cv.hline(0, top + 1, L.cols, th.faint)
        run = game.run
        time_val = run.run_time if run.speedrun else game.level_time
        if L.cols >= 70:
            if run.speedrun:
                line = (f"TIME {format_short_time(time_val)}  SCORE {max(0, run.score):06d}  "
                        f"COINS {run.coins:02d}  DEATHS {run.deaths:02d}  {game.level.key}")
            else:
                line = (f"SCORE {max(0, run.score):06d}  COINS {run.coins:02d}  "
                        f"LIVES {max(0, run.lives)}  WORLD {game.level.key}  "
                        f"TIME {format_short_time(time_val)}")
        else:
            line = (f"S{max(0, run.score):06d} C{run.coins:02d} "
                    f"{'D' if run.speedrun else 'x'}"
                    f"{run.deaths if run.speedrun else max(0, run.lives)} "
                    f"{game.level.key} {format_short_time(time_val)}")
        q = game.qresult
        flux = max(0, min(5, int(math.ceil(game.player.qflux / 20))))
        high = max(self.high_score, game.run.score)
        qline = (f"QPU 14Q G{(q.gate_count if q else 0):03d} D{(q.depth if q else 0):02d} "
                 f"FLUX[{'#' * flux}{'.' * (5 - flux)}] HI {high:06d}")
        if L.hud_rows >= 3:
            self.hud_compact = (line, qline)
        else:
            self.hud_compact = (line, "")

    def _hud_text(self, cells: CellCanvas, game: Game, L: Layout) -> None:
        th = game.level.theme
        hy = L.game_cell_rows
        # top rule
        if L.big_hud:
            cells.hline(0, hy, L.cols, "═", th.hud_dim, th.hud_bg)
            for x0, *_ in getattr(self, "hud_columns", []):
                if 0 < x0 < L.cols:
                    cells.put(x0, hy, "╪", th.hud_dim, th.hud_bg)
            for x0, x1, label, value, color in getattr(self, "hud_columns", []):
                cx = (x0 + x1) // 2
                cells.text(cx - len(label) // 2, hy + 5, label, th.hud_dim, th.hud_bg)
            line = getattr(self, "hud_quantum", "")
            cells.text(2, hy + 6, line, th.hud_dim, th.hud_bg)
            # accent some tokens in the telemetry strip
            idx = line.find("G")
            if idx > 0:
                cells.text(2 + idx, hy + 6, "G" + line[idx + 1:idx + 4], th.accent, th.hud_bg)
            idx = line.find("FLUX")
            if idx > 0:
                cells.text(2 + idx, hy + 6, line[idx:idx + 11], th.accent, th.hud_bg)
            if "BOSS" in line:
                idx = line.find("BOSS")
                cells.text(2 + idx, hy + 6, line[idx:], th.hazard, th.hud_bg)
        else:
            cells.hline(0, hy, L.cols, "═", th.hud_dim, th.hud_bg)
            line, qline = getattr(self, "hud_compact", ("", ""))
            y = hy + 1
            # split into labelled tokens and tint numbers
            cx = 2 if L.cols >= 60 else 0
            for token in line.split("  "):
                if not token:
                    continue
                color = th.accent if token.split(" ")[0] in ("TIME",) else th.hud_fg
                if token.split(" ")[0] in ("SCORE", "COINS", "LIVES", "DEATHS",
                                           "WORLD", "S", "C", "D", "x"):
                    color = th.hud_fg
                cells.text(cx, y, token, color, th.hud_bg)
                cx += len(token) + 2
                if cx > L.cols - 4:
                    break
            if qline and L.hud_rows >= 3:
                cells.text(2, hy + 2, qline, th.hud_dim, th.hud_bg)


# Yellow used only as a semantic hook; the x-ray renderer overrides most
# physical colours, while the classic palette makes coins obviously golden.
PALETTE_YELLOW = (255, 213, 74)
