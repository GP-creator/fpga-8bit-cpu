// ---------------------------------------------------------------------------
// cpu_tb.v -- Icarus Verilog testbench for the 8-bit CPU.
//
//   Clocks the CPU, pulses reset, waits for `halted`, prints OUT.
//   The baked-in demo program computes 5 + 3 - 2 = 6.
// ---------------------------------------------------------------------------

`timescale 1ns / 1ps

module cpu_tb;

    localparam [7:0] EXPECTED = 8'd6;
    localparam       MAX_CYCLES = 20;

    reg        clk = 1'b0;
    reg        reset = 1'b1;
    wire [7:0] out_val;
    wire       halted;

    integer cycles = 0;

    cpu dut (
        .clk     (clk),
        .reset   (reset),
        .out_val (out_val),
        .halted  (halted)
    );

    // 100 MHz-ish: 10 ns period
    always #5 clk = ~clk;

    // count executed clocks so we can bail out if the CPU never halts
    always @(posedge clk) begin
        if (!reset) begin
            cycles = cycles + 1;
            if (cycles > MAX_CYCLES) begin
                $display("FAIL: CPU did not halt within %0d cycles", MAX_CYCLES);
                $finish;
            end
        end
    end

    initial begin
        $dumpfile("sim/cpu_tb.vcd");
        $dumpvars(0, cpu_tb);

        // hold reset for two rising edges, then release
        reset = 1'b1;
        @(posedge clk);
        @(posedge clk);
        @(negedge clk);
        reset = 1'b0;

        // run until the CPU halts
        wait (halted);
        @(posedge clk);   // let the last write settle

        $display("");
        $display("halted   = %b", halted);
        $display("out_val  = %0d (0x%02h)", out_val, out_val);
        $display("expected = %0d (0x%02h)", EXPECTED, EXPECTED);
        if (out_val === EXPECTED)
            $display("PASS");
        else
            $display("FAIL");
        $display("");

        $finish;
    end

endmodule
