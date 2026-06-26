"""Five hand-authored worlds for QuantoMario.

The map format is deliberately boring ASCII so it can be edited without
touching the engine.  One character is one 8x8 tile.

    .  air                 #  solid earth/stone       =  one-way platform
    B  brick               ?  quantum block           X  spent block
    P  pipe                G  boss gate               F  flag / goal
    o  coin                e  entangled coin pair     *  quantum orb
    g  goomba              k  koopa                    f  quantum flyer
    !  checkpoint          W  boss                     ^  spikes
    ~  lava

All levels are 14 tiles tall.  The camera and terminal resolution adapt at
render time; the simulation always uses 8 px tiles so physics remains stable
in every terminal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .theme import theme_for, WorldTheme

H = 14
TILE = 8
SOLID = set("#B?XP G".replace(" ", ""))
HAZARD = set("^~")
ENTITY_CHARS = set("oegkfW!*")


@dataclass
class MovingPlatformSpec:
    x: float
    y: float
    w: int
    h: int
    dx: float
    dy: float
    period: float
    phase: float = 0.0


@dataclass
class LevelDef:
    key: str
    world: str
    name: str
    subtitle: str
    theme: str
    par: float
    rows: list[str]
    moving: list[MovingPlatformSpec] = field(default_factory=list)


class LevelBuilder:
    def __init__(self, width: int, height: int = H) -> None:
        self.W = width
        self.H = height
        self.grid = [["." for _ in range(width)] for _ in range(height)]
        self.moving: list[MovingPlatformSpec] = []

    def set(self, x: int, y: int, ch: str) -> None:
        if 0 <= x < self.W and 0 <= y < self.H:
            self.grid[y][x] = ch

    def fill(self, x0: int, y0: int, x1: int, y1: int, ch: str) -> None:
        for y in range(max(0, y0), min(self.H, y1)):
            for x in range(max(0, x0), min(self.W, x1)):
                self.grid[y][x] = ch

    def ground(self, x0: int, x1: int, top: int = 11) -> None:
        self.fill(x0, top, x1, self.H, "#")

    def slab(self, x0: int, x1: int, top: int, thickness: int = 2) -> None:
        self.fill(x0, top, x1, min(self.H, top + thickness), "#")

    def platform(self, x0: int, x1: int, y: int, ch: str = "=") -> None:
        self.fill(x0, y, x1, y + 1, ch)

    def pipe(self, x: int, top: int = 9, ground_top: int = 11) -> None:
        self.fill(x, top, x + 2, ground_top, "P")

    def blocks(self, x: int, y: int, pattern: str) -> None:
        for i, ch in enumerate(pattern):
            if ch != ".":
                self.set(x + i, y, ch)

    def coin(self, x: int, y: int) -> None:
        self.set(x, y, "o")

    def coin_row(self, x: int, y: int, n: int) -> None:
        for i in range(n):
            self.coin(x + i, y)

    def coin_arc(self, x: int, y: int, n: int, height: int = 3) -> None:
        for i in range(n):
            t = i / max(1, n - 1)
            dy = round(height * 4 * t * (1 - t))
            self.coin(x + i, y - dy)

    def orb(self, x: int, y: int) -> None:
        self.set(x, y, "*")

    def entangled(self, x: int, y: int) -> None:
        self.set(x, y, "e")

    def enemy(self, kind: str, x: int, ground_top: int = 11,
              y: int | None = None) -> None:
        self.set(x, ground_top - 1 if y is None else y, kind)

    def checkpoint(self, x: int, ground_top: int = 11) -> None:
        self.set(x, ground_top - 1, "!")

    def spikes(self, x0: int, x1: int, y: int = 10) -> None:
        self.fill(x0, y, x1, y + 1, "^")

    def lava(self, x0: int, x1: int, top: int = 11) -> None:
        self.fill(x0, top, x1, self.H, "~")

    def flag(self, x: int, ground_top: int = 11) -> None:
        self.set(x, max(2, ground_top - 5), "F")

    def boss(self, x: int, ground_top: int = 11) -> None:
        self.set(x, ground_top - 1, "W")

    def gate(self, x: int, ground_top: int = 11, height: int = 5) -> None:
        self.fill(x, ground_top - height, x + 1, ground_top, "G")

    def moving_platform(self, x: float, y: float, w: int, dx: float,
                        dy: float, period: float, phase: float = 0.0) -> None:
        self.moving.append(MovingPlatformSpec(x, y, w, 4, dx, dy, period, phase))

    def rows(self) -> list[str]:
        return ["".join(row) for row in self.grid]

    def level(self, *, key: str, world: str, name: str, subtitle: str,
              theme: str, par: float) -> LevelDef:
        return LevelDef(key, world, name, subtitle, theme, par,
                        self.rows(), list(self.moving))


def build_plains() -> LevelDef:
    b = LevelBuilder(196)
    b.ground(0, 34)
    b.ground(38, 66)
    b.ground(70, 104, 11)
    b.ground(108, 146)
    b.ground(150, 196)

    # gentle opening staircase and first toys
    b.blocks(13, 8, "?B?")
    b.coin_row(13, 6, 3)
    b.pipe(24, 9)
    b.enemy("g", 18)
    b.enemy("g", 31)
    b.enemy("k", 43)
    b.coin_arc(34, 8, 3, 2)
    b.blocks(44, 7, "BB?BB")
    b.coin_row(44, 5, 5)
    b.enemy("g", 56)
    b.enemy("g", 60)

    b.blocks(71, 8, "?")
    b.orb(73, 9)
    b.entangled(78, 7)
    b.enemy("k", 82)
    b.platform(84, 91, 8)
    b.coin_row(85, 7, 6)
    b.enemy("g", 93)
    b.pipe(98, 8)
    b.checkpoint(101)

    b.coin_arc(104, 8, 5, 3)
    b.platform(112, 118, 7)
    b.blocks(114, 7, "?B?")
    b.coin_row(112, 5, 7)
    b.enemy("g", 122)
    b.enemy("k", 128)
    b.entangled(132, 7)
    b.coin_row(136, 8, 4)
    b.enemy("g", 140)
    b.orb(143, 8)

    b.ground(140, 146, 9)
    b.enemy("k", 155)
    b.platform(158, 165, 8)
    b.coin_row(158, 7, 8)
    b.enemy("g", 166)
    b.blocks(170, 7, "B?B")
    b.coin_row(170, 5, 3)
    b.flag(181)
    b.ground(179, 196, 10)
    b.coin_arc(174, 9, 4, 2)
    return b.level(
        key="1-1", world="WORLD 1-1", name="SUPERPOSITION PLAINS",
        subtitle="ONE MARIO. TWO POSSIBLE PATHS.",
        theme="plains", par=95.0,
    )


def build_caverns() -> LevelDef:
    b = LevelBuilder(206)
    # cave ceiling + uneven floor
    b.fill(0, 0, 206, 2, "#")
    b.ground(0, 30, 11)
    b.ground(34, 58, 11)
    b.ground(62, 86, 10)
    b.ground(90, 118, 11)
    b.ground(122, 155, 10)
    b.ground(159, 206, 11)

    b.enemy("g", 12)
    b.blocks(16, 8, "?B?")
    b.coin_row(15, 6, 5)
    b.enemy("k", 24)
    b.coin_arc(30, 8, 4, 2)
    b.spikes(44, 47, 10)
    b.platform(42, 49, 7)
    b.coin_row(42, 6, 7)
    b.enemy("g", 53)
    b.blocks(56, 7, "BB")
    b.orb(59, 6)

    b.moving_platform(88, 72, 4, 32, 0, 3.4)
    b.platform(62, 68, 8)
    b.coin_row(63, 7, 5)
    b.enemy("k", 74)
    b.enemy("g", 80)
    b.coin_arc(86, 9, 4, 2)
    b.checkpoint(95)
    b.entangled(101, 7)
    b.blocks(104, 8, "?B?B?")
    b.coin_row(104, 6, 5)
    b.enemy("g", 112)
    b.spikes(114, 117, 10)
    b.platform(108, 120, 7)
    b.coin_row(114, 5, 5)

    b.coin_arc(118, 9, 4, 2)
    b.platform(126, 134, 8)
    b.coin_row(126, 7, 8)
    b.enemy("k", 138)
    b.blocks(140, 7, "B?B")
    b.orb(144, 8)
    b.enemy("g", 147)
    b.checkpoint(152)

    b.moving_platform(155, 72, 4, 0, -28, 3.0, 0.5)
    b.coin_arc(156, 8, 4, 3)
    b.enemy("g", 164)
    b.spikes(166, 169, 10)
    b.platform(162, 172, 7)
    b.coin_row(162, 6, 10)
    b.entangled(178, 7)
    b.enemy("k", 182)
    b.blocks(186, 8, "?B?")
    b.coin_row(186, 6, 3)
    b.flag(193)
    return b.level(
        key="1-2", world="WORLD 1-2", name="ENTANGLEMENT CAVERNS",
        subtitle="TWO COINS. ONE MEASUREMENT.",
        theme="caverns", par=110.0,
    )


def build_skyway() -> LevelDef:
    b = LevelBuilder(212)
    # floating islands; no full floor.  fall = measurement error.
    b.slab(0, 16, 10, 3)
    b.ground(0, 12, 11)
    b.slab(20, 33, 9, 2)
    b.slab(37, 50, 11, 2)
    b.slab(55, 69, 8, 2)
    b.slab(73, 87, 10, 2)
    b.slab(91, 104, 9, 2)
    b.slab(109, 126, 11, 2)
    b.slab(131, 145, 8, 2)
    b.slab(149, 164, 10, 2)
    b.slab(169, 185, 9, 2)
    b.slab(190, 212, 11, 2)

    b.blocks(6, 7, "?B?")
    b.coin_row(5, 5, 5)
    b.enemy("g", 10)
    b.coin_arc(16, 8, 4, 2)
    b.enemy("f", 25, y=5)
    b.coin_row(21, 7, 6)
    b.orb(29, 6)
    b.enemy("k", 40, ground_top=11)
    b.coin_arc(50, 9, 5, 3)
    b.platform(59, 66, 6)
    b.coin_row(59, 5, 6)
    b.enemy("f", 62, y=3)
    b.enemy("g", 78)
    b.blocks(80, 8, "B?B")
    b.coin_row(80, 6, 3)
    b.entangled(85, 6)
    b.moving_platform(105, 68, 4, 38, 0, 4.0)
    b.coin_arc(105, 7, 4, 3)
    b.enemy("f", 96, y=4)
    b.checkpoint(114)
    b.platform(117, 123, 8)
    b.coin_row(117, 7, 7)
    b.enemy("k", 120)
    b.blocks(136, 6, "?B?")
    b.coin_row(134, 4, 7)
    b.enemy("g", 141)
    b.enemy("f", 145, y=3)
    b.coin_arc(145, 9, 5, 3)
    b.moving_platform(166, 74, 4, 0, -30, 3.6)
    b.coin_arc(165, 8, 4, 2)
    b.enemy("g", 175)
    b.platform(176, 183, 7)
    b.coin_row(176, 6, 6)
    b.orb(181, 5)
    b.enemy("k", 194, ground_top=11)
    b.entangled(199, 8)
    b.flag(205, ground_top=11)
    b.coin_arc(200, 9, 3, 2)
    return b.level(
        key="1-3", world="WORLD 1-3", name="TUNNELING SKYWAY",
        subtitle="IF YOU DO NOT LOOK DOWN, YOU ARE ON SOLID GROUND.",
        theme="skyway", par=120.0,
    )


def build_foundry() -> LevelDef:
    b = LevelBuilder(214)
    b.ground(0, 28, 11)
    # lava channels with stepping stones
    b.ground(32, 54, 11)
    b.lava(55, 66, 10)
    b.ground(66, 88, 11)
    b.lava(89, 100, 10)
    b.ground(100, 128, 10)
    b.lava(129, 142, 10)
    b.ground(142, 170, 11)
    b.lava(171, 182, 10)
    b.ground(182, 214, 11)

    b.blocks(8, 7, "B?B")
    b.coin_row(8, 5, 5)
    b.enemy("g", 14)
    b.pipe(19, 9)
    b.enemy("k", 24)
    b.spikes(35, 38, 10)
    b.platform(33, 41, 7)
    b.coin_row(33, 6, 8)
    b.enemy("g", 46)
    b.blocks(49, 8, "?B?")
    b.orb(52, 7)

    b.platform(55, 60, 9)
    b.coin_row(55, 8, 6)
    b.platform(62, 66, 7)
    b.coin_row(62, 6, 5)
    b.enemy("k", 72)
    b.entangled(76, 7)
    b.enemy("g", 82)
    b.blocks(78, 8, "B?B")
    b.checkpoint(85)

    b.moving_platform(89, 64, 4, 38, 0, 4.4)
    b.coin_arc(89, 8, 4, 2)
    b.platform(97, 103, 8)
    b.enemy("k", 108, ground_top=10)
    b.spikes(112, 116, 9)
    b.platform(108, 118, 6)
    b.coin_row(108, 5, 11)
    b.enemy("g", 122)
    b.orb(124, 8)

    b.moving_platform(129, 68, 4, 0, -34, 3.2)
    b.coin_arc(129, 8, 4, 3)
    b.platform(136, 142, 8)
    b.coin_row(136, 7, 7)
    b.enemy("k", 147)
    b.blocks(150, 7, "?B?B")
    b.coin_row(149, 5, 7)
    b.enemy("g", 155)
    b.checkpoint(160)
    b.spikes(163, 166, 10)
    b.platform(162, 170, 7)
    b.coin_row(162, 6, 9)

    b.platform(171, 176, 8)
    b.coin_row(171, 7, 6)
    b.entangled(179, 7)
    b.enemy("k", 186)
    b.enemy("g", 192)
    b.blocks(188, 8, "B?B")
    b.orb(196, 7)
    b.flag(203)
    return b.level(
        key="1-4", world="WORLD 1-4", name="DECOHERENCE FOUNDRY",
        subtitle="HEAT IS JUST ENTROPY WITH A DRIP FEED.",
        theme="foundry", par=130.0,
    )


def build_observable() -> LevelDef:
    b = LevelBuilder(158)
    b.ground(0, 96, 11)
    b.ground(100, 158, 11)
    b.fill(0, 0, 158, 1, "#")

    b.blocks(7, 8, "?B?")
    b.coin_row(7, 6, 4)
    b.enemy("g", 14)
    b.enemy("k", 22)
    b.orb(17, 7)
    b.platform(26, 34, 8)
    b.coin_row(26, 7, 9)
    b.enemy("g", 38)
    b.blocks(41, 7, "BB?BB")
    b.coin_row(41, 5, 5)
    b.enemy("k", 49)
    b.spikes(55, 59, 10)
    b.platform(53, 62, 7)
    b.coin_row(53, 6, 10)
    b.checkpoint(66)
    b.entangled(70, 7)
    b.enemy("g", 74)
    b.pipe(79, 9)
    b.enemy("k", 86)
    b.coin_arc(90, 8, 4, 2)
    b.blocks(92, 7, "?")
    b.orb(94, 8)

    # boss arena
    b.lava(97, 100, 10)
    b.coin_row(98, 8, 2)
    b.boss(112)
    b.gate(126, height=6)
    b.coin_arc(128, 8, 3, 2)
    b.enemy("g", 148)
    b.flag(151)
    b.coin_row(143, 8, 5)
    b.entangled(104, 7)
    return b.level(
        key="1-5", world="WORLD 1-5", name="THE OBSERVABLE",
        subtitle="THE LAST ENEMY IS THE ONE WHO MEASURES YOU.",
        theme="observable", par=140.0,
    )


BUILDERS = (build_plains, build_caverns, build_skyway, build_foundry, build_observable)


def all_levels() -> list[LevelDef]:
    return [fn() for fn in BUILDERS]


@dataclass
class CoinSpec:
    x: float
    y: float
    kind: str
    pair: int | None = None
    ident: int = 0


@dataclass
class EnemySpec:
    kind: str
    x: float
    y: float
    w: int
    h: int


@dataclass
class Checkpoint:
    x: float
    y: float
    active: bool = False


class Level:
    """Runtime view of a LevelDef.  Gate state and checkpoint flags are reset
    when a level is retried."""

    def __init__(self, definition: LevelDef) -> None:
        self.defn = definition
        self.key = definition.key
        self.world = definition.world
        self.name = definition.name
        self.subtitle = definition.subtitle
        self.theme_key = definition.theme
        self.theme: WorldTheme = theme_for(definition.theme)
        self.par = definition.par
        self.grid = [list(row) for row in definition.rows]
        self.width = len(self.grid[0])
        self.height = len(self.grid)
        self.coin_specs: list[CoinSpec] = []
        self.enemy_specs: list[EnemySpec] = []
        self.checkpoints: list[Checkpoint] = []
        self.flag: tuple[int, int] | None = None
        self.boss_spec: EnemySpec | None = None
        self.gate_open = False
        self.gate_cells: set[tuple[int, int]] = set()
        self.spawn_x = 28.0
        self.spawn_y = 76.0
        self._parse()
        self.start_gate_open = False

    def _parse(self) -> None:
        ent: list[CoinSpec] = []
        for ty, row in enumerate(self.grid):
            for tx, ch in enumerate(row):
                if ch == "F":
                    self.flag = (tx, ty)
                    self.grid[ty][tx] = "."
                elif ch == "!":
                    self.checkpoints.append(Checkpoint(tx * TILE + TILE / 2,
                                                       (ty + 1) * TILE))
                    self.grid[ty][tx] = "."
                elif ch in "oe*":
                    spec = CoinSpec(tx * TILE + TILE / 2, ty * TILE + TILE / 2,
                                    {"o": "coin", "e": "entangled", "*": "orb"}[ch],
                                    ident=len(ent))
                    ent.append(spec)
                    self.grid[ty][tx] = "."
                elif ch in "gkf":
                    if ch == "g":
                        w, h = 8, 8
                    elif ch == "k":
                        w, h = 9, 11
                    else:
                        w, h = 9, 6
                    self.enemy_specs.append(
                        EnemySpec({"g": "goomba", "k": "koopa", "f": "flyer"}[ch],
                                  tx * TILE, (ty + 1) * TILE - h, w, h)
                    )
                    self.grid[ty][tx] = "."
                elif ch == "W":
                    self.boss_spec = EnemySpec("boss", tx * TILE,
                                               11 * TILE - 24, 17 * 2, 25 * 2)
                    self.grid[ty][tx] = "."
                elif ch == "G":
                    self.gate_cells.add((tx, ty))
        self.coin_specs = ent
        # Pair entangled coins in reading order.
        ents = [c for c in ent if c.kind == "entangled"]
        for i in range(0, len(ents) - 1, 2):
            ents[i].pair = ents[i + 1].ident
            ents[i + 1].pair = ents[i].ident
        # Spawn above the first solid tile in column 3/4.
        for sx in (3, 4, 2, 5):
            for ty in range(self.height):
                if self.grid[ty][sx] in SOLID:
                    self.spawn_x = sx * TILE
                    self.spawn_y = ty * TILE - 12
                    break
            else:
                continue
            break

    # --- queries -----------------------------------------------------
    def tile(self, tx: int, ty: int) -> str:
        if 0 <= tx < self.width and 0 <= ty < self.height:
            return self.grid[ty][tx]
        if tx < 0 or tx >= self.width:
            return "#"
        return "."

    def is_solid(self, tx: int, ty: int) -> bool:
        ch = self.tile(tx, ty)
        if ch == "G" and self.gate_open:
            return False
        return ch in SOLID

    def is_oneway(self, tx: int, ty: int) -> bool:
        return self.tile(tx, ty) == "="

    def is_hazard(self, tx: int, ty: int) -> bool:
        return self.tile(tx, ty) in HAZARD

    def solid_at_px(self, x: float, y: float) -> bool:
        return self.is_solid(int(x // TILE), int(y // TILE))

    def hazard_at_px(self, x: float, y: float) -> bool:
        return self.is_hazard(int(x // TILE), int(y // TILE))

    def flag_x(self) -> float:
        return (self.flag[0] * TILE + TILE / 2) if self.flag else self.width * TILE

    def flag_base(self) -> float:
        if not self.flag:
            return 10 * TILE
        tx, ty = self.flag
        for y in range(ty, self.height):
            if self.is_solid(tx, y):
                return y * TILE
        return (self.height - 1) * TILE

    def open_gate(self) -> None:
        self.gate_open = True

    def reset(self) -> None:
        self.gate_open = False


def level_defs() -> list[LevelDef]:
    return all_levels()
