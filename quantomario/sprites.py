"""Hand-drawn terminal pixel sprites.  '.' is transparent."""

from __future__ import annotations

MARIO_SMALL_IDLE = (
    "...RRR...",
    "..RRRRR..",
    "..RRRRRR.",
    "..SSSKS..",
    ".SSSSKSS.",
    ".SSSSSSS.",
    "..SNSNS..",
    ".RRBRRR..",
    "SRRBBRRRS",
    "SSRBBRSS.",
    ".SBBBBBS.",
    "..BB.BB..",
    ".NNN.NNN.",
)

MARIO_SMALL_RUN1 = (
    "...RRR...",
    "..RRRRR..",
    "..RRRRRR.",
    "..SSSKS..",
    ".SSSSKSS.",
    ".SSSSSSS.",
    "..SNSNS..",
    ".RRBRRR..",
    "SRRBBRRRS",
    "SSRBBRSS.",
    ".SBBBBBS.",
    "..BBBB...",
    ".NN..NNN.",
    "NNN...NN.",
)

MARIO_SMALL_RUN2 = (
    "...RRR...",
    "..RRRRR..",
    "..RRRRRR.",
    "..SSSKS..",
    ".SSSSKSS.",
    ".SSSSSSS.",
    "..SNSNS..",
    ".RRBRRR..",
    "SRRBBRRRS",
    "SSRBBRSS.",
    ".SBBBBBS.",
    "...BBBB..",
    "..NN.NN..",
    ".NNN.NNN.",
)

MARIO_SMALL_JUMP = (
    "S..RRR..S",
    "SRRRRRRRS",
    ".RRRRRRR.",
    "..SSSKS..",
    ".SSSSKSS.",
    ".SSSSSSS.",
    "..SNSNS..",
    ".RRBRRR..",
    "RRRBBRRR.",
    "SSRBBRSS.",
    "..SBBBS..",
    "..BB.BB..",
    ".NN..NN..",
    "NNN..NNN.",
)

MARIO_BIG_IDLE = (
    "...RRR...",
    "..RRRRR..",
    "..RRRRRR.",
    "..SSSKS..",
    ".SSSSKSS.",
    ".SSSSSSS.",
    ".SSNSNSS.",
    "..RRRRR..",
    ".RRRBRRR.",
    "SRRRBRRRS",
    "SRRBBBRRS",
    ".SBBBBBS.",
    ".SBBBBBS.",
    ".SBYYYBS.",
    "SSBBBBBSS",
    "..BBBBB..",
    "(NNN.NNN)",
    "NNN...NNN",
)

MARIO_BIG_RUN1 = (
    "...RRR...",
    "..RRRRR..",
    "..RRRRRR.",
    "..SSSKS..",
    ".SSSSKSS.",
    ".SSSSSSS.",
    ".SSNSNSS.",
    "..RRRRR..",
    ".RRRBRRR.",
    "SRRRBRRRS",
    "SRRBBBRRS",
    ".SBBBBBS.",
    ".SBBBBBS.",
    ".SBYYYBS.",
    "SSBBBBBSS",
    "..BBBBB..",
    ".NNN..NN.",
    "NNN....NN",
)

MARIO_BIG_RUN2 = (
    "...RRR...",
    "..RRRRR..",
    "..RRRRRR.",
    "..SSSKS..",
    ".SSSSKSS.",
    ".SSSSSSS.",
    ".SSNSNSS.",
    "..RRRRR..",
    ".RRRBRRR.",
    "SRRRBRRRS",
    "SRRBBBRRS",
    ".SBBBBBS.",
    ".SBBBBBS.",
    ".SBYYYBS.",
    "SSBBBBBSS",
    "..BBBBB..",
    "..NN.NN..",
    ".NNN.NNN.",
)

MARIO_BIG_JUMP = (
    "S..RRR..S",
    "SRRRRRRRS",
    ".RRRRRRR.",
    "..SSSKS..",
    ".SSSSKSS.",
    ".SSSSSSS.",
    ".SSNSNSS.",
    "..RRRRR..",
    ".RRRBRRR.",
    "SRRRBRRRS",
    "SRRBBBRRS",
    ".SBBBBBS.",
    ".SBBBBBS.",
    ".SBYYYBS.",
    "SSBBBBBSS",
    "..BBBBB..",
    ".NN.NN...",
    "NNN.NNN..",
)

GOOMBA = (
    "..NNNNN..",
    ".NNNNNNN.",
    "NNWNNNWNN",
    "NNWNNNWNN",
    ".NNNNNNN.",
    "..NNNNN..",
    ".NN.N.NN.",
    "NNN...NNN",
)

GOOMBA_FLAT = (
    ".........",
    ".........",
    ".........",
    ".........",
    ".........",
    ".........",
    ".NNNNNNN.",
    "NNNNNNNNN",
)

