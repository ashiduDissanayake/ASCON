// ascon_permutation: full Ascon permutation p^ROUNDS (default 12 rounds).
//
// Combinationally unrolls ROUNDS instances of ascon_round. State is packed
// into/out of a single 320-bit bus, most-significant word first, matching
// the vector format produced by model/gen_vectors.py:
//   state[319:256] = x0   state[255:192] = x1   state[191:128] = x2
//   state[127:64]  = x3   state[63:0]    = x4
//
// const_idx for round r (0-indexed, r = 0 is the first round executed) is
// (16 - ROUNDS) + r, per the round-constant table in ascon_round_const.v
// (see also model/refmodel.py::permutation and
// pyascon/ascon.py::ascon_permutation, which use the equivalent
// 0xf0 - r*0x10 + r formula for a 12-round permutation).
module ascon_permutation #(
    parameter integer ROUNDS = 12
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,
    input  wire [319:0] state_in,
    output reg  [319:0] state_out,
    output reg         done
);

    reg [319:0] state_reg;
    reg [7:0] round_count;
    reg running;

    wire [63:0] x0_cur, x1_cur, x2_cur, x3_cur, x4_cur;
    wire [63:0] x0_next, x1_next, x2_next, x3_next, x4_next;
    wire [319:0] state_next;

    assign x0_cur = state_reg[319:256];
    assign x1_cur = state_reg[255:192];
    assign x2_cur = state_reg[191:128];
    assign x3_cur = state_reg[127:64];
    assign x4_cur = state_reg[63:0];
    
    wire [7:0] const_idx_full = (16 - ROUNDS) + round_count;

    ascon_round u_round (
        .const_idx(const_idx_full[3:0]),
        .x0_in (x0_cur),
        .x1_in (x1_cur),
        .x2_in (x2_cur),
        .x3_in (x3_cur),
        .x4_in (x4_cur),
        .x0_out(x0_next),
        .x1_out(x1_next),
        .x2_out(x2_next),
        .x3_out(x3_next),
        .x4_out(x4_next)
    );

    assign state_next = {x0_next, x1_next, x2_next, x3_next, x4_next};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_reg  <= 320'd0;
            state_out  <= 320'd0;
            round_count <= 8'd0;
            running    <= 1'b0;
            done       <= 1'b0;
        end else begin
            done <= 1'b0;

            if (start && !running) begin
                state_reg   <= state_in;
                state_out   <= state_in;
                round_count <= 8'd0;
                running     <= 1'b1;
            end else if (running) begin
                if (round_count == (ROUNDS - 1)) begin
                    state_reg   <= state_next;
                    state_out   <= state_next;
                    round_count <= 8'd0;
                    running     <= 1'b0;
                    done        <= 1'b1;
                end else begin
                    state_reg   <= state_next;
                    state_out   <= state_next;
                    round_count <= round_count + 8'd1;
                end
            end
        end
    end

endmodule
