// ---------------------------------------------------------------------------
// cpu.v -- minimal 8-bit accumulator CPU (SAP-1 style)
//
//   8-bit data, 4-bit address -> 16 words of unified (Von Neumann) memory.
//   Two clock phases per instruction: FETCH then EXEC.
//   Instruction word: [7:4] = opcode, [3:0] = operand (address or immediate).
// ---------------------------------------------------------------------------

`timescale 1ns / 1ps

module cpu (
    input  wire       clk,
    input  wire       reset,      // synchronous, active high
    output wire [7:0] out_val,    // OUT latch
    output wire       halted      // high once HLT has executed
);

    // ---- opcodes ----------------------------------------------------------
    localparam [3:0] OP_NOP = 4'h0,
                     OP_LDA = 4'h1,
                     OP_ADD = 4'h2,
                     OP_SUB = 4'h3,
                     OP_STA = 4'h4,
                     OP_LDI = 4'h5,
                     OP_JMP = 4'h6,
                     OP_JC  = 4'h7,
                     OP_OUT = 4'hE,
                     OP_HLT = 4'hF;

    // ---- phases -----------------------------------------------------------
    localparam FETCH = 1'b0,
               EXEC  = 1'b1;

    // ---- state --------------------------------------------------------------
    reg [7:0] mem [0:15];   // unified program + data memory

    reg [3:0] pc;           // program counter
    reg [7:0] ir;           // instruction register
    reg [7:0] acc;          // accumulator
    reg [7:0] out_reg;      // output latch
    reg       carry;        // carry-out of ADD / borrow-out of SUB
    reg       halt_reg;
    reg       state;

    wire [3:0] opcode  = ir[7:4];
    wire [3:0] operand = ir[3:0];

    // ADD / SUB widened to 9 bits so bit 8 gives us carry / borrow directly.
    wire [8:0] sum  = {1'b0, acc} + {1'b0, mem[operand]};
    wire [8:0] diff = {1'b0, acc} - {1'b0, mem[operand]};

    assign out_val = out_reg;
    assign halted  = halt_reg;

    // ---- demo program -------------------------------------------------------
    //   0: LDI 5        acc = 5
    //   1: ADD 0xE      acc = 5 + mem[14](3) = 8
    //   2: SUB 0xD      acc = 8 - mem[13](2) = 6
    //   3: OUT          out = 6
    //   4: HLT
    initial begin
        mem[ 0] = {OP_LDI, 4'd5};    // 8'h55
        mem[ 1] = {OP_ADD, 4'hE};    // 8'h2E
        mem[ 2] = {OP_SUB, 4'hD};    // 8'h3D
        mem[ 3] = {OP_OUT, 4'h0};    // 8'hE0
        mem[ 4] = {OP_HLT, 4'h0};    // 8'hF0
        mem[ 5] = 8'h00;
        mem[ 6] = 8'h00;
        mem[ 7] = 8'h00;
        mem[ 8] = 8'h00;
        mem[ 9] = 8'h00;
        mem[10] = 8'h00;
        mem[11] = 8'h00;
        mem[12] = 8'h00;
        mem[13] = 8'd2;              // data: subtrahend
        mem[14] = 8'd3;              // data: addend
        mem[15] = 8'h00;
    end

    // ---- FSM ----------------------------------------------------------------
    always @(posedge clk) begin
        if (reset) begin
            pc       <= 4'h0;
            ir       <= 8'h00;
            acc      <= 8'h00;
            out_reg  <= 8'h00;
            carry    <= 1'b0;
            halt_reg <= 1'b0;
            state    <= FETCH;
        end else if (!halt_reg) begin
            case (state)

                FETCH: begin
                    ir    <= mem[pc];
                    pc    <= pc + 4'd1;   // wraps at 15 -> 0, which is fine
                    state <= EXEC;
                end

                EXEC: begin
                    state <= FETCH;
                    case (opcode)
                        OP_NOP: ;                                  // nothing
                        OP_LDA: acc <= mem[operand];
                        OP_ADD: begin acc <= sum[7:0];  carry <= sum[8];  end
                        OP_SUB: begin acc <= diff[7:0]; carry <= diff[8]; end
                        OP_STA: mem[operand] <= acc;
                        OP_LDI: acc <= {4'h0, operand};
                        OP_JMP: pc  <= operand;
                        OP_JC:  if (carry) pc <= operand;
                        OP_OUT: out_reg <= acc;
                        OP_HLT: halt_reg <= 1'b1;
                        default: ;                                 // unused -> NOP
                    endcase
                end

            endcase
        end
    end

endmodule