KOOPA = (
    "..GGGGG..",
    ".GYYYYYG.",
    "GYWWYWWYG",
    "GYYYYYYYG",
    ".GYYYYYG.",
    "..GGGGG..",
    "...SSS...",
    "..SSSSS..",
    ".NNNNNNN.",
    "NNN...NNN",
    ".N.....N.",
)

FLYER = (
    "A.......A",
    "AA..A..AA",
    ".AAAAAAAA",
    "AA.AAA.AA",
    "A..A.A..A",
    "...V.V...",
)

COIN_FRAMES = (
    (
        "..YYY..",
        ".YYYYY.",
        "YYWWWYY",
        "YYWWWYY",
        "YYWWWYY",
        ".YYYYY.",
        "..YYY..",
    ),
    (
        "..YYY..",
        "..YWY..",
        "..YWY..",
        "..YWY..",
        "..YWY..",
        "..YYY..",
        "...Y...",
    ),
    (
        "...Y...",
        "...Y...",
        "...Y...",
        "...Y...",
        "...Y...",
        "...Y...",
        "...Y...",
    ),
    (
        "..YYY..",
        "..YWY..",
        "..YWY..",
        "..YWY..",
        "..YWY..",
        "..YYY..",
        "...Y...",
    ),
)

ORB = (
    "..AAAAA..",
    ".A.....A.",
    "A...W...A",
    "A..WWW..A",
    "A...W...A",
    ".A.....A.",
    "..AAAAA..",
    "...A.A...",
)

MUSHROOM = (
    "..RRRRR..",
    ".RWWWWWR.",
    "RWWWRWWWR",
    "RWWRRRWWR",
    "RRRRRRRRR",
    "..SSSSS..",
    "..SKSSK..",
    "..SSSSS..",
)

BRICK = (
    "BBBBBBBBB",
    "BKKBKKBKB",
    "BBBBBBBBB",
    "BKKBKKBKB",
    "BBBBBBBBB",
    "BKKBKKBKB",
    "BBBBBBBBB",
    "BKKBKKBKB",
)

QUESTION = (
    "YYYYYYYYY",
    "Y.......Y",
    "Y..WWW..Y",
    "Y.W...W.Y",
    "Y....W..Y",
    "Y...W...Y",
    "Y.......Y",
    "YYYYYYYYY",
)

USED_BLOCK = (
    "KKKKKKKKK",
    "K.......K",
    "K.......K",
    "K.......K",
    "K.......K",
    "K.......K",
    "K.......K",
    "KKKKKKKKK",
)

BOSS = (
    "......GGGGG......",
    ".....GGGGGGG.....",
    "....GGGYYYGGG....",
    "...GGGYYYYYGGG...",
    "..GGGGYYYYYGGGG..",
    "..GGWWWGGWWWGGG..",
    "..GGWGKGGKWGGGG..",
    "..GGGGGGGGGGGGG..",
    "..GGGNNNNNNGGGG..",
    "...GGNNNNNNGGG...",
    "....GNNNNNNG.....",
    ".....GGGGGG......",
    "...YYYYYYYYYYY...",
    "..YYWWWYYWWWYYY..",
    ".YYWWWWYYWWWWYYY.",
    ".YYWWWWYYWWWWYYY.",
    ".YYYYYYYYYYYYYYY.",
    "..GGGGGGGGGGGGG..",
    ".GGGGGGGGGGGGGGG.",
    "GGGGGGGGGGGGGGGGG",
    "GGGGG..GGG..GGGGG",
    ".GGG....G....GGG.",
    "..NNN.......NNN..",
    ".NNNNN.....NNNNN.",
    ".................",
)

SPRITES = {
    "mario_idle": MARIO_SMALL_IDLE,
    "mario_run1": MARIO_SMALL_RUN1,
    "mario_run2": MARIO_SMALL_RUN2,
    "mario_jump": MARIO_SMALL_JUMP,
    "mario_big_idle": MARIO_BIG_IDLE,
    "mario_big_run1": MARIO_BIG_RUN1,
    "mario_big_run2": MARIO_BIG_RUN2,
    "mario_big_jump": MARIO_BIG_JUMP,
    "goomba": GOOMBA,
    "goomba_flat": GOOMBA_FLAT,
    "koopa": KOOPA,
    "flyer": FLYER,
    "coin0": COIN_FRAMES[0],
    "coin1": COIN_FRAMES[1],
    "coin2": COIN_FRAMES[2],
    "coin3": COIN_FRAMES[3],
    "orb": ORB,
    "mushroom": MUSHROOM,
    "brick": BRICK,
    "question": QUESTION,
    "used_block": USED_BLOCK,
    "boss": BOSS,
}


def validate_sprites() -> list[str]:
    errors = []
    for name, art in SPRITES.items():
        if not art:
            errors.append(f"{name}: empty")
            continue
        w = len(art[0])
        for i, row in enumerate(art):
            if len(row) != w:
                errors.append(f"{name} row {i}: {len(row)} != {w}")
    return errors
