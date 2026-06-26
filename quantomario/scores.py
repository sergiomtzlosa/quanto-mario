"""Persistent top-five score and speedrun tables."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time


def _data_dir() -> Path:
    override = os.environ.get("QUANTOMARIO_HOME")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base).expanduser() / "quantomario"
    return Path.home() / ".local" / "share" / "quantomario"


class Records:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (_data_dir() / "records.json")
        self.scores: list[dict] = []
        self.speedruns: list[dict] = []
        self.render_mode = "xray"
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.scores = list(data.get("scores", []))[:40]
            self.speedruns = list(data.get("speedruns", []))[:40]
            self.render_mode = data.get("render_mode", "xray")
        except (OSError, ValueError, TypeError):
            self.scores = []
            self.speedruns = []
            self.render_mode = "xray"
        self._sort()

    def _sort(self) -> None:
        self.scores.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
        self.speedruns.sort(key=lambda x: float(x.get("time", 1e9)))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "scores": self.scores[:20],
            "speedruns": self.speedruns[:20],
            "render_mode": self.render_mode,
        }
        fd, tmp = tempfile.mkstemp(prefix=".records-", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=True)
            os.replace(tmp, self.path)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    # --- leaderboard logic -------------------------------------------
    def qualifies_score(self, score: int) -> bool:
        if score <= 0:
            return False
        if len(self.scores) < 5:
            return True
        return score > int(self.scores[4].get("score", 0))

    def qualifies_speedrun(self, seconds: float) -> bool:
        if seconds <= 0:
            return False
        if len(self.speedruns) < 5:
            return True
        return seconds < float(self.speedruns[4].get("time", 1e9))

    def add_score(self, name: str, score: int, level: str, coins: int,
                  mode: str, run_time: float) -> None:
        entry = {
            "name": clean_name(name),
            "score": int(score),
            "level": level,
            "coins": int(coins),
            "mode": mode,
            "time": round(float(run_time), 3),
            "date": time.strftime("%Y-%m-%d"),
        }
        self.scores.append(entry)
        self._sort()
        self.scores = self.scores[:20]
        self.save()

    def add_speedrun(self, name: str, seconds: float, deaths: int,
                     splits: list[float]) -> None:
        entry = {
            "name": clean_name(name),
            "time": round(float(seconds), 3),
            "deaths": int(deaths),
            "splits": [round(float(s), 3) for s in splits],
            "date": time.strftime("%Y-%m-%d"),
        }
        self.speedruns.append(entry)
        self._sort()
        self.speedruns = self.speedruns[:20]
        self.save()

    def best_score(self) -> int:
        return int(self.scores[0]["score"]) if self.scores else 0

    def best_time(self) -> float | None:
        return float(self.speedruns[0]["time"]) if self.speedruns else None

    def top_scores(self, n: int = 5) -> list[dict]:
        return self.scores[:n]

    def top_speedruns(self, n: int = 5) -> list[dict]:
        return self.speedruns[:n]

    def best_splits(self) -> list[float]:
        if not self.speedruns:
            return []
        best = self.speedruns[0]
        return [float(x) for x in best.get("splits", [])]


def clean_name(name: str) -> str:
    out = "".join(ch for ch in name.upper() if ch.isalnum())[:3]
    return out or "AAA"


def format_time(seconds: float, millis: bool = True) -> str:
    seconds = max(0.0, seconds)
    if millis:
        m = int(seconds // 60)
        s = int(seconds % 60)
        ms = int((seconds * 1000) % 1000)
        return f"{m}:{s:02d}.{ms:03d}"
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


def format_short_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    tenths = int((seconds * 10) % 10)
    return f"{m}:{s:02d}.{tenths}"
