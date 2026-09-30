# The Quantum System in QuantoMario

This document explains what the quantum part of QuantoMario actually does:
what is simulated, how the circuit is built, what the measurement returns, and
which parts of the game consume the results.

For the short player-facing version, see the "Quantum scope" section of the
[README](../README.md). For the implementation, start at
[`quantomario/quantum.py`](../quantomario/quantum.py).

## Short version

Every gameplay step, QuantoMario:

1. Encodes the current controls, speed, flux, and level into 14 qubits.
2. Applies a circuit of about 40 gates.
3. Evolves a 16,384-entry complex state vector.
4. Measures the register once.
5. Feeds selected measured bits into enemy behavior, `?` block rewards, and
   visual decoherence.

The platformer physics are deliberately classical. Gravity, collision response,
jumping, scrolling, and the base movement rules are ordinary game code. The
register supplies contextual parameters to those rules, such as enemy mood and
block rewards. It is not a quantum-physics engine for the platformer.

## What is and is not happening

| Claim | Reality |
| --- | --- |
| Real state-vector simulation | Yes. Complex amplitudes, unitary gates, entanglement, interference, and Born-rule sampling. |
| Quantum hardware | No. Everything runs locally in NumPy on a classical CPU. |
| Noise, decoherence, error correction | No. It is an ideal, noiseless pure-state simulator. |
| A quantum algorithm with a purpose | No. The circuit is authored for game outcomes and presentation. |
| Quantum platformer physics | No. Mario's motion and collisions are deterministic classical code. |
| Random numbers with quantum labels | No. Measurement probabilities come from the evolved state vector and depend on inputs, frame, and level. |
| Persistent coherence across frames | No. Each frame starts from `|00...0>`, is measured, and is re-prepared on the next tick. |

The accurate description is: **a real classical simulation of a small quantum
circuit, embedded in a platformer, used as a contextual outcome generator and
visual instrument.**

## Where the code lives

| File | Responsibility |
| --- | --- |
| `quantomario/quantum.py` | Gate definitions, state-vector simulator, per-frame circuit builder (`QuantumOracle`), measurement result, OpenQASM export. |
| `quantomario/game.py` | Calls the oracle once per step and applies measured values to blocks, enemies, and effects. |
| `quantomario/view.py` | Uses measured entropy and echo for HUD readouts and decoherence visuals. |
| `quantomario/screens.py` | Renders the Quantum Lab and its help screen. |
| `quantomario/entities.py` | Holds the player `qflux` value and enemy `mood` fields. |
| `quantomario/main.py` | CLI demo, QASM dump, and quantum self-tests. |

The call flow is:

```text
Controls + speed + qflux + level
              |
              v
      QuantumOracle.tick()
              |
              v
   Circuit (38 to 43 gates)
              |
              v
    QuantumSimulator.run()
   (evolve 2^14 amplitudes,
    sample one basis state)
              |
              v
        QuantumResult
          |         |
          v         v
   Game outcomes   Quantum Lab
```

## The register

QuantoMario uses **14 qubits** and the simulator stores all **2^14 = 16,384**
complex amplitudes. Qubits are indexed little-endian: qubit `q` corresponds to
bit `q` of the basis-state index. The display bitstring reverses the measured
bits so it reads in the conventional most-significant-first order.

| Qubits | Internal label | Role |
| --- | --- | --- |
| `q0` | `L` | Left input |
| `q1` | `R` | Right input |
| `q2` | `JMP` | Jump held or pressed |
| `q3` | `RUN` | Sprint toggle |
| `q4` | `FLX` | Dash active or dash pressed |
| `q5`-`q7` | `P0`-`P2` | Phase register coupled to movement and input |
| `q8`-`q11` | `E0`-`E3` | Entropy register, prepared in superposition |
| `q12` | `COIN` | Reward / `?` block measurement |
| `q13` | `ECHO` | Echo flag for decoherence effects |

These names are labels for game roles, not a standard quantum-computing
register layout.

## One frame, stage by stage

`QuantumOracle.tick()` builds a fresh `Circuit` every gameplay step. The circuit
has a fixed skeleton and a variable number of input gates:

| Stage | Gates | Purpose |
| --- | --- | --- |
| 1. Input load | 0-5 | Flip input qubits with `X` for held or pressed controls. |
| 2. Entropy preparation | 4 | Put `q8`-`q11` into a uniform superposition with `H`. |
| 3. Phase coupling | 9 | Mix controls and momentum into `q5`-`q7`. |
| 4. Phase/entropy entanglement | 13 | Correlate the entropy register with movement and input. |
| 5. Reward oracle | 5 | Bias `q12`, the `?` block reward bit. |
| 6. Echo flag | 5 | Correlate `q13` with entropy and reward. |
| 7. Drift | 2 | Add final phase rotations to the circuit. |

