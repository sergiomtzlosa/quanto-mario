"""Platforming simulation.  All world units are virtual pixels (8 px tiles)."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Iterable

from .entities import (
    Beam, Coin, Controls, Enemy, Fireball, MovingPlatform, Mushroom, Particle,
    Player, Popup, Run,
)
from .levels import TILE, EnemySpec, Level, level_defs
from .quantum import QuantumOracle, QuantumResult

_LEVELS = None


def levels():
    global _LEVELS
    if _LEVELS is None:
        _LEVELS = level_defs()
    return _LEVELS


GRAVITY = 980.0
MAX_WALK = 76.0
MAX_RUN = 118.0
JUMP_V = 255.0
DASH_COST = 40
DASH_TIME = 0.22
DASH_SPEED = 250.0


def approach(value: float, target: float, amount: float) -> float:
    if value < target:
        return min(value + amount, target)
    return max(value - amount, target)


def overlap(ax, ay, aw, ah, bx, by, bw, bh) -> bool:
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


@dataclass
class LevelStats:
    level_time: float = 0.0
    coins: int = 0
    collapses: int = 0


class Game:
    def __init__(self, run: Run, level_index: int, *, seed: int | None = None,
                 checkpoint: tuple[float, float] | None = None,
                 view_w: float = 160.0, view_h: float = 80.0) -> None:
        self.run = run
        self.level_index = level_index
        run.level_score_start = run.score
        run.level_coins_start = run.coins
        self.defs = levels()
        self.level = Level(self.defs[level_index])
        self.oracle = QuantumOracle(seed=run.seed if seed is None else seed)
        self.qresult: QuantumResult | None = None
        self.quantum_timer = 0.0
        self.last_entropy = 0
        self.last_reward = 0
        self.last_echo = 0
        self.time = 0.0
        self.level_time = 0.0
        self.view_w = view_w
        self.view_h = view_h
        self.camera_x = 0.0
        self.camera_y = 0.0
        self.shake = 0.0
        self.shake_mag = 0.0
        self.sprint = False
        self.goal = 0.0
        self.clearing = False
        self.clear_timer = 0.0
        self.finished = False
        self.events: list[str] = []
        self.checkpoint_pos = checkpoint
        self.checkpoint_active = checkpoint is not None
        self.sound_flash = 0.0
        self.boss_defeated = False
        self.block_bumps: dict[tuple[int, int], float] = {}
        self.beams: list[Beam] = []
        self.particles: list[Particle] = []
        self.popups: list[Popup] = []
        self.coins: list[Coin] = []
        self.enemies: list[Enemy] = []
        self.mushrooms: list[Mushroom] = []
        self.fireballs: list[Fireball] = []
        self.platforms: list[MovingPlatform] = []
        self.player = Player()
        self.boss: Enemy | None = None
        self._spawn_entities()
        self._spawn_player(checkpoint)
        if seed is not None:
            self.rng = random.Random(seed)
        else:
            self.rng = random.Random()
        # Warm the QPU immediately so HUD/lab have something to show.
        self._quantum_tick()
        self._snap_camera()

    # ------------------------------------------------------------------
    # setup / reset
    # ------------------------------------------------------------------
    def _spawn_entities(self) -> None:
        self.coins = [Coin(c.x, c.y, c.kind, pair=c.pair, ident=c.ident)
                      for c in self.level.coin_specs]
        self.enemies = []
        for i, spec in enumerate(self.level.enemy_specs):
            e = Enemy(spec.kind, spec.x, spec.y, spec.w, spec.h, dir=-1, index=i)
            e.base_x, e.base_y = e.x, e.y
            self.enemies.append(e)
        if self.level.boss_spec:
            spec = self.level.boss_spec
            boss = Enemy("boss", spec.x, 11 * TILE - 42, 34, 42,
                         dir=-1, index=len(self.enemies), hp=3)
            boss.active = False
            boss.base_x, boss.base_y = boss.x, boss.y
            self.boss = boss
            self.enemies.append(boss)
        self.platforms = [MovingPlatform.from_spec(s, i)
                          for i, s in enumerate(self.level.defn.moving)]
        self.mushrooms = []
        self.fireballs = []
        self.particles = []
        self.popups = []
        self.beams = []

    def _spawn_player(self, checkpoint: tuple[float, float] | None = None) -> None:
        p = self.player
        p.big = False
        p.w, p.h = 6, 10
        if checkpoint:
            p.x, p.y = checkpoint
        else:
            p.x, p.y = self.level.spawn_x, self.level.spawn_y
        p.vx = p.vy = 0.0
        p.on_ground = False
        p.invuln = 0.8
        p.dead = False
        p.dead_timer = 0.0
        p.qflux = 100
        p.jump_buffer = 0.0
        p.coyote = 0.0
        p.dash_time = 0.0
        p.dash_cool = 0.0
        p.riding = None
        p.combo = 0
        p.slide = 0.0

    def restart_level(self, *, use_checkpoint: bool = True) -> None:
        keep_time = self.level_time
        # A retry starts the level over, so pickups and points collected since
        # the level began are rolled back.  Without this, dying on a coin-rich
        # checkpoint would be an infinite score/life farm.
        self.run.score = self.run.level_score_start
        self.run.coins = self.run.level_coins_start
        self.level = Level(self.defs[self.level_index])
        self.level.reset()
        self._spawn_entities()
        cp = self.checkpoint_pos if use_checkpoint and self.checkpoint_active else None
        self._spawn_player(cp)
        self.level_time = keep_time
        self.clearing = False
        self.clear_timer = 0.0
        self.finished = False
        self.particles = []
        self.beams = []
        self.fireballs = []
        self.block_bumps.clear()
        self._snap_camera()

    def _snap_camera(self) -> None:
        p = self.player
        self.camera_x = p.cx - self.view_w * 0.42
        self.camera_y = p.bottom - self.view_h * 0.72
        self._clamp_camera(instant=True)

    def set_view(self, width_px: float, height_px: float) -> None:
        self.view_w = max(64.0, width_px)
        self.view_h = max(48.0, height_px)
        self._clamp_camera(instant=True)

    def _clamp_camera(self, instant: bool = False) -> None:
        max_x = max(0.0, self.level.width * TILE - self.view_w)
        max_y = max(0.0, self.level.height * TILE - self.view_h)
        tx = min(max(0.0, self.player.cx - self.view_w * 0.42), max_x)
        ty = min(max(0.0, self.player.bottom - self.view_h * 0.72), max_y)
        if instant:
            self.camera_x, self.camera_y = tx, ty
        else:
            a = 0.12
            self.camera_x += (tx - self.camera_x) * a
            self.camera_y += (ty - self.camera_y) * a

    # ------------------------------------------------------------------
    # quantum bridge
    # ------------------------------------------------------------------
    def _quantum_tick(self, controls: Controls | None = None) -> None:
        p = self.player
        ctr = controls or Controls()
        self.qresult = self.oracle.tick(
            left=ctr.left, right=ctr.right,
            jump=ctr.jump_held or ctr.jump_pressed,
            sprint=self.sprint, dash=p.dash_time > 0 or ctr.dash_pressed,
            speed=abs(p.vx), qflux=p.qflux, level=self.level_index,
        )
        self.last_entropy = self.qresult.entropy
        self.last_reward = self.qresult.reward
        self.last_echo = self.qresult.echo
        for e in self.enemies:
            e.mood = (self.qresult.entropy >> (e.index % 4)) & 3
            e.mood_t = 0.24 + 0.14 * ((self.qresult.entropy >> ((e.index + 1) % 4)) & 3)

    @property
    def entropy(self) -> int:
        return self.last_entropy

    # ------------------------------------------------------------------
    # main update
    # ------------------------------------------------------------------
    def step(self, dt: float, c: Controls) -> list[str]:
        dt = min(dt, 1 / 30)
        self.events = []
        if self.finished:
            self._update_effects(dt)
            self._clamp_camera()
            return self.events
        self.time += dt
        if not self.clearing:
            self.level_time += dt
            if self.run.speedrun and self.run.started:
                self.run.run_time += dt
        self.run.started = True
        self.shake = max(0.0, self.shake - dt)
        self.sound_flash = max(0.0, self.sound_flash - dt)
        if c.sprint_pressed:
            self.sprint = not self.sprint
            c.sprint_pressed = False

        # One real state-vector circuit per simulation frame.  Fourteen
        # qubits cost roughly 1-2 ms, so this remains comfortably real-time.
        self.quantum_timer += dt
        self._quantum_tick(c)
        self.quantum_timer = 0.0

        # platforms first, carry a passenger
        for i, plat in enumerate(self.platforms):
            plat.update(dt)
            if self.player.riding == i and not self.player.dead:
                self.player.x += plat.x - plat.px
                self.player.y += plat.y - plat.py

        if self.clearing:
            self._update_clearing(dt)
            self._update_effects(dt)
            self._clamp_camera()
            return self.events
        if self.player.dead:
            self._update_dead(dt)
            self._update_enemies(dt)
            self._update_effects(dt)
            self._update_camera(dt)
            return self.events

        self._update_player(dt, c)
        self._update_enemies(dt)
        self._update_items(dt)
        self._update_blocks(dt)
        self._player_collisions(dt)
        self._check_checkpoints()
        self._check_goal()
        self._update_effects(dt)
        self._update_camera(dt)
        return self.events

    # ------------------------------------------------------------------
    # player physics
    # ------------------------------------------------------------------
    def _update_player(self, dt: float, c: Controls) -> None:
        p = self.player
        p.invuln = max(0.0, p.invuln - dt)
        p.dash_cool = max(0.0, p.dash_cool - dt)
        p.drop_through = max(0.0, p.drop_through - dt)
        p.jump_buffer = max(0.0, p.jump_buffer - dt)
        p.anim += dt * (abs(p.vx) / 20 + 1)
        if p.squash > 0:
            p.squash = max(0.0, p.squash - dt * 5)

        if c.jump_pressed:
            p.jump_buffer = 0.12
            c.jump_pressed = False
        if c.dash_pressed:
            c.dash_pressed = False
            if p.qflux >= DASH_COST and p.dash_cool <= 0:
                p.qflux -= DASH_COST
                p.dash_time = DASH_TIME
                p.dash_cool = 0.35
                p.face = c.direction or p.face
                p.invuln = max(p.invuln, DASH_TIME + 0.1)
                self.shake = max(self.shake, 0.12)
                self.shake_mag = 2.0
                self._burst(p.cx, p.y + p.h / 2, self.level.theme.accent, 12)
                self._popup(p.x, p.y - 10, "COLLAPSE!", self.level.theme.accent)

        if p.dash_time > 0:
            p.dash_time -= dt
            p.vx = DASH_SPEED * (1 if p.face > 0 else -1)
            p.vy = 0
            self._move_x(p.vx * dt)
            self._move_y(0.0, p.bottom)
            if self.time % 0.04 < dt:
                self._burst(p.cx, p.y + p.h / 2, self.level.theme.accent, 1, speed=12)
            if p.dash_time <= 0:
                p.vx *= 0.45
            return

        direction = c.direction
        if direction:
            p.face = direction
        max_speed = MAX_RUN if self.sprint else MAX_WALK
        if p.on_ground:
            if direction:
                p.vx = approach(p.vx, direction * max_speed, 760 * dt)
            else:
                p.vx = approach(p.vx, 0, 980 * dt)
        else:
            if direction:
                p.vx = approach(p.vx, direction * max_speed, 460 * dt)

        p.vy += GRAVITY * dt * (1.6 if c.down and not p.on_ground else 1.0)
        p.vy = min(p.vy, 420)
        if p.jump_buffer > 0 and (p.on_ground or p.coyote > 0):
            p.vy = -JUMP_V
            p.on_ground = False
            p.coyote = 0.0
            p.jump_buffer = 0.0
            self._burst(p.cx, p.bottom, self.level.theme.ink, 5, speed=28)
        if c.down and p.on_ground:
            # Drop through one-way platforms.
            tx = int(p.cx // TILE)
            ty = int((p.bottom + 1) // TILE)
            if self.level.is_oneway(tx, ty):
                p.drop_through = 0.18
                p.y += 1.5

        prev_bottom = p.bottom
        was_grounded = p.on_ground
        p.on_ground = False
        p.riding = None
        self._move_x(p.vx * dt)
        self._move_y(p.vy * dt, prev_bottom)

        if p.on_ground:
            p.coyote = 0.09
            if not was_grounded:
                p.combo = 0
                self._burst(p.cx, p.bottom, self.level.theme.dim, 3, speed=18)
                p.squash = 0.35
        else:
            p.coyote = max(0.0, p.coyote - dt)

        # pits
        if p.y > self.level.height * TILE + 36:
            self._kill_player(fell=True)
            return
        # hazards
        if p.invuln <= 0 and self._touch_hazard(p.x + 1, p.y + 1, p.w - 2, p.h - 2):
            self._hurt_player()

    def _move_x(self, dx: float) -> None:
        p = self.player
        if not dx:
            return
        p.x += dx
        ty0 = int((p.y + 1) // TILE)
        ty1 = int((p.bottom - 1) // TILE)
        if dx > 0:
            tx = int((p.right - 0.01) // TILE)
            for ty in range(ty0, ty1 + 1):
                if self.level.is_solid(tx, ty):
                    p.x = tx * TILE - p.w - 0.01
                    p.vx = 0
                    p.dash_time = 0
                    return
        else:
            tx = int(p.x // TILE)
            for ty in range(ty0, ty1 + 1):
                if self.level.is_solid(tx, ty):
                    p.x = (tx + 1) * TILE + 0.01
                    p.vx = 0
                    p.dash_time = 0
                    return

    def _move_y(self, dy: float, prev_bottom: float) -> None:
        p = self.player
        if not dy:
            # still check standing on a moving platform
            self._land_on_platform(prev_bottom, 0.0)
            return
        p.y += dy
        tx0 = int((p.x + 1) // TILE)
        tx1 = int((p.right - 1) // TILE)
        if dy > 0:
            ty = int((p.bottom - 0.01) // TILE)
            landed = False
            for tx in range(tx0, tx1 + 1):
                if self.level.is_solid(tx, ty):
                    p.y = ty * TILE - p.h - 0.01
                    p.vy = 0
                    p.on_ground = True
                    landed = True
                    break
                if (p.drop_through <= 0 and self.level.is_oneway(tx, ty)
                        and prev_bottom <= ty * TILE + 0.6):
                    p.y = ty * TILE - p.h
                    p.vy = 0
                    p.on_ground = True
                    landed = True
                    break
            if not landed:
                self._land_on_platform(prev_bottom, p.bottom)
        else:
            ty = int(p.y // TILE)
            hit: tuple[int, int] | None = None
            for tx in range(tx0, tx1 + 1):
                if self.level.is_solid(tx, ty):
                    p.y = (ty + 1) * TILE
                    p.vy = 0
                    ch = self.level.tile(tx, ty)
                    if ch in "?B" and hit is None:
                        hit = (tx, ty)
                    break
            if hit:
                self.hit_block(*hit)

    def _land_on_platform(self, prev_bottom: float, new_bottom: float) -> None:
        p = self.player
        for i, plat in enumerate(self.platforms):
            if p.right <= plat.x + 1 or p.x >= plat.x + plat.w - 1:
                continue
            if prev_bottom <= plat.y + 1.0 <= new_bottom + 0.1:
                p.y = plat.y - p.h
                p.vy = 0
                p.on_ground = True
                p.riding = i
                return

    def _touch_hazard(self, x: float, y: float, w: float, h: float) -> bool:
        tx0, tx1 = int(x // TILE), int((x + w) // TILE)
        ty0, ty1 = int(y // TILE), int((y + h) // TILE)
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                if self.level.is_hazard(tx, ty):
                    return True
        return False

    # ------------------------------------------------------------------
    # enemies and hazards
    # ------------------------------------------------------------------
    def _update_enemies(self, dt: float) -> None:
        p = self.player
        for e in self.enemies:
            if not e.alive:
                continue
            e.anim += dt
            e.mood_t = max(0.0, e.mood_t - dt)
            if e.invuln > 0:
                e.invuln = max(0.0, e.invuln - dt)
            distance = abs(e.cx - p.cx)
            if not e.active:
                if distance < 22 * TILE or e.kind == "flyer":
                    e.active = True
                else:
                    continue
            if e.squash > 0:
                e.squash -= dt
                if e.squash <= 0:
                    e.alive = False
                continue
            if e.kind == "boss":
                self._update_boss(e, dt)
                continue
            if e.kind == "flyer":
                e.x = e.base_x + math.sin(e.anim * 1.2 + e.index) * 30
                e.y = e.base_y + math.sin(e.anim * 3.1 + e.index) * 11
                if e.mood == 1:
                    e.x += e.dir * 8 * dt
                continue
            speed = 22.0 if e.kind == "goomba" else 18.0
            if e.mood == 1:
                speed *= 0.28
            elif e.mood == 2:
                speed *= 1.35
            e.vx = e.dir * speed
            e.vy += GRAVITY * dt
            e.vy = min(e.vy, 300)
            # horizontal
            e.x += e.vx * dt
            ty0 = int((e.y + 1) // TILE)
            ty1 = int((e.bottom - 1) // TILE)
            if e.vx > 0:
                tx = int((e.right - 0.01) // TILE)
                for ty in range(ty0, ty1 + 1):
                    if self.level.is_solid(tx, ty):
                        e.x = tx * TILE - e.w - 0.01
                        e.dir = -1
                        break
            elif e.vx < 0:
                tx = int(e.x // TILE)
                for ty in range(ty0, ty1 + 1):
                    if self.level.is_solid(tx, ty):
                        e.x = (tx + 1) * TILE + 0.01
                        e.dir = 1
                        break
            # vertical
            e.y += e.vy * dt
            if e.vy >= 0:
                ty = int((e.bottom - 0.01) // TILE)
                for tx in range(int(e.x // TILE), int(e.right // TILE) + 1):
                    solid = self.level.is_solid(tx, ty)
                    oneway = self.level.is_oneway(tx, ty)
                    if solid or oneway:
                        e.y = ty * TILE - e.h
                        e.vy = 0
                        e.on_ground = True
                        break
                else:
                    e.on_ground = False
                # stay on ledges
                if e.on_ground:
                    look = int(((e.right + 1) if e.dir > 0 else (e.x - 1)) // TILE)
                    foot = int((e.bottom + 2) // TILE)
                    if not (self.level.is_solid(look, foot) or self.level.is_oneway(look, foot)):
                        e.dir *= -1
            else:
                e.on_ground = False
            if e.y > self.level.height * TILE + 40:
                e.alive = False

        # fireballs
        for f in self.fireballs:
            if not f.alive:
                continue
            f.life -= dt
            f.anim += dt
            f.x += f.vx * dt
            f.y += f.vy * dt
            if f.life <= 0:
                f.alive = False
                continue
            tx, ty = int(f.x // TILE), int(f.y // TILE)
            if self.level.is_solid(tx, ty):
                f.alive = False
                self._burst(f.x, f.y, self.level.theme.hazard, 4)
                continue
            if overlap(f.x - f.radius, f.y - f.radius, f.radius * 2, f.radius * 2,
                       p.x, p.y, p.w, p.h):
                if p.invuln <= 0 and p.dash_time <= 0:
                    self._hurt_player()
                f.alive = False

    def _update_boss(self, e: Enemy, dt: float) -> None:
        p = self.player
        if not e.active:
            e.active = True
        e.fire_cd -= dt
        e.jump_cd -= dt
        e.vy += GRAVITY * dt
        e.vy = min(e.vy, 350)
        desired = 1 if p.cx > e.cx else -1
        e.dir = desired
        e.vx = desired * (38 if e.mood != 1 else 12)
        e.x += e.vx * dt
        # arena bounds, keep the boss off the checkpoint side
        lo = 100 * TILE
        hi = 124 * TILE
        e.x = min(max(e.x, lo), hi)
        e.y += e.vy * dt
        tx0 = int((e.x + 2) // TILE)
        tx1 = int((e.right - 2) // TILE)
        grounded = False
        for tx in range(tx0, tx1 + 1):
            ty = int((e.bottom - 0.01) // TILE)
            if self.level.is_solid(tx, ty):
                e.y = ty * TILE - e.h
                e.vy = 0
                grounded = True
                break
        e.on_ground = grounded
        if grounded and e.jump_cd <= 0:
            e.jump_cd = 2.0 + (self.entropy & 3) * 0.12
            e.vy = -240
            e.vx = desired * 65
        if e.fire_cd <= 0 and e.hp > 0:
            e.fire_cd = 1.35 + (self.entropy & 1) * 0.35
            self.fireballs.append(Fireball(e.cx, e.y + 10, desired * 95, 0))
            self._burst(e.cx, e.y + 10, self.level.theme.hazard, 6)
        if e.y > self.level.height * TILE + 50:
            e.y = 10 * TILE - e.h
            e.vy = 0

    def _player_collisions(self, dt: float) -> None:
        p = self.player
        if p.dead:
            return
        for e in self.enemies:
            if not e.alive or e.squash > 0:
                continue
            if not e.active and e.kind != "boss":
                continue
            if not overlap(p.x, p.y, p.w, p.h, e.x, e.y, e.w, e.h):
                continue
            if p.dash_time > 0:
                self._damage_enemy(e, dash=True)
                continue
            if p.invuln > 0:
                continue
            # Only a genuine downward landing counts as a stomp.  The old
            # approximation let a falling player barge through enemies from
            # the side, which made tight corridor sections unpredictable.
            stomp = (p.vy > 0
                     and p.bottom - p.vy * dt * 1.6 <= e.y + 5
                     and p.y < e.y + e.h * 0.45)
            if stomp:
                self._stomp(e)
                continue
            if e.kind == "boss" and e.invuln > 0:
                continue
            self._hurt_player(e)

    def _stomp(self, e: Enemy) -> None:
        p = self.player
        p.vy = -185
        p.squash = 1.0
        self.shake = max(self.shake, 0.08)
        self.shake_mag = 1.5
        if e.kind == "boss":
            if e.invuln > 0:
                return
            e.hp -= 1
            e.invuln = 0.9
            if e.hp <= 0:
                e.alive = False
                self.boss_defeated = True
                self.level.open_gate()
                self.run.add_score(5000)
                self._popup(e.cx, e.y, "+5000", self.level.theme.accent)
                self._burst(e.cx, e.y + e.h / 2, self.level.theme.accent, 60, speed=120)
                self._burst(e.cx, e.y + e.h / 2, self.level.theme.hazard, 40, speed=90)
                self.shake = 0.8
                self.shake_mag = 5.0
                self.events.append("boss_down")
            else:
                self._popup(e.cx, e.y, "PHASE " + str(3 - e.hp), self.level.theme.accent)
                self._burst(e.cx, e.y, self.level.theme.accent, 18, speed=70)
            return
        # Keep the enemy alive just long enough to render its flattened
        # sprite; the squash timer removes it on the next update.
        e.squash = 0.3 if e.kind != "koopa" else 0.45
        e.alive = True
        p.combo += 1
        points = min(1000, 100 * (2 ** min(p.combo - 1, 3)))
        self.run.add_score(points)
        self._popup(e.cx, e.y, f"+{points}", self.level.theme.accent)
        self._burst(e.cx, e.cy if hasattr(e, "cy") else e.y + e.h / 2,
                   self.level.theme.ink, 10)

    def _damage_enemy(self, e: Enemy, *, dash: bool = False) -> None:
        if e.kind == "boss":
            if e.invuln > 0:
                return
            e.hp -= 1
            e.invuln = 1.0
            self.shake = 0.5
            self.shake_mag = 4.0
            if e.hp <= 0:
                e.alive = False
                self.boss_defeated = True
                self.level.open_gate()
                self.run.add_score(5000)
                self._popup(e.cx, e.y, "+5000", self.level.theme.accent)
                self._burst(e.cx, e.y + e.h / 2, self.level.theme.accent, 70, speed=130)
                self.events.append("boss_down")
            return
        e.alive = False
        e.squash = 0.2
        self.run.add_score(100)
        self._popup(e.cx, e.y, "+100", self.level.theme.accent)
        self._burst(e.cx, e.y + e.h / 2, self.level.theme.accent, 16, speed=80)

    def _hurt_player(self, source: Enemy | None = None) -> None:
        p = self.player
        if p.dead or p.invuln > 0 or p.dash_time > 0 or self.clearing:
            return
        if p.big:
            p.set_big(False)
            p.invuln = 1.8
            p.vy = -150
            if source:
                p.vx = -70 if source.cx > p.cx else 70
            self.shake = 0.25
            self.shake_mag = 2.0
            self._burst(p.cx, p.y + p.h / 2, self.level.theme.accent, 22, speed=60)
            self._popup(p.x, p.y - 8, "DECOHERED", self.level.theme.accent)
            self.events.append("hurt")
            return
        self._kill_player()

    def _kill_player(self, *, fell: bool = False) -> None:
        p = self.player
        if p.dead:
            return
        p.dead = True
        p.dead_timer = 1.25
        p.vy = -240 if not fell else 0
        p.vx = 0
        p.dash_time = 0
        self.run.deaths += 1
        self.shake = max(self.shake, 0.3)
        self.shake_mag = 3.0
        if not self.run.speedrun:
            self.run.lives = max(0, self.run.lives - 1)
            self.run.add_score(-250)
        self._burst(p.cx, p.y + p.h / 2, self.level.theme.hazard, 30, speed=90)
        self.events.append("death")

    def _update_dead(self, dt: float) -> None:
        p = self.player
        p.dead_timer -= dt
        p.vy += GRAVITY * 0.8 * dt
        p.y += p.vy * dt
        if p.dead_timer <= 0:
            if self.run.speedrun:
                self.restart_level(use_checkpoint=False)
                self.events.append("retry")
                return
            if self.run.lives <= 0:
                self.finished = True
                self.events.append("game_over")
                return
            self.restart_level(use_checkpoint=True)
            self.events.append("respawn")

    def _update_clearing(self, dt: float) -> None:
        self.clear_timer -= dt
        p = self.player
        p.vx = 0
        if p.slide > 0:
            floor = self.level.flag_base()
            if p.bottom < floor:
                p.y = min(floor - p.h, p.y + 55 * dt)
            p.slide -= dt
        self._update_camera(dt)
        if self.clear_timer <= 0 and not self.finished:
            self.finished = True
            self.events.append("clear")

    # ------------------------------------------------------------------
    # items, blocks, checkpoints, goal
    # ------------------------------------------------------------------
    def _update_items(self, dt: float) -> None:
        p = self.player
        for coin in self.coins:
            if coin.collected:
                continue
            coin.anim += dt * 7
            if overlap(p.x, p.y, p.w, p.h,
                       coin.x - 4, coin.y - 4, 8, 8):
                self._collect_coin(coin)
        for m in self.mushrooms:
            if not m.alive:
                continue
            m.anim += dt
            if m.emerge > 0:
                m.emerge -= dt
                m.y -= 22 * dt
                continue
            m.vy += GRAVITY * dt
            m.x += m.vx * dt
            # horizontal collision
            tx = int((m.right - 0.01) // TILE) if m.vx > 0 else int(m.x // TILE)
            mid = int((m.y + m.h / 2) // TILE)
            if self.level.is_solid(tx, mid):
                m.vx *= -1
                m.x += m.vx * dt * 2
            m.y += m.vy * dt
            ty = int((m.bottom - 0.01) // TILE)
            for tx2 in range(int(m.x // TILE), int(m.right // TILE) + 1):
                if self.level.is_solid(tx2, ty) or self.level.is_oneway(tx2, ty):
                    m.y = ty * TILE - m.h
                    m.vy = 0
                    break
            if overlap(p.x, p.y, p.w, p.h, m.x, m.y, m.w, m.h):
                m.alive = False
                if not p.big:
                    p.set_big(True)
                    self._popup(p.x, p.y - 8, "SUPER!", self.level.theme.accent)
                else:
                    self.run.add_score(1000)
                    self._popup(p.x, p.y - 8, "+1000", self.level.theme.accent)
                self._burst(m.x + 4, m.y + 4, self.level.theme.accent, 20, speed=50)
            if m.y > self.level.height * TILE + 40:
                m.alive = False
        self.mushrooms = [m for m in self.mushrooms if m.alive]

    def _collect_coin(self, coin: Coin) -> None:
        coin.collected = True
        p = self.player
        if coin.kind == "orb":
            self.run.add_score(500)
            p.qflux = min(100, p.qflux + 50)
            self._popup(coin.x, coin.y - 4, "+500 FLUX", self.level.theme.accent)
            self._burst(coin.x, coin.y, self.level.theme.accent, 24, speed=80)
        else:
            self.run.add_score(200)
            self.run.coins += 1
            self.level_stats_coins = getattr(self, "level_stats_coins", 0) + 1
            self._popup(coin.x, coin.y - 4, "+200", self.level.theme.ink)
            text_color = self.level.theme.accent if coin.kind == "entangled" else self.level.theme.ink
            self._burst(coin.x, coin.y, text_color, 8, speed=35)
            if coin.kind == "entangled" and coin.pair is not None:
                partner = next((c for c in self.coins
                                if c.ident == coin.pair and not c.collected), None)
                if partner:
                    partner.collected = True
                    self.run.add_score(300)
                    self.run.coins += 1
                    self._popup(partner.x, partner.y - 4, "COLLAPSED +300",
                                self.level.theme.accent)
                    self._burst(partner.x, partner.y, self.level.theme.accent, 22, speed=65)
                    self.beams.append(Beam(coin.x, coin.y, partner.x, partner.y, 0.45))
                    self.shake = max(self.shake, 0.1)
                    self.shake_mag = 1.0
            if self.run.coins and self.run.coins % 50 == 0:
                self.run.lives += 1
                self._popup(p.cx, p.y - 14, "1 UP", self.level.theme.accent)
        self.sound_flash = 0.12

    def _update_blocks(self, dt: float) -> None:
        for key in list(self.block_bumps):
            self.block_bumps[key] -= dt
            if self.block_bumps[key] <= 0:
                del self.block_bumps[key]

    def hit_block(self, tx: int, ty: int) -> None:
        ch = self.level.tile(tx, ty)
        if ch not in "?B":
            return
        self.block_bumps[(tx, ty)] = 0.22
        p = self.player
        if ch == "?":
            self.level.grid[ty][tx] = "X"
            if self.last_reward == 1:
                self.mushrooms.append(Mushroom(tx * TILE + 1, ty * TILE - 8, 26))
                self._popup(tx * TILE + 4, ty * TILE - 14, "SUPER",
                            self.level.theme.accent)
            else:
                self.run.add_score(200)
                self.run.coins += 1
                self._popup(tx * TILE + 4, ty * TILE - 10, "+200", self.level.theme.ink)
            self._burst(tx * TILE + 4, ty * TILE, self.level.theme.accent, 12, speed=55)
            self.sound_flash = 0.15
        elif ch == "B":
            if p.big:
                self.level.grid[ty][tx] = "."
                self.run.add_score(50)
                self._burst(tx * TILE + 4, ty * TILE + 4, self.level.theme.brick, 18, speed=80)
            else:
                self._burst(tx * TILE + 4, ty * TILE, self.level.theme.brick, 6, speed=35)

    def _check_checkpoints(self) -> None:
        p = self.player
        for cp in self.level.checkpoints:
            if cp.active:
                continue
            if p.right > cp.x - 3 and p.bottom > cp.y - 28 and abs(p.bottom - cp.y) < 20:
                cp.active = True
                self.checkpoint_active = True
                self.checkpoint_pos = (cp.x - p.w / 2, cp.y - p.h)
                self._popup(cp.x, cp.y - 24, "ENTANGLED", self.level.theme.accent)
                self._burst(cp.x, cp.y - 12, self.level.theme.accent, 18, speed=55)
                self.events.append("checkpoint")

    def _check_goal(self) -> None:
        if self.clearing or self.finished or not self.level.flag:
            return
        p = self.player
        fx = self.level.flag_x()
        if p.right >= fx - 4:
            if self.level.gate_cells and not self.level.gate_open:
                return
            self.clearing = True
            self.clear_timer = 1.35
            p.vx = 0
            p.slide = 1.1
            p.x = fx - p.w - 1
            p.y = min(p.y, self.level.flag_base() - p.h)
            bonus = 1000 + int(max(0.0, self.level.par - self.level_time) * 20)
            self.run.add_score(bonus)
            self.run.level_times.append(self.level_time)
            if self.run.speedrun:
                self.run.splits.append(self.run.run_time)
            else:
                self.run.splits.append(self.level_time)
            self._popup(p.cx, p.y - 12, f"+{bonus}", self.level.theme.accent)
            self._burst(p.cx, p.y, self.level.theme.accent, 40, speed=100)
            self._burst(p.cx - 20, p.y - 10, self.level.theme.ink, 20, speed=80)
            self.shake = 0.3
            self.shake_mag = 2.0
            self.events.append("goal")

    # ------------------------------------------------------------------
    # fx / camera
    # ------------------------------------------------------------------
    def _update_effects(self, dt: float) -> None:
        for particle in self.particles:
            particle.life -= dt
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            particle.vy += particle.gravity * dt
        self.particles = [p for p in self.particles if p.life > 0]
        for popup in self.popups:
            popup.life -= dt
            popup.y -= 18 * dt
        self.popups = [p for p in self.popups if p.life > 0]
        for beam in self.beams:
            beam.life -= dt
        self.beams = [b for b in self.beams if b.life > 0]
        for f in self.fireballs:
            f.anim += dt
        self.fireballs = [f for f in self.fireballs if f.alive]
        for m in self.mushrooms:
            m.anim += dt
        if self.player.invuln > 0 and self.time % 0.09 < dt:
            self._burst(self.player.cx, self.player.y + self.player.h / 2,
                        self.level.theme.accent, 1, speed=20)
        if self.last_echo and self.time % 0.13 < dt:
            self._burst(self.player.cx + self.rng.uniform(-12, 12),
                        self.player.y + self.rng.uniform(0, self.player.h),
                        self.level.theme.accent, 1, speed=6)

    def _update_camera(self, dt: float) -> None:
        p = self.player
        max_x = max(0.0, self.level.width * TILE - self.view_w)
        max_y = max(0.0, self.level.height * TILE - self.view_h)
        tx = min(max(0.0, p.cx - self.view_w * 0.42), max_x)
        ty = min(max(0.0, p.bottom - self.view_h * 0.72), max_y)
        self.camera_x += (tx - self.camera_x) * min(1.0, dt * 9.0)
        self.camera_y += (ty - self.camera_y) * min(1.0, dt * 9.0)

    def _popup(self, x: float, y: float, text: str, color: tuple[int, int, int]) -> None:
        if len(self.popups) < 24:
            self.popups.append(Popup(x, y, text, color))

    def _burst(self, x: float, y: float, color: tuple[int, int, int], n: int,
               speed: float = 50.0) -> None:
        if len(self.particles) > 260:
            return
        for _ in range(n):
            self.particles.append(Particle(
                x, y,
                self.rng.uniform(-speed, speed),
                self.rng.uniform(-speed, speed) - 20,
                self.rng.uniform(0.18, 0.55),
                color,
                1 if self.rng.random() < 0.8 else 2,
            ))

    # ------------------------------------------------------------------
    # info for UI / rendering
    # ------------------------------------------------------------------
    @property
    def boss_hp(self) -> int:
        return max(0, self.boss.hp) if self.boss else 0

    @property
    def total_coins(self) -> int:
        return self.run.coins

    def status_line(self) -> str:
        q = self.qresult
        if not q:
            return "QPU OFFLINE"
        return (f"QPU {q.bits.count(1):02d} | G{q.gate_count:02d} D{q.depth:02d} | "
                f"PSI {q.entropy:02d} | ECHO {q.echo} | {q.sample_time_ms:.1f}MS")
