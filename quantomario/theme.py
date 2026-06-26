"""Colour themes: Quandoom-style x-ray (default) and a classic palette."""

from __future__ import annotations

from dataclasses import dataclass, field

RGB = tuple[int, int, int]

# Entity sprite palette.  Transparent is '.', everything else must exist here.
PALETTE: dict[str, RGB] = {
    "K": (12, 14, 18),       # outline / black
    "W": (255, 255, 255),
    "w": (206, 216, 225),
    "m": (137, 150, 162),
    "d": (72, 82, 94),
    "R": (229, 57, 53),      # Mario red
    "r": (156, 32, 40),
    "S": (255, 198, 148),    # skin
    "s": (212, 140, 96),
    "N": (126, 75, 38),      # brown
    "n": (84, 48, 24),
    "B": (44, 92, 205),      # overalls blue
    "b": (25, 51, 122),
    "G": (67, 176, 71),      # green
    "g": (34, 111, 48),
    "Y": (255, 213, 74),     # yellow
    "y": (209, 154, 27),
    "O": (242, 143, 43),     # orange
    "o": (172, 81, 19),
    "A": (89, 227, 255),     # quantum cyan
    "V": (178, 140, 255),    # quantum violet
    "P": (169, 89, 255),
    "C": (255, 241, 210),    # cream
    "T": (63, 233, 181),     # teal
}

# In scan mode all physical colours collapse into a narrow phosphor palette.
XRAY_MAP: dict[str, RGB] = {
    "K": (5, 7, 10),
    "W": (232, 248, 255),
    "w": (178, 205, 221),
    "m": (118, 146, 163),
    "d": (48, 65, 78),
    # Keep a readable luminance ladder in scan mode: cap bright, skin mid,
    # overalls dark, boots nearly black.  Without this the monochrome Mario
    # collapses into one phosphor blob at small terminal sizes.
    "R": (238, 250, 255),
    "r": (128, 157, 175),
    "S": (176, 207, 223),
    "s": (112, 141, 158),
    "N": (86, 112, 129),
    "n": (40, 57, 71),
    "B": (64, 96, 120),
    "b": (31, 50, 65),
    "G": (204, 231, 243),
    "g": (112, 144, 162),
    "Y": (245, 251, 255),
    "y": (150, 178, 194),
    "O": (210, 233, 244),
    "o": (104, 131, 148),
    "A": (89, 227, 255),
    "V": (178, 140, 255),
    "P": (169, 89, 255),
    "C": (238, 249, 255),
    "T": (104, 247, 212),
}


@dataclass
class WorldTheme:
    key: str
    bg: RGB
    bg2: RGB
    ink: RGB
    dim: RGB
    faint: RGB
    accent: RGB
    hazard: RGB
    terrain: RGB
    terrain_fill: RGB
    brick: RGB
    brick_fill: RGB
    platform: RGB
    star: RGB
    hud_fg: RGB
    hud_dim: RGB
    hud_bg: RGB
    classic: dict[str, RGB] = field(default_factory=dict)

    def color(self, ch: str, xray: bool = True) -> RGB:
        if ch == ".":
            return self.bg
        if xray:
            return XRAY_MAP.get(ch, self.ink)
        return self.classic.get(ch, PALETTE.get(ch, self.ink))

    def sprite_palette(self, xray: bool) -> dict[str, RGB]:
        if xray:
            return XRAY_MAP
        # Classic entities are constant across worlds; hazards can be tinted.
        return PALETTE