The total is **38 to 43 gates**, depending on how many inputs are active in the
frame. A typical frame is around 40 gates, which is what the HUD and README
report.

### 1. Input load

The oracle receives the same controls the platformer uses:

- `left` -> `X q0`
- `right` -> `X q1`
- jump held or jump pressed -> `X q2`
- sprint toggle -> `X q3`
- dash active or dash pressed -> `X q4`

`X` flips a qubit, so each of these qubits starts as `|0>` or `|1>` depending on
the player's input. If both left and right are held, both `q0` and `q1` are set;
a later Toffoli detects that combination.

### 2. Entropy preparation

Four Hadamard gates put `q8`-`q11` into a uniform superposition of all 16
four-bit values. This is the source of the "entropy" name. The next stage
entangles this register with the player's state, so the measured value is not
just an independent random number.

### 3. Phase coupling

The input bits are copied into the phase register, then rotated:

```text
CNOT q0 -> q5          CNOT q1 -> q6          CNOT q2 -> q7
RY   q5  (frame, level) RY q6 (frame)          RZ q7 (frame, speed)
CNOT q3 -> q5          CNOT q4 -> q6           CCX q0, q1 -> q7
```

The rotation angles vary with the frame counter; `q5` also uses the level and
`q7` uses the player's horizontal speed:

```text
phi = sin(frame * 0.071) * 0.8 + speed / 340
```

A Toffoli on `q0`, `q1`, and `q7` marks the case where both directions are held.
The result is a phase register whose amplitudes depend on what the player is
doing.

### 4. Phase/entropy entanglement

The phase register is then coupled into the entropy register:

```text
CNOT q5 -> q8    CNOT q6 -> q9    CNOT q7 -> q10    CNOT q4 -> q11
RZ   q8          H    q8          S    q10          T    q11
CNOT q8 -> q11   H    q9          CNOT q9 -> q10    CZ q10, q11
H    q11
```

This is the part that makes the measured entropy contextual rather than flat.
The qubits are correlated with input and momentum, and the phase gates (`S`,
`T`, `RZ`, `CZ`) create interference. Different player states produce different
probability distributions over the 16 entropy values.

### 5. Reward oracle

The reward bit `q12` is prepared with a slowly changing bias and then coupled to
the entropy register and the player's remaining flux:

```text
RY   q12  (frame, level)     CNOT q11 -> q12
RZ   q12  (qflux)            CNOT q10 -> q12
RY   q12  (-0.28)
```

The `RZ` angle includes `qflux`:

```text
0.4 + qflux * 0.01
```

As a result, the probability that `q12` measures as `1` changes with the frame,
level, entropy state, and available dash flux. That measured bit becomes the
`?` block reward for the frame.

### 6. Echo flag

The echo bit is correlated with entropy and reward:

```text
CNOT q9 -> q13    CNOT q12 -> q13    H q13    T q13    H q13
```

`q13` is used only for presentation, but it is entangled with the rest of the
circuit, so its measurement is not an independent coin flip.

### 7. Drift

Two small `RZ` rotations on `q5` and `q9` add per-frame phase drift at the end of
the circuit:

```text
RZ q5 (sin(frame * 0.021) * 0.3)
RZ q9 (cos(frame * 0.019) * 0.3)
```

## Simulation and measurement

`QuantumSimulator` starts every run from `|00...0>`, applies the circuit, and
computes:

```text
P(basis state i) = |amplitude[i]|^2
```

It then samples exactly one basis state from that distribution. This is the
measurement. Afterward the state vector is collapsed to the sampled basis state.
Because the next tick calls `_prepare()` again, the collapse has no lasting
effect on later frames; it mainly keeps the implementation faithful to a
measure/loop model.

The sampling uses `numpy.random.default_rng(seed)`. A run seed therefore makes
the measurement sequence reproducible for the same inputs, but normal play
changes the controls and frame counter, so probabilities and outcomes change.

The full result object contains:

| Field | Meaning |
| --- | --- |
| `bits` | The 14 measured bits, indexed `q0` to `q13`. |
| `entropy` | Four-bit integer from `q8`-`q11` (`q8` is the low bit), range 0-15. |
| `reward` | Measured `q12`, either 0 or 1. |
| `echo` | Measured `q13`, either 0 or 1. |
| `phase` | Three-bit integer from `q5`-`q7`, range 0-7. Currently informational only. |
| `marginals` | `P(q = 1)` for each qubit, computed from the pre-measurement distribution. |
| `probabilities` | All 16,384 Born-rule probabilities. |
| `gate_count` | Number of gates in the frame circuit. |
| `depth` | Greedy ASAP circuit depth in layers. |
| `sample_time_ms` | Wall-clock time to execute the state-vector simulation. |
| `frame` | Running frame counter for the oracle. |

