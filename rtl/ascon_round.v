// ascon_round: one full Ascon permutation round = pC -> pS -> pL.
//
// Wires together the three layer submodules:
//   1. ascon_pC : adds the round constant selected by const_idx into x2
//   2. ascon_pS : bitsliced 5-bit S-box substitution layer
//   3. ascon_pL : word-wise linear diffusion layer
//
// const_idx follows the same convention as ascon_round_const/ascon_pC: it is
// an index into the 16-entry round-constant table, not a round counter. For
// an N-round permutation (N <= 12), round r (0-indexed, 0 = first round
// executed) uses const_idx = (16 - N) + r.
module ascon_round (
    input  wire [3:0]  const_idx,
    input  wire [63:0] x0_in,
    input  wire [63:0] x1_in,
    input  wire [63:0] x2_in,
    input  wire [63:0] x3_in,
    input  wire [63:0] x4_in,
    output wire [63:0] x0_out,
    output wire [63:0] x1_out,
    output wire [63:0] x2_out,
    output wire [63:0] x3_out,
    output wire [63:0] x4_out
);

    wire [63:0] x2_after_pc;

    ascon_pC u_pc (
        .s2_in     (x2_in),
        .const_idx (const_idx),
        .s2_out    (x2_after_pc)
    );

    wire [63:0] s0, s1, s2, s3, s4;

    ascon_pS u_ps (
        .x0_in (x0_in),
        .x1_in (x1_in),
        .x2_in (x2_after_pc),
        .x3_in (x3_in),
        .x4_in (x4_in),
        .x0_out(s0),
        .x1_out(s1),
        .x2_out(s2),
        .x3_out(s3),
        .x4_out(s4)
    );

    ascon_pL u_pl (
        .x0_in (s0),
        .x1_in (s1),
        .x2_in (s2),
        .x3_in (s3),
        .x4_in (s4),
        .x0_out(x0_out),
        .x1_out(x1_out),
        .x2_out(x2_out),
        .x3_out(x3_out),
        .x4_out(x4_out)
    );

endmodule