def make_theme(**overrides) -> WorldTheme:
    base = WorldTheme(
        key="plains",
        bg=(3, 6, 9),
        bg2=(7, 12, 17),
        ink=(232, 248, 255),
        dim=(150, 180, 196),
        faint=(46, 62, 74),
        accent=(89, 227, 255),
        hazard=(255, 105, 105),
        terrain=(232, 248, 255),
        terrain_fill=(66, 84, 97),
        brick=(210, 233, 244),
        brick_fill=(82, 102, 115),
        platform=(188, 218, 232),
        star=(123, 157, 174),
        hud_fg=(232, 248, 255),
        hud_dim=(129, 156, 172),
        hud_bg=(3, 6, 9),
    )
    classic = {
        "sky": (92, 148, 252),
        "sky2": (132, 180, 255),
        "ink": (255, 255, 255),
        "terrain": (200, 120, 60),
        "terrain_fill": (126, 68, 32),
        "brick": (205, 103, 52),
        "brick_fill": (126, 56, 29),
        "platform": (236, 196, 118),
        "hill": (74, 177, 74),
        "hill_dim": (40, 120, 53),
        "cloud": (248, 250, 255),
        "star": (255, 244, 190),
        "hazard": (225, 55, 45),
    }
    classic.update({
        "R": PALETTE["R"], "S": PALETTE["S"], "B": PALETTE["B"],
        "N": PALETTE["N"], "G": PALETTE["G"], "Y": PALETTE["Y"],
    })
    for k, v in overrides.items():
        if k in classic:
            classic[k] = v
        else:
            setattr(base, k, v)
    base.classic = classic
    return base


THEMES: dict[str, WorldTheme] = {
    "plains": make_theme(key="plains"),
    "caverns": make_theme(
        key="caverns",
        bg=(2, 5, 10), bg2=(5, 11, 16),
        ink=(207, 240, 255), dim=(112, 158, 183), faint=(31, 52, 64),
        accent=(94, 233, 255), hazard=(255, 128, 92),
        classic={
            "sky": (8, 14, 26), "sky2": (17, 28, 43),
            "ink": (210, 233, 247),
            "terrain": (108, 104, 145), "terrain_fill": (55, 48, 84),
            "brick": (125, 91, 154), "brick_fill": (63, 42, 84),
            "platform": (160, 157, 190),
            "hill": (42, 53, 90), "hill_dim": (25, 30, 57),
            "cloud": (110, 134, 160), "star": (126, 217, 255),
            "hazard": (255, 118, 78),
        },
    ),
    "skyway": make_theme(
        key="skyway",
        bg=(4, 8, 15), bg2=(9, 17, 27),
        ink=(226, 246, 255), dim=(135, 176, 203), faint=(37, 58, 76),
        accent=(118, 235, 255), hazard=(255, 120, 130),
        classic={
            "sky": (116, 186, 255), "sky2": (190, 228, 255),
            "ink": (255, 255, 255),
            "terrain": (238, 247, 255), "terrain_fill": (118, 168, 209),
            "brick": (178, 220, 250), "brick_fill": (97, 143, 182),
            "platform": (225, 244, 255),
            "hill": (155, 207, 245), "hill_dim": (108, 160, 206),
            "cloud": (254, 254, 255), "star": (255, 255, 255),
            "hazard": (255, 105, 120),
        },
    ),
    "foundry": make_theme(
        key="foundry",
        bg=(7, 4, 5), bg2=(15, 7, 8),
        ink=(255, 233, 220), dim=(192, 139, 128), faint=(69, 38, 38),
        accent=(255, 176, 90), hazard=(255, 96, 45),
        classic={
            "sky": (27, 12, 15), "sky2": (55, 21, 18),
            "ink": (255, 232, 214),
            "terrain": (113, 87, 92), "terrain_fill": (55, 40, 47),
            "brick": (151, 77, 60), "brick_fill": (80, 38, 33),
            "platform": (205, 160, 123),
            "hill": (64, 34, 35), "hill_dim": (36, 19, 21),
            "cloud": (100, 60, 54), "star": (255, 152, 84),
            "hazard": (255, 84, 31),
        },
    ),
    "observable": make_theme(
        key="observable",
        bg=(3, 3, 8), bg2=(8, 7, 17),
        ink=(240, 235, 255), dim=(154, 139, 198), faint=(47, 39, 76),
        accent=(191, 140, 255), hazard=(255, 93, 121),
        classic={
            "sky": (8, 6, 20), "sky2": (22, 15, 48),
            "ink": (245, 238, 255),
            "terrain": (93, 88, 124), "terrain_fill": (43, 38, 67),
            "brick": (125, 104, 170), "brick_fill": (62, 48, 94),
            "platform": (177, 157, 214),
            "hill": (38, 30, 66), "hill_dim": (22, 17, 42),
            "cloud": (96, 84, 140), "star": (218, 176, 255),
            "hazard": (255, 84, 131),
        },
    ),
}


def theme_for(key: str) -> WorldTheme:
    return THEMES.get(key, THEMES["plains"])