In addition, `QuantumOracle.last_shots` keeps 96 basis-state samples drawn from
the same probability distribution for the lab histogram. The 96 lab shots are
**not** 96 circuit executions; they are samples drawn from the already-computed
distribution.

## What the measured bits change in the game

Only three measured values are consumed by the game. The rest are visible in the
HUD or lab.

| Output | Consumer | Effect |
| --- | --- | --- |
| `reward` (`q12`) | `Game.hit_block()` | A `?` block gives a mushroom when the bit is 1, otherwise a coin and 200 points. |
| `entropy` (`q8`-`q11`) | `Game._quantum_tick()` | Selects each enemy's mood and pacing. |
| `echo` (`q13`) | `Game._update_effects()` and `view.py` | Adds decoherence sparkles, star accents, and a scanline in The Observable. |
| `entropy` low bit | `view.py` | Adds the decoherence scanline in The Observable and accents some stars. |
| `entropy`, gates, depth | HUD | Shows gate count and depth, plus the ENT value on the large HUD. |
| `marginals`, `last_shots` | Quantum Lab | Marginal bars and 96-shot histogram. |
| `phase` (`q5`-`q7`) | Nothing currently | Computed and exposed, but not read by gameplay or rendering. |

### `?` block rewards

When Mario hits a `?` block, `hit_block()` checks `last_reward`:

- `1` -> spawn a mushroom.
- `0` -> award 200 points and one coin.

This is the clearest direct gameplay consequence of a measurement. The block is
then replaced with a spent `X` tile, so the decision happens once per block.

### Enemy moods and pacing

Every frame, `_quantum_tick()` assigns each enemy a mood:

```text
mood   = (entropy >> (enemy.index % 4)) & 3
mood_t = 0.24 + 0.14 * ((entropy >> ((enemy.index + 1) % 4)) & 3)
```

The measured 4-bit entropy value therefore spreads across enemies. `mood` is in
the range 0-3 and changes behavior:

- Ground enemies (goombas and koopas):
  - mood 1: speed multiplied by `0.28` (slow).
  - mood 2: speed multiplied by `1.35` (fast).
  - moods 0 and 3: normal speed.
- Flyers: mood 1 adds a small horizontal drift on top of their sine motion.
- Boss:
  - mood 1 reduces horizontal speed from 38 to 12.
  - `entropy & 3` sets the jump cooldown: `2.0 + (entropy & 3) * 0.12`.
  - `entropy & 1` sets the fireball cooldown: `1.35 + (entropy & 1) * 0.35`.
- Rendering: a mood-2 goomba or koopa gets an accent dot; a mood-1 goomba gets
  a dim dot.

`mood_t` is currently maintained and decremented, but no behavior or rendering
code reads it. It is effectively a spare output from the second entropy nibble.

### Echo and decoherence visuals

`echo` does not alter movement or collisions. When it is 1:

- `Game._update_effects()` occasionally emits an extra particle near Mario.
- `view.py` adds accent stars and, in The Observable, a short horizontal
  scanline.
- The measured bit appears in the lab's `M` column for `q13`.

The player's dash afterimages are separate: they are triggered by dash time or
invulnerability, not by the echo bit.

### What the quantum part does not change

- Gravity, jumping, acceleration, collision resolution, and camera motion are
  classical and deterministic.
- Coins are fixed level placements. Collecting one member of an "entangled"
  coin pair also collects its partner, but that is a scripted level mechanic,
  not a measurement.
- The quantum dash is a normal dash move: it costs 40 flux, lasts 0.22 seconds,
  makes Mario briefly invulnerable, and damages enemies on contact. The dash
  flag enters the circuit as `q4`, but the dash itself is not a quantum
  measurement.
- The player's displayed quantum aura reflects remaining dash flux, not a
  qubit state.

## The Quantum Lab

The lab is a **read-only snapshot of the last simulated frame**, not a live loop.
Opening it pauses gameplay, so the oracle does not tick while the lab is open.
The frame number, measured bits, marginals, and histogram stay frozen until the
player returns to gameplay and reopens the lab. Opening it from the title screen
shows a generated demo frame.

The lab display includes:

- **Frame header** (space permitting): frame number, 14 qubits, gate count,
  circuit depth, and NumPy sample time.
