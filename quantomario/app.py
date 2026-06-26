"""Interactive application shell for QuantoMario."""

from __future__ import annotations

import os
from pathlib import Path
import random
import sys
import time
from dataclasses import dataclass

from .entities import Controls, Run
from .game import Game
from .input import InputController, KeyReader
from .levels import level_defs
from .render import CellCanvas, PixelCanvas, Terminal, from_pixels
from .scores import Records, format_time
from .screens import Screens, TITLE_MENU, PAUSE_MENU, dim_cells, BG, INK, DIM, ACCENT, FAINT, HAZARD, AMBER
from .view import SceneRenderer, compute_layout


STEP = 1.0 / 60.0


class App:
    def __init__(self, records: Records, *, seed: int | None = None,
                 color_mode: str = "auto", fps: int = 30,
                 xray: bool = True) -> None:
        self.records = records
        self.seed = seed
        self.color_mode = color_mode
        self.fps = max(10, min(60, fps))
        self.t = 0.0
        self.running = True
        self.state = "title"
        self.return_state = "title"
        self.menu_index = 0
        self.pause_index = 0
        self.reader = KeyReader()
        self.controller = InputController()
        self.scene = SceneRenderer(xray=xray)
        self.screens = Screens()
        self.game: Game | None = None
        self.lab_game: Game | None = None
        self.run: Run | None = None
        self.intro_timer = 0.0
        self.clear_timer = 0.0
        self.toast_text = ""
        self.toast_timer = 0.0
        self.lab_message = ""
        self.lab_message_timer = 0.0
        self.name_buffer = ""
        self.pending: dict | None = None
        self.qualified = False
        self.submitted = False
        self.victory = False
        self.run_pb_before: float | None = None
        self.accum = 0.0
        self.last_size: tuple[int, int] | None = None
        self.last_now = time.monotonic()

    # ------------------------------------------------------------------
    def set_xray(self, xray: bool) -> None:
        self.scene.xray = xray
        self.records.render_mode = "xray" if xray else "classic"
        try:
            self.records.save()
        except OSError:
            pass

    def toggle_xray(self) -> None:
        self.set_xray(not self.scene.xray)

    # ------------------------------------------------------------------
    def run_loop(self) -> None:
        with Terminal(self.color_mode) as term:
            try:
                while self.running:
                    loop_start = time.perf_counter()
                    now = time.monotonic()
                    dt = min(0.1, max(0.0, now - self.last_now))
                    self.last_now = now
                    self.t += dt
                    cols, rows = term.size()
                    if cols < 40 or rows < 16:
                        cells = self._too_small(cols, rows)
                        events = self.reader.poll()
                        if any(e in ("ctrl-c", "quit", "pause") for e in events):
                            self.running = False
                        term.draw(cells)
                        self._sleep(loop_start)
                        continue
                    if self.last_size != (cols, rows):
                        term.write("\x1b[2J")
                        self.last_size = (cols, rows)
                    events = self.reader.poll()
                    if any(e == "ctrl-c" for e in events):
                        self.running = False
                        break
                    self._dispatch(events, cols, rows, dt)
                    cells = self._render(cols, rows, dt)
                    if self.toast_timer > 0:
                        self.toast_timer -= dt
                        self.screens.toast(cells, self.toast_text, ACCENT)
                    term.draw(cells)
                    self._sleep(loop_start)
            finally:
                pass

    def _sleep(self, loop_start: float) -> None:
        target = 1.0 / self.fps
        elapsed = time.perf_counter() - loop_start
        if elapsed < target:
            time.sleep(target - elapsed)

    # ------------------------------------------------------------------
    def _dispatch(self, events: list[str], cols: int, rows: int, dt: float) -> None:
        if self.state == "title":
            self._events_title(events)
        elif self.state == "records":
            if any(e in ("pause", "enter", "quit") for e in events):
                self.state = self.return_state
        elif self.state == "controls":
            if any(e in ("pause", "enter", "quit", "jump", "nav_up") for e in events):
                self.state = self.return_state
        elif self.state == "intro":
            self.intro_timer -= dt
            if self.intro_timer <= 0 or any(e in ("enter", "jump") for e in events):
                self.state = "play"
                self.run.started = True
                self.controller.release_all()
        elif self.state == "play":
            self._events_play(events, cols, rows, dt)
        elif self.state == "pause":
            self._events_pause(events)
        elif self.state == "lab":
            self._events_lab(events)
        elif self.state == "lab_help":
            for ev in events:
                if ev in ("help", "lab", "pause", "enter"):
                    self.state = "lab"
                    break
                if ev == "color":
                    self.toggle_xray()
                elif ev == "quit":
                    self.state = "lab"
                    break
        elif self.state == "clear":
            self.clear_timer -= dt
            if self.clear_timer <= 0 or any(e in ("enter", "jump") for e in events):
                self._advance_clear()
        elif self.state == "name":
            self._events_name(events)
        elif self.state == "results":
            if any(e in ("enter", "pause", "quit") for e in events):
                self.state = "title"
                self.menu_index = 0
                self.game = None
                self.run = None
        if self.lab_message_timer > 0:
            self.lab_message_timer -= dt
            if self.lab_message_timer <= 0:
                self.lab_message = ""

    def _events_title(self, events: list[str]) -> None:
        for ev in events:
            if ev in ("up", "nav_up") or ev == "ch:w":
                self.menu_index = (self.menu_index - 1) % len(TITLE_MENU)
            elif ev in ("down", "nav_down") or ev == "ch:s":
                self.menu_index = (self.menu_index + 1) % len(TITLE_MENU)
            elif ev == "enter":
                self._activate_title()
                return
            elif ev == "quit":
                self.running = False
                return
            elif ev == "color":
                self.toggle_xray()

    def _activate_title(self) -> None:
        item = TITLE_MENU[self.menu_index][0]
        if item == "QUIT":
            self.running = False
        elif item == "STORY":
            self._start_run("story")
        elif item == "SPEEDRUN":
            self._start_run("speedrun")
        elif item == "QUANTUM LAB":
            self._open_title_lab()
        elif item == "RECORDS":
            self.return_state = "title"
            self.state = "records"
        elif item == "CONTROLS":
            self.return_state = "title"
            self.state = "controls"

    def _start_run(self, mode: str) -> None:
        seed = self.seed
        if seed is None:
            seed = random.SystemRandom().randrange(1, 1 << 30)
        self.run = Run(mode=mode, seed=seed, lives=3 if mode == "story" else 3)
        self.run_pb_before = self.records.best_time() if mode == "speedrun" else None
        self._start_level(0)
        self.qualified = False
        self.submitted = False
        self.victory = False

    def _start_level(self, index: int) -> None:
        if not self.run:
            return
        self.run.level_index = index
        seed = None if self.run.seed is None else self.run.seed + index * 1009
        self.game = Game(self.run, index, seed=seed)
        self.state = "intro"
        self.intro_timer = 1.5 if self.run.speedrun else 1.9
        self.controller.release_all()

    def _open_title_lab(self) -> None:
        demo_run = Run(mode="story", seed=self.seed or 12345)
        self.lab_game = Game(demo_run, 0, seed=self.seed or 12345)
        self.lab_game.oracle.tick(left=False, right=True, jump=False, sprint=False,
                                 dash=False, speed=0.0, qflux=100, level=0)
        self.lab_message = ""
        self.return_state = "title"
        self.state = "lab"

    # ------------------------------------------------------------------
    def _events_play(self, events: list[str], cols: int, rows: int, dt: float) -> None:
        if not self.game:
            self.state = "title"
            return
        feed: list[str] = []
        for ev in events:
            if ev in ("pause", "quit"):
                self.controller.release_all()
                self.pause_index = 0
                self.state = "pause"
                return
            if ev == "lab":
                self.controller.release_all()
                self.lab_game = self.game
                self.lab_message = ""
                self.return_state = "play"
                self.state = "lab"
                return
            if ev == "color":
                self.toggle_xray()
                self.toast_text = "RENDER: X-RAY" if self.scene.xray else "RENDER: CLASSIC"
                self.toast_timer = 1.1
            elif ev == "help":
                self.controller.release_all()
                self.return_state = "play"
                self.state = "controls"
                return
            elif ev == "mute":
                self.toast_text = "THIS TERMINAL HAS NO SOUND CARD"
                self.toast_timer = 1.4
            else:
                feed.append(ev)
        if feed:
            self.controller.feed(feed)
        layout = compute_layout(cols, rows)
        self.game.set_view(layout.view_w, layout.view_h)
        self.accum += dt
        steps = 0
        controls: Controls | None = None
        while self.accum >= STEP and steps < 4 and self.state == "play":
            if controls is None:
                controls = self.controller.snapshot()
            evs = self.game.step(STEP, controls)
            self.accum -= STEP
            steps += 1
            if self._game_events(evs):
                return
        if steps == 0:
            # Keep the edge flag alive until a simulation step consumes it.
            pass

    def _game_events(self, events: list[str]) -> bool:
        """Returns True if the app state changed."""
        if not self.game or not self.run:
            return True
        for ev in events:
            if ev == "clear":
                self.state = "clear"
                self.clear_timer = 2.2 if self.run.speedrun else 3.0
                self.controller.release_all()
                return True
            if ev == "game_over":
                self._finish(story_victory=False)
                return True
            if ev == "retry":
                self.toast_text = "COLLAPSED - RETRYING"
                self.toast_timer = 1.0
            elif ev == "respawn":
                self.toast_text = "LIFE LOST - CHECKPOINT RESTORED"
                self.toast_timer = 1.4
            elif ev == "boss_down":
                self.toast_text = "BOSS PHASE COLLAPSED - GATE OPEN"
                self.toast_timer = 1.8
            elif ev == "checkpoint":
                self.toast_text = "CHECKPOINT ENTANGLED"
                self.toast_timer = 1.3
            elif ev == "hurt":
                self.toast_text = "DECOHERENCE"
                self.toast_timer = 0.7
        return False

    def _advance_clear(self) -> None:
        if not self.run or not self.game:
            self.state = "title"
            return
        if self.run.level_index < 4:
            self._start_level(self.run.level_index + 1)
        else:
            self._finish(story_victory=True)

    def _finish(self, *, story_victory: bool) -> None:
        if not self.run or not self.game:
            self.state = "title"
            return
        self.victory = story_victory or (self.run.speedrun and self.run.level_index >= 4)
        self.qualified = False
        self.submitted = False
        self.pending = None
        if self.run.speedrun:
            if self.victory:
                self.qualified = self.records.qualifies_speedrun(self.run.run_time)
                self.pending = {"kind": "run"}
        else:
            self.qualified = self.records.qualifies_score(self.run.score)
            self.pending = {"kind": "score"}
        if self.qualified:
            self.name_buffer = ""
            self.state = "name"
        else:
            self.state = "results"

    # ------------------------------------------------------------------
    def _events_pause(self, events: list[str]) -> None:
        for ev in events:
            if ev in ("up", "nav_up", "ch:w"):
                self.pause_index = (self.pause_index - 1) % len(PAUSE_MENU)
            elif ev in ("down", "nav_down", "ch:s"):
                self.pause_index = (self.pause_index + 1) % len(PAUSE_MENU)
            elif ev in ("pause", "enter"):
                self._pause_action()
                return
            elif ev == "lab":
                self._open_lab_from("pause")
                return
            elif ev == "color":
                self.toggle_xray()
            elif ev == "quit":
                self._quit_to_title()
                return

    def _pause_action(self) -> None:
        item = PAUSE_MENU[self.pause_index]
        if item == "RESUME":
            self.state = "play"
            self.controller.release_all()
        elif item == "QUANTUM LAB":
            self._open_lab_from("pause")
        elif item == "RECORDS":
            self.return_state = "pause"
            self.state = "records"
        elif item == "RESTART LEVEL":
            if self.game:
                self.game.restart_level(use_checkpoint=True)
                self.accum = 0.0
                self.state = "play"
                self.controller.release_all()
        elif item == "QUIT TO TITLE":
            self._quit_to_title()

    def _open_lab_from(self, from_state: str) -> None:
        if not self.game:
            return
        self.lab_game = self.game
        self.return_state = from_state
        self.lab_message = ""
        self.state = "lab"

    def _quit_to_title(self) -> None:
        self.state = "title"
        self.game = None
        self.run = None
        self.menu_index = 0
        self.controller.release_all()

    def _events_lab(self, events: list[str]) -> None:
        exported = False
        for ev in events:
            if ev in ("lab", "pause", "enter"):
                self.state = self.return_state
                if self.state == "play":
                    self.controller.release_all()
                return
            if ev == "color":
                self.toggle_xray()
            elif ev == "help":
                self.state = "lab_help"
                return
            elif ev == "quit":
                self.state = "title" if self.return_state == "title" else self.return_state
                return
            elif ev in ("ch:x", "sprint") and not exported:
                self._export_qasm()
                exported = True

    def _export_qasm(self) -> None:
        game = self.lab_game or self.game
        if not game:
            return
        path = Path.cwd() / "frame.qasm"
        try:
            path.write_text(game.oracle.qasm(), encoding="utf-8")
            self.lab_message = f"SAVED {path}"
        except OSError as exc:
            self.lab_message = f"COULD NOT SAVE: {exc}"
        self.lab_message_timer = 3.0

    # ------------------------------------------------------------------
    def _events_name(self, events: list[str]) -> None:
        for ev in events:
            if ev == "enter":
                self._submit_name()
                return
            if ev == "backspace":
                self.name_buffer = self.name_buffer[:-1]
            elif ev.startswith("ch:"):
                ch = ev[3:]
                if ch.isalnum() and len(self.name_buffer) < 3:
                    self.name_buffer += ch.upper()
            elif ev == "pause":
                # Escape is deliberately not a cancel here; use backspace.
                pass

    def _submit_name(self) -> None:
        name = self.name_buffer or "AAA"
        if not self.run or not self.pending:
            self.state = "results"
            return
        if self.pending["kind"] == "score":
            level = self.game.level.key if self.game else "1-1"
            self.records.add_score(name, self.run.score, level, self.run.coins,
                                   self.run.mode, self.run.run_time)
        else:
            self.records.add_speedrun(name, self.run.run_time, self.run.deaths,
                                      self.run.splits)
        self.submitted = True
        self.state = "results"

    # ------------------------------------------------------------------
    def _render(self, cols: int, rows: int, dt: float) -> CellCanvas:
        if self.state == "title":
            return self.screens.title(cols, rows, self.records, self.menu_index, self.t,
                                      self.scene.xray)
        if self.state == "records":
            return self.screens.records(cols, rows, self.records, self.t, self.scene.xray)
        if self.state == "controls":
            return self.screens.controls(cols, rows, self.t)
        if self.state == "results":
            game = self.game
            run = self.run
            if not game or not run:
                return self.screens.title(cols, rows, self.records, 0, self.t)
            hint = "ENTER: RETURN TO TITLE"
            return self.screens.results(cols, rows, self.records, run, game, self.t,
                                        self.victory, self.qualified or self.submitted,
                                        hint)
        if self.state == "name":
            if not self.run:
                return self.screens.name_entry(cols, rows, self.name_buffer, 0, None, self.t)
            timev = self.run.run_time if self.run.speedrun else None
            rank = ("TOP FIVE TIME" if self.run.speedrun else "TOP FIVE SCORE") if self.qualified else ""
            return self.screens.name_entry(cols, rows, self.name_buffer,
                                           self.run.score, timev, self.t, rank)
        if self.state == "clear":
            if not self.game or not self.run:
                return self.screens.title(cols, rows, self.records, 0, self.t)
            return self.screens.level_clear(cols, rows, self.game, self.t,
                                            self.run.level_index + 1, 5,
                                            self.run_pb_before, self.run.speedrun)
        if self.state == "lab_help":
            return self.screens.lab_help(cols, rows, self.t, self.scene.xray)
        # everything below needs a game
        game = self.game
        if self.state == "lab":
            game = self.lab_game or self.game
            if not game:
                return self.screens.title(cols, rows, self.records, 0, self.t)
        if not game:
            return self.screens.title(cols, rows, self.records, self.menu_index, self.t)
        layout = compute_layout(cols, rows)
        game.set_view(layout.view_w, layout.view_h)
        self.scene.high_score = self.records.best_score()
        base = self.scene.render(game, cols, rows)
        if self.state == "intro":
            return self.screens.intro(base, cols, rows, game, self.t)
        if self.state == "pause":
            return self.screens.pause(base, cols, rows, game, self.pause_index, self.t)
        if self.state == "lab":
            return self.screens.lab(base, cols, rows, game, self.t, self.lab_message)
        return base

    # ------------------------------------------------------------------
    def _too_small(self, cols: int, rows: int) -> CellCanvas:
        cells = CellCanvas(max(1, cols), max(1, rows), INK, BG)
        msg = "QUANTOMARIO"
        cells.text(max(0, (cols - len(msg)) // 2), max(1, rows // 2 - 3), msg, ACCENT, BG)
        msg2 = "TERMINAL TOO SMALL"
        if len(msg2) <= cols:
            cells.text(max(0, (cols - len(msg2)) // 2), max(1, rows // 2 - 1), msg2, HAZARD, BG)
        msg3 = f"NEED 40 x 16 / HAVE {cols} x {rows}"
        if len(msg3) <= cols:
            cells.text(max(0, (cols - len(msg3)) // 2), max(1, rows // 2 + 1), msg3, DIM, BG)
        msg4 = "RESIZE WINDOW OR PRESS Q"
        if len(msg4) <= cols:
            cells.text(max(0, (cols - len(msg4)) // 2), max(1, rows // 2 + 3), msg4, FAINT, BG)
        return cells


def make_demo_cells(level: int = 0, cols: int = 120, rows: int = 40,
                    steps: int = 0) -> CellCanvas:
    from .scores import Records
    records = Records()
    app = App(records)
    run = Run(seed=42)
    game = Game(run, level, seed=42)
    game.set_view(*_view_for(cols, rows))
    for _ in range(steps):
        game.step(STEP, Controls(right=True, jump_pressed=(_ % 30 == 0)))
    return app.scene.render(game, cols, rows)


def _view_for(cols: int, rows: int) -> tuple[float, float]:
    from .view import compute_layout
    L = compute_layout(cols, rows)
    return L.view_w, L.view_h
