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
    input  wire [319:0] state_in,
    output wire [319:0] state_out
);

    // words[0] holds the state entering round 0, words[ROUNDS] holds the
    // final state after all rounds have been applied.
    wire [63:0] x0 [0:ROUNDS];
    wire [63:0] x1 [0:ROUNDS];
    wire [63:0] x2 [0:ROUNDS];
    wire [63:0] x3 [0:ROUNDS];
    wire [63:0] x4 [0:ROUNDS];

    assign x0[0] = state_in[319:256];
    assign x1[0] = state_in[255:192];
    assign x2[0] = state_in[191:128];
    assign x3[0] = state_in[127:64];
    assign x4[0] = state_in[63:0];

    genvar r;
    generate
        for (r = 0; r < ROUNDS; r = r + 1) begin : g_round
            ascon_round u_round (
                .const_idx(4'((16 - ROUNDS) + r)),
                .x0_in (x0[r]),
                .x1_in (x1[r]),
                .x2_in (x2[r]),
                .x3_in (x3[r]),
                .x4_in (x4[r]),
                .x0_out(x0[r+1]),
                .x1_out(x1[r+1]),
                .x2_out(x2[r+1]),
                .x3_out(x3[r+1]),
                .x4_out(x4[r+1])
            );
        end
    endgenerate

    assign state_out = {x0[ROUNDS], x1[ROUNDS], x2[ROUNDS], x3[ROUNDS], x4[ROUNDS]};

endmodule
