"""A tiny, real state-vector quantum core for QuantoMario.

Inspired by Quandoom's loop: input qubits are prepared from the keyboard, a
circuit is applied to the whole register, and the register is measured.  The
measured bits drive the game (enemy phases, block rewards, quantum luck and
the visual decoherence field).  Fourteen qubits is small enough to simulate at
30 fps in NumPy, but it is a genuine complex state vector, not a random number
generator wearing a lab coat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import Iterable

import numpy as np

N_QUBITS = 14
DIM = 1 << N_QUBITS

QUBIT_NAMES = (
    "L", "R", "JMP", "RUN", "FLX",
    "P0", "P1", "P2",
    "E0", "E1", "E2", "E3",
    "COIN", "ECHO",
)

# Fixed 2x2 gates.  Rotations are built on demand.
_PAULI = {
    "x": np.array([[0, 1], [1, 0]], dtype=np.complex128),
    "y": np.array([[0, -1j], [1j, 0]], dtype=np.complex128),
    "z": np.array([[1, 0], [0, -1]], dtype=np.complex128),
    "h": np.array([[1, 1], [1, -1]], dtype=np.complex128) / math.sqrt(2),
    "s": np.array([[1, 0], [0, 1j]], dtype=np.complex128),
    "sdg": np.array([[1, 0], [0, -1j]], dtype=np.complex128),
    "t": np.array([[1, 0], [0, np.exp(1j * math.pi / 4)]], dtype=np.complex128),
    "tdg": np.array([[1, 0], [0, np.exp(-1j * math.pi / 4)]], dtype=np.complex128),
}


def _ry(theta: float) -> np.ndarray:
    c, s = math.cos(theta / 2.0), math.sin(theta / 2.0)
    return np.array([[c, -s], [s, c]], dtype=np.complex128)


def _rz(theta: float) -> np.ndarray:
    return np.array(
        [[np.exp(-0.5j * theta), 0], [0, np.exp(0.5j * theta)]],
        dtype=np.complex128,
    )


def _rx(theta: float) -> np.ndarray:
    c, s = math.cos(theta / 2.0), -1j * math.sin(theta / 2.0)
    return np.array([[c, s], [s, c]], dtype=np.complex128)


@dataclass(frozen=True)
class Gate:
    name: str
    qubits: tuple[int, ...]
    param: float | None = None
    label: str | None = None

    def symbol(self) -> str:
        if self.label:
            return self.label
        return {
            "cx": "X",
            "ccx": "X",
            "measure": "M",
            "rz": "Z",
            "ry": "Y",
            "rx": "X",
        }.get(self.name, self.name.upper())

    def qasm(self) -> str:
        target = self.qubits[-1] if self.qubits else 0
        if self.name in ("x", "y", "z", "h", "s", "sdg", "t", "tdg"):
            return f"{self.name} q[{target}];"
        if self.name in ("rx", "ry", "rz"):
            return f"{self.name}({self.param:.8f}) q[{target}];"
        if self.name == "cx":
            return f"cx q[{self.qubits[0]}],q[{self.qubits[1]}];"
        if self.name == "cz":
            return f"cz q[{self.qubits[0]}],q[{self.qubits[1]}];"
        if self.name == "swap":
            return f"swap q[{self.qubits[0]}],q[{self.qubits[1]}];"
        if self.name == "ccx":
            return f"ccx q[{self.qubits[0]}],q[{self.qubits[1]}],q[{self.qubits[2]}];"
        if self.name == "measure":
            return "measure q -> c;"
        return f"// unsupported gate {self.name}"


@dataclass
class QuantumResult:
    bits: list[int]
    entropy: int
    reward: int
    echo: int
    phase: int
    marginals: list[float]
    probabilities: np.ndarray = field(repr=False)
    sample_time_ms: float = 0.0
    gate_count: int = 0
    depth: int = 0
    frame: int = 0

    @property
    def bitstring(self) -> str:
        return "".join(str(b) for b in self.bits[::-1])


class Circuit:
    """Ordered gate list plus a small scheduling helper for diagrams."""

    def __init__(self) -> None:
        self.gates: list[Gate] = []

    def add(self, name: str, *qubits: int, param: float | None = None,
            label: str | None = None) -> "Circuit":
        for q in qubits:
            if not 0 <= q < N_QUBITS:
                raise ValueError(f"qubit {q} out of range")
        self.gates.append(Gate(name, tuple(qubits), param, label))
        return self

    def x(self, q: int) -> "Circuit":
        return self.add("x", q)

    def h(self, q: int) -> "Circuit":
        return self.add("h", q)

    def cx(self, c: int, t: int) -> "Circuit":
        return self.add("cx", c, t)

    def ccx(self, a: int, b: int, t: int) -> "Circuit":
        return self.add("ccx", a, b, t)

    def rz(self, q: int, theta: float) -> "Circuit":
        return self.add("rz", q, param=theta)

    def ry(self, q: int, theta: float) -> "Circuit":
        return self.add("ry", q, param=theta)

    def rx(self, q: int, theta: float) -> "Circuit":
        return self.add("rx", q, param=theta)

    def __len__(self) -> int:
        return len(self.gates)

    def layers(self) -> list[list[Gate]]:
        """Greedy ASAP scheduling.  Used for depth and the in-game lab."""
        layers: list[list[Gate]] = []
        for gate in self.gates:
            if gate.name == "measure":
                break
            placed = False
            for layer in layers:
                used: set[int] = set()
                for g in layer:
                    used.update(g.qubits)
                if not used.intersection(gate.qubits):
                    layer.append(gate)
                    placed = True
                    break
            if not placed:
                layers.append([gate])
        return layers

    def depth(self) -> int:
        return len(self.layers())


class QuantumSimulator:
    """Dense state-vector simulator, little-endian qubit indexing."""

    def __init__(self, n: int = N_QUBITS, seed: int | None = None) -> None:
        self.n = n
        self.size = 1 << n
        self.rng = np.random.default_rng(seed)
        self.state = np.zeros(self.size, dtype=np.complex128)
        self.state[0] = 1.0
        self._prepare()

    def _prepare(self) -> None:
        self.state.fill(0)
        self.state[0] = 1.0

    def _apply_1q(self, u: np.ndarray, q: int) -> None:
        # Reshape to (high, bit, low); apply u to the middle axis.
        shape = (1 << (self.n - q - 1), 2, 1 << q)
        arr = self.state.reshape(shape)
        a = arr[:, 0, :].copy()
        b = arr[:, 1, :].copy()
        arr[:, 0, :] = u[0, 0] * a + u[0, 1] * b
        arr[:, 1, :] = u[1, 0] * a + u[1, 1] * b

    def _cnot(self, c: int, t: int) -> None:
        idx = np.arange(self.size)
        sel = ((idx >> c) & 1).astype(bool)
        idx0 = idx[sel & (((idx >> t) & 1) == 0)]
        idx1 = idx0 | (1 << t)
        tmp = self.state[idx0].copy()
        self.state[idx0] = self.state[idx1]
        self.state[idx1] = tmp

    def _toffoli(self, a: int, b: int, t: int) -> None:
        idx = np.arange(self.size)
        sel = (((idx >> a) & 1) & ((idx >> b) & 1)).astype(bool)
        idx0 = idx[sel & (((idx >> t) & 1) == 0)]
        idx1 = idx0 | (1 << t)
        tmp = self.state[idx0].copy()
        self.state[idx0] = self.state[idx1]
        self.state[idx1] = tmp

    def apply(self, gate: Gate) -> None:
        name, qs = gate.name, gate.qubits
        if name in _PAULI:
            self._apply_1q(_PAULI[name], qs[0])
        elif name == "rz":
            self._apply_1q(_rz(gate.param or 0.0), qs[0])
        elif name == "ry":
            self._apply_1q(_ry(gate.param or 0.0), qs[0])
        elif name == "rx":
            self._apply_1q(_rx(gate.param or 0.0), qs[0])
        elif name == "cx":
            self._cnot(qs[0], qs[1])
        elif name == "cz":
            idx = np.arange(self.size)
            mask = (((idx >> qs[0]) & 1) & ((idx >> qs[1]) & 1)).astype(bool)
            self.state[mask] *= -1
        elif name == "swap":
            self._cnot(qs[0], qs[1])
            self._cnot(qs[1], qs[0])
            self._cnot(qs[0], qs[1])
        elif name == "ccx":
            self._toffoli(qs[0], qs[1], qs[2])
        elif name == "measure":
            return
        else:  # pragma: no cover - guards future mistakes
            raise ValueError(f"unknown gate {name}")

    def run(self, circuit: Circuit) -> tuple[int, np.ndarray, float]:
        start = time.perf_counter()
        self._prepare()
        for gate in circuit.gates:
            if gate.name == "measure":
                break
            self.apply(gate)
        probs = np.abs(self.state) ** 2
        total = float(probs.sum())
        if total <= 0:
            probs = np.full(self.size, 1.0 / self.size)
            self.state[:] = 1 / math.sqrt(self.size)
        else:
            probs = probs / total
        sample = int(self.rng.choice(self.size, p=probs))
        dt = (time.perf_counter() - start) * 1000.0
        # Collapse (not strictly needed for a fresh circuit, but faithful to
        # the Quandoom loop and useful if we ever keep coherence across frames).
        self.state.fill(0)
        self.state[sample] = 1.0
        return sample, probs, dt


def marginal_probabilities(probs: np.ndarray, n: int = N_QUBITS) -> list[float]:
    idx = np.arange(probs.size)
    return [float(probs[((idx >> q) & 1).astype(bool)].sum()) for q in range(n)]


def sample_shots(probs: np.ndarray, shots: int, rng: np.random.Generator,
                 n: int = N_QUBITS) -> list[int]:
    return rng.choice(probs.size, size=shots, p=probs).tolist()


class QuantumOracle:
    """Builds and runs the once-per-frame gateware for the game."""

    def __init__(self, seed: int | None = None) -> None:
        self.sim = QuantumSimulator(N_QUBITS, seed=seed)
        self.seed = seed
        self.frame = 0
        self.last_circuit = Circuit()
        self.last_result: QuantumResult | None = None
        self.last_shots: list[int] = []
        self.gate_history: list[int] = []

    def tick(self, *, left: bool, right: bool, jump: bool, sprint: bool,
             dash: bool, speed: float, qflux: int, level: int) -> QuantumResult:
        self.frame += 1
        f = self.frame
        c = Circuit()
        # 1. Keyboard -> input qubits.  This is Quandoom's input stage.
        if left:
            c.x(0)
        if right:
            c.x(1)
        if jump:
            c.x(2)
        if sprint:
            c.x(3)
        if dash:
            c.x(4)

        # 2. Entropy register: a fresh uniform superposition every frame.
        for q in range(8, 12):
            c.h(q)

        # 3. Couple the player's momentum into the phase register.
        c.cx(0, 5)
        c.cx(1, 6)
        c.cx(2, 7)
        phi = math.sin(f * 0.071) * 0.8 + speed / 340.0
        c.ry(5, 0.45 + 0.35 * math.sin(f * 0.11 + level))
        c.ry(6, 0.45 + 0.35 * math.cos(f * 0.09))
        c.rz(7, phi)
        c.cx(3, 5)
        c.cx(4, 6)
        c.ccx(0, 1, 7)

        # 4. Entangle phase <-> entropy.  Reversibility, like Quandoom.
        c.cx(5, 8)
        c.cx(6, 9)
        c.cx(7, 10)
        c.cx(4, 11)
        c.rz(8, 0.35 + 0.2 * math.sin(f * 0.037 + level))
        c.h(8)
        c.add("s", 10)
        c.add("t", 11)
        c.cx(8, 11)
        c.h(9)
        c.cx(9, 10)
        c.add("cz", 10, 11)
        c.h(11)

        # 5. Reward oracle (quantum ? blocks / mushroom rolls).  RY biases
        #    the coin qubit; entanglement makes the collapse contextual.
        c.ry(12, 0.85 + 0.25 * math.sin(f * 0.023 + level * 1.7))
        c.cx(11, 12)
        c.rz(12, 0.4 + qflux * 0.01)
        c.cx(10, 12)
        c.ry(12, -0.28)

        # 6. Echo flag.  Controls ghost trails and decoherence sparkle.
        c.cx(9, 13)
        c.cx(12, 13)
        c.h(13)
        c.add("t", 13)
        c.h(13)

        # Small drift so the live diagram never looks frozen.
        c.rz(5, math.sin(f * 0.021) * 0.3)
        c.rz(9, math.cos(f * 0.019) * 0.3)

        sample, probs, dt = self.sim.run(c)
        bits = [(sample >> q) & 1 for q in range(N_QUBITS)]
        entropy = sum(bits[8 + i] << i for i in range(4))
        result = QuantumResult(
            bits=bits,
            entropy=entropy,
            reward=bits[12],
            echo=bits[13],
            phase=sum(bits[5 + i] << i for i in range(3)),
            marginals=marginal_probabilities(probs),
            probabilities=probs,
            sample_time_ms=dt,
            gate_count=len(c),
            depth=c.depth(),
            frame=f,
        )
        self.last_circuit = c
        self.last_result = result
        self.last_shots = sample_shots(probs, 96, self.sim.rng)
        self.gate_history.append(len(c))
        if len(self.gate_history) > 180:
            self.gate_history.pop(0)
        return result

    def qasm(self) -> str:
        c = self.last_circuit
        lines = [
            "// QuantoMario frame circuit",
            f"// frame {self.frame}, {len(c)} gates, depth {c.depth()}",
            "OPENQASM 2.0;",
            'include "qelib1.inc";',
            f"qreg q[{N_QUBITS}];",
            "creg c[14];",
        ]
        lines.extend(g.qasm() for g in c.gates)
        lines.append("measure q -> c;")
        return "\n".join(lines) + "\n"

    def marginal(self, qubit: int) -> float:
        if not self.last_result:
            return 0.0
        return self.last_result.marginals[qubit]

    def histogram(self, mask_qubits: Iterable[int]) -> dict[int, int]:
        qs = list(mask_qubits)
        hist: dict[int, int] = {}
        for sample in self.last_shots:
            v = 0
            for i, q in enumerate(qs):
                v |= ((sample >> q) & 1) << i
            hist[v] = hist.get(v, 0) + 1
        return hist
