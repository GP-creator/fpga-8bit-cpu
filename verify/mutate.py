#!/usr/bin/env python3
"""
mutate.py -- mutation testing for the randomized verification suite.

Applies one hand-picked RTL bug at a time to a scratch copy of rtl/cpu.v,
reruns the exact same random test vectors used for the real cpu.v (same
seed, so both sides see the identical programs), and reports whether the
suite noticed. A mutant the suite fails to catch ("survived") is evidence of
a real coverage gap in the random generator or the comparison logic, not
just a curiosity -- it means some class of RTL bug would slip through this
whole verification setup undetected.

Each mutation is a literal source-text patch against rtl/cpu.v: an
(old_string, new_string) pair (or a list of them, applied together) that
must match exactly once. If a patch's anchor text doesn't match rtl/cpu.v
verbatim -- because the file was edited after this list was written -- the
mutant is reported as "patch failed to apply" rather than silently skipped
or silently matching the wrong spot.

Usage:
    python3 verify/mutate.py [--num-tests 3000] [--max-steps 24] [--seed 42]
"""

import argparse
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import run_random  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
RTL_CPU_V = ROOT / "rtl" / "cpu.v"
WORK = ROOT / "verify" / "work"
MUTANTS_DIR = WORK / "mutants"


MUTATIONS = [
    {
        "id": "opcode_decode_flip",
        "desc": "LDA and STA opcode values swapped (1<->4) in the decode table",
        "patches": [
            ("OP_LDA = 4'h1,", "OP_LDA = 4'h4,"),
            ("OP_STA = 4'h4,", "OP_STA = 4'h1,"),
        ],
    },
    {
        "id": "broken_carry_add",
        "desc": "ADD never updates the carry flag",
        "patches": [
            ("OP_ADD: begin acc <= sum[7:0];  carry <= sum[8];  end",
             "OP_ADD: begin acc <= sum[7:0];  carry <= carry;  end"),
        ],
    },
    {
        "id": "broken_carry_sub",
        "desc": "SUB never updates the carry (borrow) flag",
        "patches": [
            ("OP_SUB: begin acc <= diff[7:0]; carry <= diff[8]; end",
             "OP_SUB: begin acc <= diff[7:0]; carry <= carry; end"),
        ],
    },
    {
        "id": "addsub_swap",
        "desc": "ADD and SUB results swapped (ADD computes a subtraction and vice versa)",
        "patches": [
            ("OP_ADD: begin acc <= sum[7:0];  carry <= sum[8];  end",
             "OP_ADD: begin acc <= diff[7:0];  carry <= diff[8];  end"),
            ("OP_SUB: begin acc <= diff[7:0]; carry <= diff[8]; end",
             "OP_SUB: begin acc <= sum[7:0]; carry <= sum[8]; end"),
        ],
    },
    {
        "id": "pc_off_by_one",
        "desc": "PC advances by 2 each FETCH instead of 1",
        "patches": [
            ("pc    <= pc + 4'd1;   // wraps at 15 -> 0, which is fine",
             "pc    <= pc + 4'd2;   // wraps at 15 -> 0, which is fine"),
        ],
    },
    {
        "id": "jc_inverted",
        "desc": "JC branches when carry is clear instead of when it is set",
        "patches": [
            ("OP_JC:  if (carry) pc <= operand;",
             "OP_JC:  if (!carry) pc <= operand;"),
        ],
    },
    {
        "id": "ldi_wrong_nibble",
        "desc": "LDI loads its immediate into the high nibble of ACC instead of the low nibble",
        "patches": [
            ("OP_LDI: acc <= {4'h0, operand};",
             "OP_LDI: acc <= {operand, 4'h0};"),
        ],
    },
    {
        "id": "sta_noop",
        "desc": "STA never actually writes memory",
        "patches": [
            ("OP_STA: mem[operand] <= acc;",
             "OP_STA: mem[operand] <= mem[operand];"),
        ],
    },
    {
        "id": "hlt_noop",
        "desc": "HLT never sets halt_reg, so the CPU never halts",
        "patches": [
            ("OP_HLT: halt_reg <= 1'b1;",
             "OP_HLT: ;"),
        ],
    },
    {
        "id": "reset_acc_leak",
        "desc": "reset doesn't clear ACC, so state leaks from one test into the next",
        "patches": [
            ("acc      <= 8'h00;",
             "acc      <= acc;"),
        ],
    },
]