- **Gate rows `q0`-`q13`**: as many recent circuit layers as the panel fits,
  with role labels and `●`/`⊕` markers for controlled gates.
- **`M` column**: the measured 0 or 1 for each qubit from the last sample.
- **`|psi>` bitstring** (wide terminals): the measured basis state,
  most-significant bit first.
- **Marginal P(1)** (wide terminals): bars for the reward, echo, and entropy
  qubits.
- **Entropy histogram** (wide terminals): 96 sampled shots grouped into 16 bins
  over the four entropy qubits.
- **OpenQASM pane** (tall terminals): the last frame's OpenQASM export.

Lab keys:

| Key | Action |
| --- | --- |
| `H` | Show the lab help screen. |
| `X` | Export the current frame to `frame.qasm` in the current directory. |
| `C` | Toggle x-ray / classic rendering. |
| `G`, `Esc`, or `Enter` | Return to play or the title screen. |

The lab help screen itself summarises the register roles and reiterates that
the platformer physics remain classical.

## OpenQASM export

`QuantumOracle.qasm()` writes the last built circuit as OpenQASM 2.0:

```text
// QuantoMario frame circuit
// frame 42, 41 gates, depth 20
OPENQASM 2.0;
include "qelib1.inc";
qreg q[14];
creg c[14];
...
measure q -> c;
```

Supported gate translations include `x`, `y`, `z`, `h`, `s`, `sdg`, `t`, `tdg`,
parameterised `rx`/`ry`/`rz`, `cx`, `cz`, `swap`, and `ccx`. The export ends
with one `measure q -> c;`. It is a description of the circuit, not a recording
of a hardware run.

Useful commands:

```sh
# Export one generated frame and print its stats.
python3 play.py --dump-qasm /tmp/frame.qasm

# Run the quantum and game self-tests.
python3 play.py --selftest
```

The self-test includes a Bell-pair state-vector check and an oracle/QASM check.

## Reproducibility, performance, and scaling

- **Seeding**: the `QuantumOracle` receives a NumPy PCG64 seed. When a run seed
  is present, each level derives its seed from the run seed plus the level
  index. A fixed seed plus identical controls and level reproduces the same
  measurement sequence.
- **Frame independence**: every tick prepares `|00...0>` from scratch. There is
  no carried-over coherence, drift, or calibration between frames.
- **Cost**: one circuit touches a 16,384-entry complex vector. The measured
  execution time is shown in the lab and the HUD status line, typically around
  1-2 ms on a normal laptop.
- **Memory**: the state vector alone is about 256 KiB at `complex128`, plus the
  probability array and result buffers.
- **Scaling**: cost grows as `2^n` in both memory and gate application time.
  Fourteen qubits is a deliberate limit chosen for real-time play. Raising the
  qubit count quickly becomes impractical for a frame-by-frame game loop.

## Common questions

### Is this really quantum?

It is a real numerical simulation of a quantum circuit, using complex state
vectors and the same measurement rule a quantum computer obeys. It is not
running on quantum hardware, and it does not include noise or decoherence.

### Does the quantum register decide whether Mario can jump or land?

No. Jumping, gravity, collisions, and movement are classical. The register
decides outcomes that are deliberately left contextual: a `?` block's contents,
enemy mood, and visual decoherence.

### Are the coins quantum?

No. The "entangled" coin pairs in levels are a scripted gameplay rule: collect
one, and its partner is collected too. The 14-qubit register does not simulate
those pairs.

### Why is the dash called a quantum dash?

It is a piece of game fiction. The dash consumes flux, grants brief
invulnerability, and damages enemies. Its active state is loaded into `q4` as an
input, but the dash's physics are ordinary game code.

### Why does the lab not animate?

Because it is an inspection screen. Gameplay pauses while the lab is open, so
no new circuits are built. This freeze-frame behaviour is intentional.

### Why 14 qubits?

Because `2^14 = 16,384` amplitudes is small enough to evolve at interactive
speeds in NumPy while still being a nontrivial entangled register. More qubits
would grow the state vector exponentially without adding gameplay value.

## Related files

- [`quantomario/quantum.py`](../quantomario/quantum.py) - simulator, circuits, oracle, QASM
- [`quantomario/game.py`](../quantomario/game.py) - quantum bridge and gameplay effects
- [`quantomario/screens.py`](../quantomario/screens.py) - lab and help rendering
- [`quantomario/view.py`](../quantomario/view.py) - HUD and decoherence visuals
- [`quantomario/main.py`](../quantomario/main.py) - CLI export and self-tests
