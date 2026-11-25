"""
model.py -- golden reference model of the 8-bit SAP-1-style CPU.

A pure-Python re-implementation of rtl/cpu.v's instruction semantics, used as
the oracle for the randomized RTL verification suite (run_random.py) and for
mutation testing (mutate.py). Kept intentionally dumb and literal so it is
easy to audit against the instruction table in README.md -- it is the thing
the RTL is being checked *against*, so it must not share a bug with the RTL
by construction.

Opcode encoding matches rtl/cpu.v exactly (top nibble = opcode, bottom nibble
= operand/immediate). ADD/SUB carry semantics also match the RTL bit-for-bit:
both are computed as 9-bit unsigned arithmetic, and bit 8 of the result is
the carry flag (so SUB's "carry" is really a borrow flag, set when
acc < mem[operand]).
"""

from dataclasses import dataclass, field

OP_NOP = 0x0
OP_LDA = 0x1
OP_ADD = 0x2
OP_SUB = 0x3
OP_STA = 0x4
OP_LDI = 0x5
OP_JMP = 0x6
OP_JC = 0x7
OP_OUT = 0xE
OP_HLT = 0xF


@dataclass
class SapModel:
    mem: list
    pc: int = 0
    acc: int = 0
    carry: int = 0
    out: int = 0
    halted: bool = False

    def __post_init__(self):
        if len(self.mem) != 16:
            raise ValueError("mem must have exactly 16 words")
        self.mem = list(self.mem)

    def step(self):
        """Execute one FETCH+EXEC instruction cycle (a no-op once halted,
        matching the RTL's `else if (!halt_reg)` guard)."""
        if self.halted:
            return

        instr = self.mem[self.pc]
        self.pc = (self.pc + 1) & 0xF
        opcode = (instr >> 4) & 0xF
        operand = instr & 0xF

        if opcode == OP_NOP:
            pass
        elif opcode == OP_LDA:
            self.acc = self.mem[operand]
        elif opcode == OP_ADD:
            s = (self.acc + self.mem[operand]) & 0x1FF
            self.carry = (s >> 8) & 1
            self.acc = s & 0xFF
        elif opcode == OP_SUB:
            d = (self.acc - self.mem[operand]) & 0x1FF
            self.carry = (d >> 8) & 1
            self.acc = d & 0xFF
        elif opcode == OP_STA:
            self.mem[operand] = self.acc
        elif opcode == OP_LDI:
            self.acc = operand
        elif opcode == OP_JMP:
            self.pc = operand
        elif opcode == OP_JC:
            if self.carry:
                self.pc = operand
        elif opcode == OP_OUT:
            self.out = self.acc
        elif opcode == OP_HLT:
            self.halted = True
        else:
            pass  # reserved opcodes (0x8-0xD) decode as NOP

    def snapshot(self):
        """(pc, acc, carry, out, halted, mem-tuple) -- the full architectural
        state, in the same field order the RTL testbench prints it."""
        return (self.pc, self.acc, self.carry, self.out, self.halted, tuple(self.mem))

    def run_trace(self, max_steps):
        """Run up to max_steps instructions, returning one snapshot per step
        (including steps after HLT, which just repeat the frozen state --
        this keeps traces a fixed length, which the RTL side matches too)."""
        trace = []
        for _ in range(max_steps):
            self.step()
            trace.append(self.snapshot())
        return trace
