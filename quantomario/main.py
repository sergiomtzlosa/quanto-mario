"""Command line entry point for QuantoMario."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .app import App, make_demo_cells
from .entities import Controls, Run
from .game import Game
from .levels import level_defs
from .quantum import Circuit, N_QUBITS, QuantumOracle, QuantumSimulator
from .render import ColorEncoder
from .scores import Records, format_time
from .sprites import validate_sprites
from .view import compute_layout


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="quantomario",
        description="A Quandoom-inspired quantum Super Mario platformer for the terminal.",
    )
    p.add_argument("--seed", type=int, default=None, help="Deterministic run seed")
    p.add_argument("--color", choices=("auto", "truecolor", "256", "16"),
                   default="auto", help="Terminal colour depth")
    p.add_argument("--fps", type=int, default=30, help="Render frame rate (10-60)")
    p.add_argument("--classic", action="store_true", help="Start in classic colours")
    p.add_argument("--xray", action="store_true", help="Start in Quandoom x-ray scan mode")
    p.add_argument("--records", type=Path, default=None, help="Path to records.json")
    p.add_argument("--demo", action="store_true", help="Render one demo frame and exit")
    p.add_argument("--demo-level", type=int, default=0, help="0-4")
    p.add_argument("--demo-steps", type=int, default=30)
    p.add_argument("--demo-size", default="120x40", help="COLSxROWS")
    p.add_argument("--no-ansi", action="store_true", help="With --demo, emit plain glyphs")
    p.add_argument("--dump-qasm", type=Path, default=None,
                   help="Write one frame of OpenQASM and exit")
    p.add_argument("--levels", action="store_true", help="List worlds and exit")
    p.add_argument("--selftest", action="store_true", help="Run non-interactive checks")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.selftest:
        return selftest()
    if args.levels:
        for i, d in enumerate(level_defs()):
            print(f"{i + 1}. {d.world:10s} {d.name:28s} par {d.par:5.0f}s  "
                  f"{len(d.rows[0]):3d} tiles")
        return 0
    if args.dump_qasm:
        oracle = QuantumOracle(seed=args.seed)
        oracle.tick(left=False, right=True, jump=True, sprint=False, dash=False,
                    speed=42.0, qflux=80, level=0)
        args.dump_qasm.parent.mkdir(parents=True, exist_ok=True) if args.dump_qasm.parent != Path('.') else None
        args.dump_qasm.write_text(oracle.qasm(), encoding="utf-8")
        q = oracle.last_result
        print(f"Wrote {args.dump_qasm}  ({q.gate_count} gates, depth {q.depth}, "
              f"{q.sample_time_ms:.2f} ms)")
        return 0
    records = Records(args.records)
    if args.demo:
        try:
            cols, rows = (int(x) for x in args.demo_size.lower().split("x", 1))
        except ValueError:
            print("--demo-size must look like 120x40", file=sys.stderr)
            return 2
        cells = make_demo_cells(args.demo_level, cols, rows, args.demo_steps)
        if args.no_ansi:
            for row in cells.cells:
                print("".join(c.ch for c in row))
        else:
            sys.stdout.write(ColorEncoder(args.color).encode(cells) + "\n")
        return 0
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("QuantoMario needs an interactive terminal (TTY).", file=sys.stderr)
        print("Try: python3 play.py", file=sys.stderr)
        print("Or:  python3 play.py --demo --no-ansi", file=sys.stderr)
        return 2
    xray = True
    if args.classic:
        xray = False
    elif args.xray:
        xray = True
    else:
        xray = records.render_mode != "classic"
    app = App(records, seed=args.seed, color_mode=args.color, fps=args.fps, xray=xray)
    try:
        app.run_loop()
    except KeyboardInterrupt:
        return 130
    finally:
        try:
            records.save()
        except OSError:
            pass
    return 0


def selftest() -> int:
    failures: list[str] = []

    def check(name: str, fn) -> None:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"FAIL  {name}: {exc}")

    def quantum_bell() -> None:
        sim = QuantumSimulator(2, seed=3)
        c = Circuit().h(0).cx(0, 1)
        sample, probs, _ = sim.run(c)
        assert abs(probs[0] - 0.5) < 1e-9
        assert abs(probs[3] - 0.5) < 1e-9
        bits = [(sample >> i) & 1 for i in range(2)]
        assert bits[0] == bits[1]

    def oracle_qasm() -> None:
        o = QuantumOracle(seed=4)
        r = o.tick(left=True, right=False, jump=True, sprint=False, dash=False,
                   speed=20, qflux=100, level=1)
        assert len(r.bits) == N_QUBITS
        qasm = o.qasm()
        assert "OPENQASM 2.0;" in qasm and "measure q -> c;" in qasm
        assert len(o.last_circuit) >= 20
        assert o.last_circuit.depth() > 1

    def sprites() -> None:
        errors = validate_sprites()
        assert not errors, errors

    def levels_ok() -> None:
        levels = level_defs()
        assert len(levels) == 5
        for level in levels:
            widths = {len(r) for r in level.rows}
            assert len(widths) == 1, (level.key, widths)
            assert any("F" in row for row in level.rows), level.key
            assert len(level.rows) == 14

    def render_sizes() -> None:
        for cols, rows in ((40, 16), (80, 24), (120, 40), (200, 60)):
            cells = make_demo_cells(0, cols, rows, 5)
            assert len(cells.cells) == rows
            assert len(cells.cells[0]) == cols
            L = compute_layout(cols, rows)
            assert L.tile_px >= 4

    def physics() -> None:
        run = Run(seed=11)
        g = Game(run, 0, seed=11)
        g.set_view(128, 64)
        controls = Controls(right=True)
        for i in range(600):
            controls.jump_pressed = (i % 47 == 0)
            g.step(1 / 60, controls)
            controls.jump_pressed = False
        assert g.player.x > 30
        assert g.qresult is not None

    def timers() -> None:
        assert format_time(65.432) == "1:05.432"

    check("state-vector Bell pair", quantum_bell)
    check("quantum oracle + QASM", oracle_qasm)
    check("sprite rectangles", sprites)
    check("five level maps", levels_ok)
    check("responsive render sizes", render_sizes)
    check("physics smoke test", physics)
    check("score time formatting", timers)
    if failures:
        print(f"\n{len(failures)} FAILURE(S)")
        return 1
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
