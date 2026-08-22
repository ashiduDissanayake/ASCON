// ascon_pS: Ascon substitution layer (S-box), NIST SP 800-232.
//
// Implements the 5-bit S-box applied bitsliced in parallel across all 64
// bit-slices of the 5-word, 320-bit Ascon state. This module operates on a
// single round's 5 words *after* the constant-addition layer (ascon_pC) has
// already been applied to x2, and produces the 5 words to be consumed by the
// linear diffusion layer (ascon_pL).
//
// Reference (bitsliced chi5 S-box), matching model/refmodel.py::permutation
// and pyascon/ascon.py::ascon_permutation:
//   x0 ^= x4;  x4 ^= x3;  x2 ^= x1;
//   t0 = ~x0 & x1;  t1 = ~x1 & x2;  t2 = ~x2 & x3;  t3 = ~x3 & x4;  t4 = ~x4 & x0;
//   x0 ^= t1;  x1 ^= t2;  x2 ^= t3;  x3 ^= t4;  x4 ^= t0;
//   x1 ^= x0;  x0 ^= x4;  x3 ^= x2;  x2 ^= ~0;
//
// All values above are taken *after* the preceding assignment in program
// order; the Verilog below spells that out with distinct wire names instead
// of reusing x0..x4, since continuous assignments have no notion of "in
// program order" on the same net.
module ascon_pS (
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

    // Step 1: x0 ^= x4; x4 ^= x3; x2 ^= x1  (x1 and x3 pass through unchanged)
    wire [63:0] a0 = x0_in ^ x4_in;
    wire [63:0] a1 = x1_in;
    wire [63:0] a2 = x2_in ^ x1_in;
    wire [63:0] a3 = x3_in;
    wire [63:0] a4 = x4_in ^ x3_in;

    // Step 2: nonlinear term, T[i] = ~a[i] & a[(i+1)%5]
    wire [63:0] t0 = (~a0) & a1;
    wire [63:0] t1 = (~a1) & a2;
    wire [63:0] t2 = (~a2) & a3;
    wire [63:0] t3 = (~a3) & a4;
    wire [63:0] t4 = (~a4) & a0;

    // Step 3: x[i] ^= T[(i+1)%5]
    wire [63:0] b0 = a0 ^ t1;
    wire [63:0] b1 = a1 ^ t2;
    wire [63:0] b2 = a2 ^ t3;
    wire [63:0] b3 = a3 ^ t4;
    wire [63:0] b4 = a4 ^ t0;

    // Step 4: x1 ^= x0; x0 ^= x4; x3 ^= x2; x2 = ~x2
    assign x1_out = b1 ^ b0;
    assign x0_out = b0 ^ b4;
    assign x3_out = b3 ^ b2;
    assign x2_out = ~b2;
    assign x4_out = b4;

endmodule
