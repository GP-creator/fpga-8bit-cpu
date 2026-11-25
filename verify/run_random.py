#!/usr/bin/env python3
"""
run_random.py -- randomized self-checking testbench driver.

Generates N random-but-valid 16-word programs, runs each one through both
the RTL (via Icarus Verilog + testbench.v) and the Python golden reference
model (model.py), and compares the two instruction-by-instruction. This is
the "self-checking" part: nothing here trusts a canned expected value, the
reference model computes what should happen fresh for every random program.

Standalone use:
    python3 verify/run_random.py --num-tests 3000 --max-steps 24 --seed 42

Also importable: mutate.py reuses generate_programs()/reference_traces()/
compile_rtl()/run_rtl()/parse_rtl_trace()/compare() directly so it can rerun
just the RTL half of the pipeline against each mutant without regenerating
the (cheap, deterministic) reference traces from scratch each time.
"""

import argparse
import pathlib
import random
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from model import SapModel  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERIFY = ROOT / "verify"
WORK = VERIFY / "work"

# Only the 10 defined mnemonics -- HLT is under-weighted relative to the
# others so a typical random program runs several instructions before it
# halts (or is cut off by MAX_STEPS) instead of stopping immediately.
VALID_OPCODES = [0x0, 0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0xE, 0xF]
OPCODE_WEIGHTS = [3, 3, 3, 3, 3, 3, 3, 3, 3, 1]


def gen_program(rng):
    return [
        (rng.choices(VALID_OPCODES, weights=OPCODE_WEIGHTS)[0] << 4) | rng.randrange(16)
        for _ in range(16)
    ]


def generate_programs(num_tests, seed):
    rng = random.Random(seed)
    return [gen_program(rng) for _ in range(num_tests)]


def write_programs_hex(programs, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for prog in programs:
            for word in prog:
                f.write(f"{word:02x}\n")


def reference_traces(programs, max_steps):
    return [SapModel(prog).run_trace(max_steps) for prog in programs]


def compile_rtl(cpu_v_path, num_tests, max_steps, out_vvp):
    out_vvp.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "iverilog",
        f"-DNUM_TESTS={num_tests}",
        f"-DMAX_STEPS={max_steps}",
        "-o", str(out_vvp),
        str(cpu_v_path),
        str(VERIFY / "testbench.v"),
    ]
    subprocess.run(cmd, check=True, cwd=ROOT, capture_output=True, text=True)


def run_rtl(vvp_path):
    proc = subprocess.run(
        ["vvp", str(vvp_path)], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return proc.stdout


def parse_rtl_trace(stdout, num_tests, max_steps):
    traces = [[None] * max_steps for _ in range(num_tests)]
    for line in stdout.splitlines():
        if not line.startswith("S "):
            continue
        parts = line.split()
        t, s = int(parts[1]), int(parts[2])
        pc = int(parts[3], 16)
        acc = int(parts[4], 16)
        carry = int(parts[5], 2)
        out = int(parts[6], 16)
        halted = bool(int(parts[7], 2))
        mem = tuple(int(x, 16) for x in parts[8:8 + 16])
        traces[t][s] = (pc, acc, carry, out, halted, mem)
    return traces


def compare(ref_traces, rtl_traces):
    """Per-test result list of dicts: {passed, first_mismatch_step, ref, rtl}."""
    results = []
    total_steps = 0
    passed_steps = 0
    for t, (ref_trace, rtl_trace) in enumerate(zip(ref_traces, rtl_traces)):
        first_mismatch = None
        for s, (ref_snap, rtl_snap) in enumerate(zip(ref_trace, rtl_trace)):
            total_steps += 1
            if rtl_snap is not None and tuple(ref_snap) == tuple(rtl_snap):
                passed_steps += 1
            elif first_mismatch is None:
                first_mismatch = (s, ref_snap, rtl_snap)
        results.append({
            "test": t,
            "passed": first_mismatch is None,
            "first_mismatch": first_mismatch,
        })
    return results, total_steps, passed_steps


def run_suite(cpu_v_path, num_tests, max_steps, seed, label="rtl"):
    """Full pipeline against one RTL source file. Returns (results, programs,
    ref_traces, total_steps, passed_steps)."""
    programs = generate_programs(num_tests, seed)
    hex_path = WORK / "programs.hex"
    write_programs_hex(programs, hex_path)

    ref_traces = reference_traces(programs, max_steps)

    vvp_path = WORK / f"{label}.vvp"
    compile_rtl(cpu_v_path, num_tests, max_steps, vvp_path)
    stdout = run_rtl(vvp_path)
    rtl_traces = parse_rtl_trace(stdout, num_tests, max_steps)

    results, total_steps, passed_steps = compare(ref_traces, rtl_traces)
    return results, programs, ref_traces, total_steps, passed_steps


def format_snapshot(snap):
    if snap is None:
        return "<no RTL output for this step>"
    pc, acc, carry, out, halted, mem = snap
    mem_str = " ".join(f"{b:02x}" for b in mem)
    return (f"pc={pc:x} acc={acc:02x} carry={carry} out={out:02x} "
            f"halted={int(halted)} mem=[{mem_str}]")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--num-tests", type=int, default=3000)
    ap.add_argument("--max-steps", type=int, default=24)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cpu-v", type=pathlib.Path, default=ROOT / "rtl" / "cpu.v")
    ap.add_argument("--log-failures", type=int, default=10,
                     help="max number of failing tests to detail in the log file")
    args = ap.parse_args()

    print(f"Random self-checking suite")
    print(f"  cpu.v          : {args.cpu_v}")
    print(f"  vectors        : {args.num_tests}")
    print(f"  max steps/test : {args.max_steps}")
    print(f"  seed           : {args.seed}")

    results, programs, ref_traces, total_steps, passed_steps = run_suite(
        args.cpu_v, args.num_tests, args.max_steps, args.seed
    )

    passed_tests = sum(r["passed"] for r in results)
    num_tests = len(results)

    print()
    print(f"  vectors (programs) : {num_tests}")
    print(f"  step-comparisons   : {total_steps}")
    print(f"  PASS programs      : {passed_tests} / {num_tests} "
          f"({100.0 * passed_tests / num_tests:.2f}%)")
    print(f"  PASS steps         : {passed_steps} / {total_steps} "
          f"({100.0 * passed_steps / total_steps:.2f}%)")

    failing = [r for r in results if not r["passed"]]
    if failing:
        log_path = WORK / "failures.log"
        WORK.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w") as f:
            for r in failing[:args.log_failures]:
                t = r["test"]
                s, ref_snap, rtl_snap = r["first_mismatch"]
                prog_str = " ".join(f"{w:02x}" for w in programs[t])
                f.write(f"test {t}, first divergence at step {s}\n")
                f.write(f"  program: {prog_str}\n")
                f.write(f"  ref: {format_snapshot(ref_snap)}\n")
                f.write(f"  rtl: {format_snapshot(rtl_snap)}\n\n")
        print(f"\n  {len(failing)} failing test(s) -- details in {log_path}")

    sys.exit(0 if not failing else 1)


if __name__ == "__main__":
    main()
