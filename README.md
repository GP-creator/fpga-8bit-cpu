# 8-bit CPU in Verilog

A minimal 8-bit accumulator CPU (SAP-1 style, "Simple As Possible"), written in
plain Verilog and verified by simulation. It is deliberately small: 16 words of
memory, 10 instructions, and two clock phases per instruction.

The design is synthesizable-shaped but has no board target yet — for now this is
a simulation-only project. Icarus Verilog is the primary simulator; Vivado can
be pointed at the same two files as a cross-check.

> **Where this lives.** The project sits in WSL at `~/fpga_8bit_cpu`, because
> that is where the Icarus toolchain (`iverilog`, `vvp`, `make`, `gtkwave`) is
> installed — none of it is on the Windows side. Run everything from a WSL
> shell. Windows can still read the files at
> `\\wsl.localhost\<distro>\home\<user>\fpga_8bit_cpu`, which matters for the
> Vivado step below.

## Layout

```
fpga_8bit_cpu/
├── rtl/cpu.v         the CPU
├── sim/cpu_tb.v      testbench (Icarus, also works as a Vivado sim source)
├── verify/           randomized verification suite (golden model + mutation tests)
├── vivado/           empty — create the Vivado project here manually
├── Makefile          `make sim`, `make verify`, `make mutate`
└── README.md
```

## Running the simulation

From a WSL shell, in the project root (`cd ~/fpga_8bit_cpu`):

```
make sim
```

Without `make`, the two raw commands are:

```
iverilog -o sim/cpu_tb.vvp rtl/cpu.v sim/cpu_tb.v
vvp sim/cpu_tb.vvp
```

Expected output:

```
halted   = 1
out_val  = 6 (0x06)
expected = 6 (0x06)
PASS
```

The run also writes `sim/cpu_tb.vcd`, viewable in GTKWave (`make wave`, or
`gtkwave sim/cpu_tb.vcd`).

## Architecture

- **Data width** 8 bits; **address width** 4 bits → 16 words of unified memory,
  program and data sharing one space (Von Neumann).
- **Registers**: `pc` (4-bit program counter), `ir` (8-bit instruction
  register), `acc` (8-bit accumulator), `out_reg` (8-bit output latch), and a
  1-bit `carry` flag.
- **Two phases per instruction**, driven by a 1-bit FSM:
  - `FETCH` — `ir <= mem[pc]`, `pc <= pc + 1`
  - `EXEC` — decode `ir` and act
- **Instruction word**: bits `[7:4]` opcode, bits `[3:0]` operand (an address or
  a 4-bit immediate).
- `reset` is synchronous and active high. Once `HLT` executes, `halted` goes
  high and the CPU stops updating state until the next reset.

### Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | clock |
| `reset` | in | 1 | synchronous, active high |
| `out_val` | out | 8 | contents of the OUT latch |
| `halted` | out | 1 | high after `HLT` |

## Instruction set

| Opcode | Mnemonic | Action |
|---|---|---|
| `0000` | `NOP` | no-op |
| `0001` | `LDA addr` | `ACC ← mem[addr]` |
| `0010` | `ADD addr` | `ACC ← ACC + mem[addr]` (sets carry) |
| `0011` | `SUB addr` | `ACC ← ACC − mem[addr]` (sets carry on borrow) |
| `0100` | `STA addr` | `mem[addr] ← ACC` |
| `0101` | `LDI imm` | `ACC ← imm` (4-bit immediate, 0–15) |
| `0110` | `JMP addr` | `PC ← addr` |
| `0111` | `JC addr` | `PC ← addr`, only if carry set |
| `1110` | `OUT` | `OUT ← ACC` |
| `1111` | `HLT` | halt |

Opcodes `1000`–`1101` are unused and decode as `NOP`.

Carry semantics: `ADD` sets `carry` to the carry-out of the 8-bit addition;
`SUB` sets `carry` to the *borrow* out of the subtraction, i.e. it is set when
`ACC < mem[addr]`. Only `ADD` and `SUB` touch the flag — it survives every other
instruction, so `JC` can be placed some distance after the arithmetic that set
it.

