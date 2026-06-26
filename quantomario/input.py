"""Raw Unix keyboard input and the terminal's press-only movement memory.

Terminals traditionally do not report key releases.  Movement therefore uses a
small input-memory window refreshed by key auto-repeat; jumping is edge based.
The game documents this and works around it in the physics (air momentum).
"""

from __future__ import annotations

import os
import select
import sys
import time
from dataclasses import dataclass

from .entities import Controls


_SEMANTIC = {
    "a": "left", "A": "left",
    "d": "right", "D": "right",
    "w": "jump", "W": "jump", " ": "jump",
    "s": "down", "S": "down",
    "e": "dash", "E": "dash",
    "x": "sprint", "X": "sprint",
    "p": "pause", "P": "pause",
    "g": "lab", "G": "lab",
    "q": "quit", "Q": "quit",
    "c": "color", "C": "color",
    "h": "help", "H": "help",
    "m": "mute", "M": "mute",
}


class KeyReader:
    def __init__(self) -> None:
        self.fd = sys.stdin.fileno()
        self.buf = b""
        self.esc_at = 0.0

    def poll(self) -> list[str]:
        events: list[str] = []
        try:
            while select.select([self.fd], [], [], 0.0)[0]:
                chunk = os.read(self.fd, 4096)
                if not chunk:
                    break
                self.buf += chunk
        except OSError:
            return events
        self.buf, new = self._parse(self.buf)
        events.extend(new)
        return events

    def _parse(self, buf: bytes) -> tuple[bytes, list[str]]:
        events: list[str] = []
        i = 0
        n = len(buf)
        while i < n:
            b = buf[i]
            if b == 0x03:  # Ctrl-C
                events.append("ctrl-c")
                i += 1
                continue
            if b == 0x1B:
                # arrows and common CSI/SS3 sequences
                if i + 1 >= n:
                    # Could be a lone Escape. Resolve after a short hold.
                    if time.monotonic() - self.esc_at > 0.05:
                        events.append("pause")
                        i += 1
                        continue
                    break
                if buf[i + 1:i + 2] == b"[":
                    if i + 2 >= n:
                        break
                    code = buf[i + 2:i + 3]
                    if code in (b"A", b"B", b"C", b"D"):
                        ev = {b"A": "jump", b"B": "down",
                              b"C": "right", b"D": "left"}[code]
                        events.append(ev)
                        events.append({"jump": "nav_up", "down": "nav_down",
                                       "right": "nav_right", "left": "nav_left"}[ev])
                        i += 3
                        continue
                    # consume other CSI sequences (function keys etc.)
                    j = i + 2
                    while j < n and not (0x40 <= buf[j] <= 0x7E):
                        j += 1
                    i = min(n, j + 1)
                    continue
                if buf[i + 1:i + 2] == b"O":
                    if i + 2 >= n:
                        break
                    code = buf[i + 2:i + 3]
                    if code in (b"A", b"B", b"C", b"D"):
                        ev = {b"A": "jump", b"B": "down",
                              b"C": "right", b"D": "left"}[code]
                        events.append(ev)
                        events.append({"jump": "nav_up", "down": "nav_down",
                                       "right": "nav_right", "left": "nav_left"}[ev])
                        i += 3
                        continue
                    i += 3
                    continue
                # Alt+key or unrecognised escape: ignore the escape.
                i += 1
                continue
            ch = None
            if b == 0x0D or b == 0x0A:
                events.append("enter")
                i += 1
                continue
            if b in (0x7F, 0x08):
                events.append("backspace")
                i += 1
                continue
            if b == 0x09:
                events.append("tab")
                i += 1
                continue
            try:
                ch = bytes([b]).decode("utf-8")
            except UnicodeDecodeError:
                # consume a multi-byte UTF-8 code point
                for ln in (2, 3, 4):
                    try:
                        ch = buf[i:i + ln].decode("utf-8")
                        i += ln - 1
                        break
                    except UnicodeDecodeError:
                        continue
            i += 1
            if not ch:
                continue
            if ch in _SEMANTIC:
                events.append(_SEMANTIC[ch])
            if ch.isprintable():
                events.append("ch:" + ch)
            if ch == " ":
                events.append("ch: ")
        self.esc_at = time.monotonic()
        return buf[i:], events


@dataclass
class _DirState:
    until: float = 0.0
    last: float = 0.0
    repeats: int = 0


class InputController:
    """Turns press events into a stable per-frame Controls snapshot."""

    GRACE = 0.30

    def __init__(self) -> None:
        self.dirs = {-1: _DirState(), 1: _DirState()}
        self.last_dir = 0
        self.down_until = 0.0
        self.jump_pressed = False
        self.jump_until = 0.0
        self.dash_pressed = False
        self.sprint_pressed = False
        self._clock = time.monotonic()
        self.last_jump_at = 0.0

    def set_clock(self, now: float | None = None) -> None:
        self._clock = time.monotonic() if now is None else now

    def feed(self, events: list[str]) -> None:
        now = time.monotonic()
        self.set_clock(now)
        for ev in events:
            if ev == "left":
                self._dir(-1, now)
            elif ev == "right":
                self._dir(1, now)
            elif ev == "down":
                self.down_until = now + self.GRACE
            elif ev == "jump":
                self.jump_pressed = True
                self.jump_until = now + 0.12
                self.last_jump_at = now
            elif ev == "dash":
                self.dash_pressed = True
            elif ev == "sprint":
                self.sprint_pressed = True

    def _dir(self, d: int, now: float) -> None:
        st = self.dirs[d]
        if now - st.last > 0.18:
            st.repeats = 0
        st.repeats += 1
        st.last = now
        st.until = now + self.GRACE
        self.last_dir = d

    def update(self, dt: float) -> None:
        self._clock += dt
        # Timers use monotonic internally, but we also let the app tick them
        # for deterministic headless tests.
        now = time.monotonic()
        self._clock = now

    def snapshot(self) -> Controls:
        now = time.monotonic()
        left = self.last_dir == -1 and now < self.dirs[-1].until
        right = self.last_dir == 1 and now < self.dirs[1].until
        down = now < self.down_until
        c = Controls(
            left=left,
            right=right,
            down=down,
            jump_held=now < self.jump_until,
            jump_pressed=self.jump_pressed,
            dash_pressed=self.dash_pressed,
            sprint_pressed=self.sprint_pressed,
        )
        self.jump_pressed = False
        self.dash_pressed = False
        self.sprint_pressed = False
        return c

    def release_all(self) -> None:
        now = time.monotonic()
        for st in self.dirs.values():
            st.until = now
        self.down_until = now
        self.jump_pressed = False
        self.dash_pressed = False
        self.sprint_pressed = False
        self.last_dir = 0
