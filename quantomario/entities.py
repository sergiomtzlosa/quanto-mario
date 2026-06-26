"""Runtime entities shared by the simulation and the renderer."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from .levels import MovingPlatformSpec, TILE


@dataclass
class Controls:
    left: bool = False
    right: bool = False
    down: bool = False
    jump_held: bool = False
    jump_pressed: bool = False
    dash_pressed: bool = False
    sprint_pressed: bool = False

    @property
    def direction(self) -> int:
        if self.left and not self.right:
            return -1
        if self.right and not self.left:
            return 1
        return 0


@dataclass
class Player:
    x: float = 0
    y: float = 0
    w: float = 6
    h: float = 10
    vx: float = 0
    vy: float = 0
    on_ground: bool = False
    big: bool = False
    face: int = 1
    anim: float = 0
    invuln: float = 0
    dead: bool = False
    dead_timer: float = 0
    dash_time: float = 0
    dash_cool: float = 0
    qflux: int = 100
    jump_buffer: float = 0
    coyote: float = 0
    drop_through: float = 0
    combo: int = 0
    squash: float = 0
    riding: int | None = None
    slide: float = 0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def right(self) -> float:
        return self.x + self.w

    def set_big(self, big: bool) -> None:
        if big == self.big:
            return
        old_bottom = self.bottom
        self.big = big
        self.h = 15 if big else 10
        self.w = 7 if big else 6
        self.y = old_bottom - self.h


@dataclass
class Enemy:
    kind: str
    x: float
    y: float
    w: float
    h: float
    vx: float = 0
    vy: float = 0
    dir: int = -1
    base_x: float = 0
    base_y: float = 0
    alive: bool = True
    on_ground: bool = False
    squash: float = 0
    mood: int = 0
    mood_t: float = 0
    anim: float = 0
    hp: int = 1
    invuln: float = 0
    fire_cd: float = 1.2
    jump_cd: float = 0.8
    active: bool = False
    index: int = 0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def right(self) -> float:
        return self.x + self.w


@dataclass
class Coin:
    x: float
    y: float
    kind: str
    pair: int | None = None
    ident: int = 0
    collected: bool = False
    anim: float = 0
    pop: float = 0


@dataclass
class MovingPlatform:
    spec: MovingPlatformSpec
    index: int
    x: float
    y: float
    px: float
    py: float
    w: int = 4 * TILE
    h: int = 4
    t: float = 0.0

    @classmethod
    def from_spec(cls, spec: MovingPlatformSpec, index: int) -> "MovingPlatform":
        return cls(spec, index, spec.x, spec.y, spec.x, spec.y,
                   w=spec.w * TILE, h=spec.h, t=spec.phase)

    def update(self, dt: float) -> None:
        self.t += dt
        self.px, self.py = self.x, self.y
        phase = math.sin((self.t / max(0.1, self.spec.period)) * math.tau)
        self.x = self.spec.x + self.spec.dx * phase
        self.y = self.spec.y + self.spec.dy * phase


@dataclass
class Mushroom:
    x: float
    y: float
    vx: float
    vy: float = 0
    emerge: float = 0.45
    alive: bool = True
    anim: float = 0
    w: int = 9
    h: int = 8

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


@dataclass
class Fireball:
    x: float
    y: float
    vx: float
    vy: float = 0
    life: float = 4.0
    alive: bool = True
    anim: float = 0
    radius: int = 4


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    color: tuple[int, int, int]
    size: int = 1
    gravity: float = 160
    kind: str = "dot"


@dataclass
class Popup:
    x: float
    y: float
    text: str
    color: tuple[int, int, int]
    life: float = 0.9
    max_life: float = 0.9


@dataclass
class Beam:
    x0: float
    y0: float
    x1: float
    y1: float
    life: float = 0.35
    max_life: float = 0.35


@dataclass
class Run:
    mode: str = "story"          # story | speedrun
    level_index: int = 0
    score: int = 0
    coins: int = 0
    lives: int = 3
    deaths: int = 0
    run_time: float = 0.0        # speedrun IGT
    splits: list[float] = field(default_factory=list)
    level_times: list[float] = field(default_factory=list)
    started: bool = False
    finished: bool = False
    seed: int | None = None
    level_score_start: int = 0
    level_coins_start: int = 0

    @property
    def speedrun(self) -> bool:
        return self.mode == "speedrun"

    @property
    def lives_text(self) -> str:
        return "INF" if self.speedrun else str(max(0, self.lives))

    def add_score(self, n: int) -> None:
        self.score = max(0, self.score + n)