## The demo program

The program is baked into `mem` by an `initial` block in `rtl/cpu.v` — there is
no external hex file to load. It computes `5 + 3 - 2 = 6`:

| Addr | Word | Assembly | Effect |
|---|---|---|---|
| 0 | `0x55` | `LDI 5` | `ACC = 5` |
| 1 | `0x2E` | `ADD 0xE` | `ACC = 5 + 3 = 8` |
| 2 | `0x3D` | `SUB 0xD` | `ACC = 8 - 2 = 6` |
| 3 | `0xE0` | `OUT` | `OUT = 6` |
| 4 | `0xF0` | `HLT` | stop |
| … | `0x00` | | unused |
| 13 | `0x02` | | data: subtrahend |
| 14 | `0x03` | | data: addend |
| 15 | `0x00` | | unused |

To try a different program, edit that `initial` block. Five instructions take
ten clocks, and the testbench allows twenty before declaring a timeout — raise
`MAX_CYCLES` in `sim/cpu_tb.v` if a longer program needs it.

## Randomized verification

Beyond the single demo program, `verify/` holds a randomized suite that checks
the RTL against a golden reference model:

- `verify/model.py` — a cycle-level Python model of the CPU (the golden
  reference).
- `verify/testbench.v` — a whitebox testbench that loads an arbitrary program
  into `mem`, runs it, and dumps a per-step trace (`pc`, `ir`, `acc`, `carry`,
  `out`, `halted`, and memory writes).
- `verify/run_random.py` — generates random programs, runs each through both
  the RTL (Icarus) and the Python model, and compares the traces step by step.

```
make verify
```

Defaults: 3000 random programs, up to 24 steps each, seed 42 (all overridable —
see `python3 verify/run_random.py --help`). Current status: **3000/3000
programs pass, 72000/72000 steps match**.

### Mutation testing

`verify/mutate.py` checks that the suite is actually capable of catching bugs.
It patches 10 deliberate bugs into a copy of `rtl/cpu.v` — swapped opcodes,
broken carry in ADD and in SUB, ADD/SUB swap, PC off-by-one, inverted JC, LDI
loading the wrong nibble, STA and HLT as no-ops, and reset failing to clear
ACC — and reruns the suite against each mutant:

```
make mutate
```

Current status: **10/10 mutants caught, mutation score 100%**.

## Next: open in Vivado

Vivado is used here purely as a second simulator, to confirm it reproduces the
result Icarus gave. There is no board target, so **skip synthesis, implementation,
and bitstream generation** — and no constraints file (`.xdc`) is needed.

Vivado runs on the Windows side, so it reaches these files over the WSL share at
`\\wsl.localhost\<distro>\home\<user>\fpga_8bit_cpu`. Vivado is occasionally
awkward about UNC paths for the *project* location — if it complains, copy
`rtl/cpu.v` and `sim/cpu_tb.v` to a plain Windows folder and build the project
there instead. Nothing in the design depends on where it sits.

1. Vivado → *Create Project* → RTL Project, location `vivado/`, and untick
   *Do not specify sources at this time*.
2. Add `rtl/cpu.v` as a **design source**. Set `cpu` as the top module.
3. Add `sim/cpu_tb.v` as a **simulation-only** source (Add Sources → *Add or
   create simulation sources*). Set `cpu_tb` as the simulation top.
4. *Run Simulation* → *Run Behavioral Simulation*.
5. Check the Tcl console for the same `out_val = 6 … PASS` lines, and inspect
   `pc`, `ir`, `acc`, and `state` in the waveform viewer.

One wrinkle: the testbench writes its VCD to the relative path `sim/cpu_tb.vcd`,
and Vivado runs from its own simulation directory, so the file lands somewhere
under `vivado/`. That is harmless — Vivado has its own waveform database and
does not need the VCD.