def apply_patches(src_text, patches):
    text = src_text
    for old, new in patches:
        count = text.count(old)
        if count != 1:
            raise ValueError(
                f"anchor text matched {count} time(s), expected exactly 1: {old!r}"
            )
        text = text.replace(old, new, 1)
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--num-tests", type=int, default=3000)
    ap.add_argument("--max-steps", type=int, default=24)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    MUTANTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Baseline: running the suite against the real rtl/cpu.v ...")
    base_results, _, _, base_total, base_passed = run_random.run_suite(
        RTL_CPU_V, args.num_tests, args.max_steps, args.seed, label="baseline"
    )
    base_failed = [r for r in base_results if not r["passed"]]
    if base_failed:
        print(f"\nBaseline FAILED: {len(base_failed)}/{len(base_results)} test(s) "
              f"already mismatch against the unmodified RTL.")
        print("Mutation testing is meaningless on a failing baseline -- fix rtl/cpu.v "
              "(or the reference model) first. Aborting.")
        sys.exit(1)
    print(f"Baseline OK: {len(base_results)}/{len(base_results)} programs, "
          f"{base_passed}/{base_total} steps pass.\n")

    src_text = RTL_CPU_V.read_text()

    caught, survived, errored = 0, 0, 0
    rows = []

    for mut in MUTATIONS:
        mid = mut["id"]
        try:
            mutant_text = apply_patches(src_text, mut["patches"])
        except ValueError as e:
            errored += 1
            rows.append((mid, mut["desc"], "PATCH FAILED", str(e)))
            print(f"[{mid}] patch failed to apply: {e}")
            continue

        mutant_path = MUTANTS_DIR / f"{mid}.v"
        mutant_path.write_text(mutant_text)

        try:
            results, _, _, total_steps, passed_steps = run_random.run_suite(
                mutant_path, args.num_tests, args.max_steps, args.seed, label=f"mut_{mid}"
            )
        except subprocess.CalledProcessError as e:
            errored += 1
            detail = (e.stderr or "")[-300:]
            rows.append((mid, mut["desc"], "COMPILE ERROR", detail))
            print(f"[{mid}] compile error -- {detail.strip()[:120]}")
            continue

        failed = [r for r in results if not r["passed"]]
        if failed:
            caught += 1
            ex = failed[0]
            s, ref_snap, rtl_snap = ex["first_mismatch"]
            detail = (f"caught by test {ex['test']} at step {s}: "
                      f"ref={run_random.format_snapshot(ref_snap)} "
                      f"rtl={run_random.format_snapshot(rtl_snap)}")
            rows.append((mid, mut["desc"], "CAUGHT", detail))
            print(f"[{mid}] CAUGHT ({len(failed)}/{len(results)} programs diverged)")
        else:
            survived += 1
            rows.append((mid, mut["desc"], "SURVIVED", ""))
            print(f"[{mid}] SURVIVED -- suite did not notice this bug!")

    total = len(MUTATIONS)
    print()
    print("=" * 78)
    print(f"{'id':<20}{'result':<12}description")
    print("-" * 78)
    for mid, desc, status, _ in rows:
        print(f"{mid:<20}{status:<12}{desc}")
    print("=" * 78)
    print(f"Mutants: {total}  Caught: {caught}  Survived: {survived}  Errored: {errored}")
    if total - errored > 0:
        print(f"Mutation score (caught / (total - errored)): "
              f"{100.0 * caught / (total - errored):.1f}%")

    sys.exit(0 if survived == 0 and errored == 0 else 1)


if __name__ == "__main__":
    main()
