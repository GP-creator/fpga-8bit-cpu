// ---------------------------------------------------------------------------
// testbench.v -- generic randomized trace-dumping testbench.
//
//   Loads NUM_TESTS programs (16 words each) from verify/work/programs.hex,
//   runs each for MAX_STEPS instructions, and prints one state snapshot per
//   instruction to stdout. run_random.py (or mutate.py) parses that output
//   and compares it, step by step, against model.py's prediction for the
//   same program -- this file only produces the RTL side of the trace, it
//   does not itself judge pass/fail.
//
//   Whitebox by necessity: `mem` isn't a port, so loading a test program and
//   dumping memory state both go through the hierarchical reference
//   `dut.mem`. Same technique used ad hoc while developing sim/cpu_tb.v.
//
//   Timing note: each instruction takes exactly two clock edges (FETCH,
//   then EXEC), even after HLT -- once `halt_reg` is set, the CPU's own
//   `else if (!halt_reg)` guard makes every further edge a no-op. So this
//   testbench never needs to inspect `dut.state` to know when an
//   instruction has completed: it simply pulses two edges per step and
//   samples on the following negedge, when NBA updates from the second
//   edge have already settled. Padding steps after HLT harmlessly repeat
//   the same frozen state on both the RTL and reference side.
// ---------------------------------------------------------------------------

`timescale 1ns / 1ps

`ifndef NUM_TESTS
`define NUM_TESTS 100
`endif
`ifndef MAX_STEPS
`define MAX_STEPS 24
`endif

module testbench;

    parameter NUM_TESTS = `NUM_TESTS;
    parameter MAX_STEPS = `MAX_STEPS;

    reg        clk = 1'b0;
    reg        reset = 1'b1;
    wire [7:0] out_val;
    wire       halted;

    integer t, s, i;
    reg [7:0] flat_mem [0:NUM_TESTS*16-1];

    cpu dut (
        .clk     (clk),
        .reset   (reset),
        .out_val (out_val),
        .halted  (halted)
    );

    always #5 clk = ~clk;

    initial begin
        $readmemh("verify/work/programs.hex", flat_mem);

        for (t = 0; t < NUM_TESTS; t = t + 1) begin
            // hold reset while loading this test's program into dut.mem
            reset = 1'b1;
            @(posedge clk);
            for (i = 0; i < 16; i = i + 1)
                dut.mem[i] = flat_mem[t * 16 + i];
            @(posedge clk);
            @(negedge clk);
            reset = 1'b0;

            for (s = 0; s < MAX_STEPS; s = s + 1) begin
                @(posedge clk);   // FETCH
                @(posedge clk);   // EXEC
                @(negedge clk);   // let NBA updates settle before sampling

                $write("S %0d %0d %h %h %b %h %b", t, s, dut.pc, dut.acc,
                       dut.carry, out_val, halted);
                for (i = 0; i < 16; i = i + 1)
                    $write(" %h", dut.mem[i]);
                $write("\n");
            end
        end

        $display("DONE");
        $finish;
    end

endmodule
